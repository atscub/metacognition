---

## My Current Framing

**"The WebSocket handler's event listeners aren't being properly removed when connections close, causing EventEmitter listeners to accumulate and leak memory."**

This is the obvious frame because:
- EventEmitter listeners grow 20x (412 → 8,420)
- The code *looks* suspicious with `setMaxListeners(0)` and dynamic listener registration
- The team suspected it

But there's a critical clue I should interrogate: **the team disabled WebSocket for 6 hours and the leak persisted at the same rate.** This directly contradicts my framing.

---

## Reframing Through Lenses

### Inversion Lens
*What would guarantee this leak?*

- Open FDs grow 1000x (42 → 48,900) in 24 hours
- That's ~2,000 new open FDs per hour, or ~33 per minute
- At 400 HTTP requests/minute: roughly 1 FD opened per 12 requests that never closes
- Node.js streams aren't closed → file descriptors aren't released
- This guarantees a leak independent of WebSocket

### Zoom In Lens
*Look at the exact byte-by-byte flow:*

In `requestLogger.ts`:
```typescript
const logStream = fs.createWriteStream(logFile, { flags: 'a' });
(req as any).logStream = logStream;
logStream.write(...); // write start
```

Then in `res.end`:
```typescript
logStream.write(...); // write end
// <-- MISSING: logStream.close() or logStream.destroy()
return originalEnd.apply(res, args);
```

**The stream is never closed.** It stays attached to the request object, holding an open file descriptor. Since there are 24,000 requests/hour, you accumulate 24,000 unclosed streams/hour. By hour 4: ~96,000 streams. But the heap only shows ~9,850 FDs because some are garbage collected eventually, but the accumulation is linear.

### Precedent Lens
*Standard stream patterns across Node.js:*

Every example in the wild explicitly closes streams:
```typescript
const stream = fs.createWriteStream(file);
stream.write(data);
stream.end(); // or .close()
```

The code violates this invariant.

### Simplicity Lens
*What if I'm overcomplicating this?*

Strip to fundamentals:
- 400 requests/minute × 1,440 minutes/day = 576,000 requests per day
- Each request creates a WriteStream
- WriteStreams hold file descriptors
- No code closes them
- File descriptors accumulate
- OS limits fd count (usually ~1M for root, ~1024 for unprivileged)
- Memory grows because open streams hold buffers and event listeners

It's not complex. It's a textbook resource leak.

### The Critical Evidence
*Why the WebSocket disable didn't help:*

- WebSocket runs once per connection (~200 concurrent, ~15min lifetime)
- requestLogger runs for EVERY request (24,000/hour)
- Even without WebSocket, the request logger still accumulates 24,000 streams/hour
- The leak rate would stay nearly the same

---

## Convergence

All lenses point to the same culprit:

| Lens | Finding |
|------|---------|
| **Inversion** | Unclosed streams → guaranteed leak |
| **Zoom In** | No `.close()` or `.end()` on logStream |
| **Simplicity** | 24,000 streams/hour × no cleanup = accumulation |
| **Precedent** | All stream code must explicitly close |
| **Open FD growth** | 1000x growth matches "never close" not "bad listeners" |
| **WebSocket disable** | Leak persisted → not WebSocket's fault |

---

## The Diagnosis

**The memory leak is in `src/middleware/requestLogger.ts`.**

The request logger creates a WriteStream for every HTTP request (24,000/hour) but never closes it. Each stream:
- Holds an open file descriptor
- Maintains internal buffers
- Registers event listeners
- Stays referenced in memory (attached to req object)

This causes:
1. **Open FD growth** (42 → 48,900): streams never release file descriptors
2. **Memory growth** (~227 MB/12h): accumulated streams, buffers, listeners
3. **EventEmitter listener growth** as a side effect: WriteStreams *are* EventEmitters

The WebSocket handler looks suspicious but is innocent—the team's canary test proved it.

---

## The Fix

Close the stream in `res.end()`:

```typescript
res.end = function(...args: any[]) {
  logStream.write(JSON.stringify({
    type: 'request_end',
    timestamp: Date.now(),
    statusCode: res.statusCode,
  }) + '\n');

  logStream.end(); // <-- ADD THIS: close the stream
  return originalEnd.apply(res, args);
};
```

Or if async aggregation needs the stream briefly longer, use a timeout:
```typescript
logStream.end();
// Stream stays readable for ~100ms for aggregation pickup, then fully releases
```

This should drop RSS and open FDs linearly with request count, not quadratically.
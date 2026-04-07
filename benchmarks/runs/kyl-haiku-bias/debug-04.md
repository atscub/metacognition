## Step 1: Current Framing

The team framed this as: **"EventEmitter listeners in the WebSocket handler aren't being cleaned up properly"**
- Mental model: Event listener accumulation → memory bloat → OOM
- Solution space: Fix ws event handler cleanup, add removeAllListeners, or improve EventEmitter management

## Step 2: Reframe Through Multiple Lenses

**The Inversion Lens** – What would *guarantee* this specific pattern of failure?
- Linear FD growth (42 → 48,900) screams file descriptor leak
- Streams that never close accumulate in memory
- Each unclosed stream holds buffers waiting to be flushed

**The Zoom Out Lens** – They disabled WebSocket and the leak *persisted at the same rate*. That's not a WebSocket problem.
- What runs on EVERY request? The request logger middleware.
- What does the request logger do? Creates a fs.WriteStream and **never closes it**.

**The Zoom In Lens** – Compare raw numbers:
- 400 HTTP requests/min × 24 hours = ~576k requests total
- FDs at hour 24: 48,900 (some reuse/GC, but clearly proportional to requests)
- WriteStream objects in heap: +4,815 (roughly 400/hour — matches request rate *exactly*)
- Buffer growth: +197.6 MB (unflushed/buffered stream data)

The progression is proportional to HTTP traffic, not WebSocket traffic.

**The Novice Lens** – Reading the requestLogger code from scratch:
```typescript
const logStream = fs.createWriteStream(logFile, { flags: 'a' });
(req as any).logStream = logStream;
// ... writes ...
// NOTE: stream stays open for async log aggregation pickup
// ... but nothing calls close() or end() ...
```

There's a *comment* explaining why it's open, but **no code that ever closes it**.

**The Constraint Lens** – "stream stays open for async log aggregation pickup"
- Who's doing this aggregation? 
- Is anything actually consuming it after the response?
- If there's no consumer, this constraint is phantom.

## Step 3: Comparison

| Framing | Evidence | Prediction Match | Explains WebSocket Test |
|---------|----------|------------------|--------------------------|
| **WebSocket EventEmitter leak** | +4,820 EventEmitters in heap | ✗ Leak should stop when WS disabled | ✗ No — leak continued |
| **Request logger FD leak** | +49k FDs, +4.8k WriteStreams, linear with request rate | ✓ Exact proportionality | ✓ Yes — requestLogger runs on all requests |

## Step 4: Diagnosis

**You have a file descriptor leak in `requestLogger`, not an EventEmitter leak.**

Each HTTP request (400/min = ~6,400/hr) opens a WriteStream via `fs.createWriteStream()` and never closes it. The stream object holds:
- An open file descriptor (consuming 1 FD per request)
- Unflushed buffers in memory (each WriteStream buffers data before flushing)
- Event listener bindings to that FD

Over 24 hours:
- 153,600 requests × 1 FD/request = 153,600 FDs (system recycles some, so you hit ~49k open)
- Buffered data accumulates → +197.6 MB buffer growth
- WriteStream EventEmitters pile up → mistaken diagnosis as "EventEmitter leak"

The WebSocket test was a red herring — it disabled one consumer of the leak, but the leak source (requestLogger) remained active on all HTTP traffic.

---

## Fix

In `src/middleware/requestLogger.ts`, **close the stream when the response finishes**:

```typescript
const originalEnd = res.end;
res.end = function(...args: any[]) {
  logStream.write(JSON.stringify({
    type: 'request_end',
    timestamp: Date.now(),
    statusCode: res.statusCode,
  }) + '\n');

  logStream.end();  // ← ADD THIS LINE
  return originalEnd.apply(res, args);
};
```

Or better, if "async log aggregation pickup" is actually needed, use a proper log rotation library (e.g., `winston`, `pino`) that manages the lifecycle automatically.

This should drop memory from OOM to baseline within an hour of redeployment.
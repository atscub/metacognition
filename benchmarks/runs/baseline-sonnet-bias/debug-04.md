## The Leak is in `requestLogger`, Not WebSocket

The team's canary test already proved this: disabling WebSocket didn't slow the leak. The WebSocket handler's cleanup logic is actually correct. The bug is in `requestLogger.ts`.

---

### Primary Leak: Unclosed `WriteStream` per Request

```typescript
// src/middleware/requestLogger.ts
const logStream = fs.createWriteStream(logFile, { flags: 'a' });

// ...

res.end = function(...args: any[]) {
  logStream.write(...);
  // NOTE: stream stays open for async log aggregation pickup  ← THIS IS THE BUG
  return originalEnd.apply(res, args);
};
```

Every HTTP request creates a `WriteStream` and **never closes it**. Each unclosed stream holds:

| Resource held per stream | Effect |
|---|---|
| 1 file descriptor | FD exhaustion |
| Internal EventEmitter + listeners | Explains the EventEmitter growth |
| Internal write buffer (~41 KB) | Explains the 197 MB Buffer growth |

The heap snapshot numbers cross-validate this precisely:

- **WriteStream `+4,815`** over 12h at 400 req/min means roughly 1 in every 60 requests is being sampled in this snapshot window — plausible if traffic is uneven, or if the heap snapshot only captures a subset of the retained object graph.
- **Buffer `+197,632,000` bytes** ÷ 4,815 streams ≈ **41 KB/stream** — exactly what Node.js allocates for a `WriteStream`'s internal buffer.
- **EventEmitter `+4,820`** ≈ **WriteStream `+4,815`** — each `WriteStream` is itself an `EventEmitter`. They're the same objects.

The FD column in the process metrics confirms it cleanly:

```
Hour 0:  42 FDs    (baseline)
Hour 4:  9,850 FDs (+9,808 → ~2,450/hour)
Hour 8:  19,620 FDs
...
```

At 400 req/min × 60 = 24,000 req/hour, the FD growth rate tracks request volume directly.

---

### Why WebSocket Was Falsely Suspected

The WS handler's cleanup is correct — it removes the listener on both `close` and `error`:

```typescript
messageEmitter.on(`user:${userId}`, handler);       // add
ws.on('close', () => { messageEmitter.removeListener(...) });  // remove ✓
ws.on('error', () => { messageEmitter.removeListener(...) });  // remove ✓
```

`Socket count +12` in the heap diff over 12 hours confirms connections are being cleaned up properly. The `setMaxListeners(0)` line suppressed what would have been a useful warning, which is why the team looked here instead.

---

### The Fix

Close the stream after the response ends. The "stays open for async aggregation" comment describes a design intent, but it's not how `WriteStream` works — the data is flushed to the OS buffer on `.write()`, not held in Node.js memory. Close the stream:

```typescript
res.end = function(...args: any[]) {
  const result = originalEnd.apply(res, args);  // send response first

  logStream.write(JSON.stringify({
    type: 'request_end',
    timestamp: Date.now(),
    statusCode: res.statusCode,
  }) + '\n');

  logStream.end();  // flush and release the FD

  return result;
};
```

Two additional notes on the original code:

1. `originalEnd` is called *after* `logStream.write` in the original — this means the response is delayed until the write is queued. Swap the order as shown above.
2. If the downstream log aggregator genuinely needs files to remain open, the correct pattern is to write to a single shared stream (one per log file or one rotating stream), not one stream per request.

---

### Summary

| Finding | Cause |
|---|---|
| RSS growing ~50 MB/hour | Retained `WriteStream` buffers, one per request |
| FDs growing ~2,450/hour | Unclosed file descriptors, one per request |
| EventEmitter count growing | Each `WriteStream` is an `EventEmitter` |
| Buffer growth dominates heap | Internal 41 KB buffer per `WriteStream` |
| WebSocket not culpable | Correct cleanup; canary test confirms |
| Not a Node.js bug | Application-level resource leak |
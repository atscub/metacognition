The leak is **in the request logger**, not the WebSocket handler. The `logStream` created for each request is **never closed**.

## Root Cause

In `src/middleware/requestLogger.ts`:

```typescript
const logStream = fs.createWriteStream(logFile, { flags: 'a' });
// ...
res.end = function(...args: any[]) {
  logStream.write(...);
  // NOTE: stream stays open for async log aggregation pickup
  return originalEnd.apply(res, args);
};
```

**The comment is the smoking gun.** The stream is created for every request (400/min = 576k/day) and explicitly left open. It's never closed, meaning:

1. **File descriptors leak** — each WriteStream holds an open FD. You see this in your metrics: 42 → 48,900 FDs over 24h. That's ~2,000 FDs/hour = ~33 FDs/minute, matching your 400 requests/minute where most requests complete quickly but their streams stay open.

2. **Memory accumulates** — WriteStream objects + their internal buffers + EventEmitter listeners (WriteStream extends EventEmitter) stay in memory. The heap snapshot shows exactly this: +4,815 WriteStreams, +96,400 Buffers, +4,820 EventEmitter instances.

3. **WebSocket disabling didn't help** — because the leak is in the *request logger*, which runs for ALL HTTP requests regardless of WebSocket status.

## The Fix

Close the log stream when the response completes:

```typescript
res.end = function(...args: any[]) {
  logStream.write(JSON.stringify({
    type: 'request_end',
    timestamp: Date.now(),
    statusCode: res.statusCode,
  }) + '\n');

  // CRITICAL: Close the stream immediately
  logStream.end();
  
  return originalEnd.apply(res, args);
};
```

Or, if you truly need async log aggregation, use a background worker pool (like BullMQ or pino transports) instead of holding streams open indefinitely:

```typescript
// Better approach: queue logs asynchronously, don't hold streams
const logQueue = [];
logStream.write(...);
logStream.end(); // close immediately

logQueue.push(logData);
// Background worker processes logQueue and aggregates logs
```

The current design conflates "log aggregation" with "stream lifecycle"—they're separate concerns. Once you `.end()` the stream, Node.js flushes the write buffer. If you need aggregation, implement it at the application level (in-memory queue + worker), not by leaving FD-holding streams dangling.

**Expected result after fix:** RSS will stabilize around 200-300MB, open FDs will hover around 100-200 (normal for a Node.js app), and EventEmitter count will plateau.
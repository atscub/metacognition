## Root Cause: `requestLogger.ts`, Not the WebSocket Handler

The team is looking at the wrong component. The heap snapshot tells the story clearly:

```
EventEmitter   +4,820
WriteStream    +4,815   ← nearly identical counts
Buffer        +96,400
```

Each `fs.WriteStream` IS an EventEmitter (it inherits from `stream.Writable`). The EventEmitter leak and the WriteStream leak are the **same objects** counted twice under different constructors. And the Buffer growth (~197MB) is write buffers held by those same streams.

### The bug

In `requestLogger.ts`, a new `WriteStream` is created per request and **never closed**:

```typescript
const logStream = fs.createWriteStream(logFile, { flags: 'a' });
// ...
res.end = function(...args: any[]) {
  logStream.write(/* request_end */);
  // ← logStream.end() or logStream.close() is never called
  return originalEnd.apply(res, args);
};
```

The comment `// NOTE: stream stays open for async log aggregation pickup` is the bug dressed as a feature. The stream stays open forever — it holds:
- An open file descriptor
- Internal write buffers (Buffers)
- The EventEmitter machinery itself

At 400 req/min, that's **576,000 unclosed streams per day**.

### Why the FD numbers confirm this

```
Hour  Open FDs
0     42
4     9,850    → +9,808 FDs over 4h
8     19,620   → +9,770 FDs over 4h
```

~9,800 new FDs per 4 hours ≈ ~40/sec sustained growth. The discrepancy from 400 req/min suggests the GC does eventually reclaim some streams (Node's finalizer closes FDs on GC), but it can't keep up under load, so thousands accumulate.

### Why WebSocket was a red herring

The WebSocket handler is actually **correct** — it removes the listener on both `close` and `error`. The `setMaxListeners(0)` was suppressing Node's built-in leak warning (which fires at 11 listeners by default), masking diagnostic output, but the handler logic is sound.

The canary test confirmed it: "disabled WebSocket for 6 hours, memory leak persisted at the same rate." That's definitive. The leak is entirely in the HTTP path.

### Fix

**Option 1 — Close the stream after the response (minimal change):**

```typescript
res.end = function(...args: any[]) {
  logStream.write(JSON.stringify({
    type: 'request_end',
    timestamp: Date.now(),
    statusCode: res.statusCode,
  }) + '\n');

  logStream.end(); // ← add this; flushes and closes the FD

  return originalEnd.apply(res, args);
};
```

**Option 2 — Recommended: use a single shared rotating stream instead of per-request files:**

```typescript
import { createStream } from 'rotating-file-stream'; // or winston/pino

const logStream = createStream('access.log', {
  interval: '1d',
  path: LOG_DIR,
});

export function requestLogger(req: Request, res: Response, next: NextFunction) {
  const requestId = req.headers['x-request-id'] || crypto.randomUUID();
  
  logStream.write(JSON.stringify({
    type: 'request_start',
    requestId,
    // ...
  }) + '\n');

  const originalEnd = res.end;
  res.end = function(...args: any[]) {
    logStream.write(JSON.stringify({
      type: 'request_end',
      requestId,
      statusCode: res.statusCode,
    }) + '\n');
    return originalEnd.apply(res, args);
  };

  next();
}
```

One stream, no per-request allocation, no leak.

### Cleanup item for the WebSocket handler

Remove `messageEmitter.setMaxListeners(0)` — that was suppressing potentially useful warnings. The handler is correct, so you won't see spurious warnings anyway. If you ever introduce a bug there in the future, you want Node to warn you.
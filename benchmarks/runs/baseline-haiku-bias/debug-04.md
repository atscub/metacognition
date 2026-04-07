**The leak is in `src/middleware/requestLogger.ts`** — not the WebSocket handler.

## Root Cause

Every HTTP request creates a `WriteStream` that is **never closed**:

```typescript
const logStream = fs.createWriteStream(logFile, { flags: 'a' });
// ...
res.end = function(...args: any[]) {
  logStream.write(...);
  // ⚠️ Stream never closed here
  return originalEnd.apply(res, args);
};
```

With **400 requests/minute**, you accumulate unclosed streams at this rate:
- **12 hours** = 288,000 requests = 288,000 unclosed WriteStreams
- **24 hours** = 576,000 unclosed WriteStreams

Each WriteStream holds:
- A **file descriptor** (explains your FD leak: 42 → 48,900 over 24h)
- **Internal buffers** (explains +197MB Buffer growth)
- **Event listeners** (explains the EventEmitter growth to +8,420)

## Why the WebSocket test didn't help

You disabled WebSocket *but HTTP request logging stays on*. That 400 req/min is still leaking 6,667 unclosed streams per hour. The leak persists at the same rate because the actual problem wasn't WebSocket at all.

## Fix

Close the stream **after the response finishes**:

```typescript
export function requestLogger(req: Request, res: Response, next: NextFunction) {
  const requestId = req.headers['x-request-id'] || crypto.randomUUID();
  const logFile = path.join(LOG_DIR, `req-${requestId}.log`);
  const logStream = fs.createWriteStream(logFile, { flags: 'a' });

  (req as any).logStream = logStream;

  logStream.write(JSON.stringify({
    type: 'request_start',
    timestamp: Date.now(),
    method: req.method,
    url: req.url,
    headers: req.headers,
  }) + '\n');

  const originalEnd = res.end;
  res.end = function(...args: any[]) {
    logStream.write(JSON.stringify({
      type: 'request_end',
      timestamp: Date.now(),
      statusCode: res.statusCode,
    }) + '\n');

    // ✅ Close the stream—this triggers a 'finish' event and releases all resources
    logStream.end();

    return originalEnd.apply(res, args);
  };

  next();
}
```

Or, if you truly need async log aggregation to happen *after* the response ends, use an event-driven approach instead of leaving streams open:

```typescript
logStream.end(() => {
  // Stream closed safely, now trigger async aggregation
  aggregateLog(logFile);
});
```

This single fix will reclaim all those file descriptors, buffers, and event listeners. The process should stabilize near 200–250MB RSS.
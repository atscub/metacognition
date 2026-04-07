## Reframing First

**Team's framing:** "EventEmitter listener accumulation in the WebSocket handler."

Let me apply three lenses before accepting that.

---

### Lens 1 — The Inversion Lens

What would *guarantee* this leak? A resource that is created on every request but never freed. What creates a resource on every HTTP request? The middleware stack — not just the WebSocket handler.

### Lens 2 — Zoom In on the Numbers

```
Hour  FD growth      Requests at 400/min
0→4   +9,808 FDs    ~96,000 requests
4→8   +9,770 FDs    ~96,000 requests
```

~9,800 new open FDs per 4-hour window. That's ~41 FDs/minute leaking. 400 HTTP req/min with a slow GC cycle is consistent. **WebSocket connections average 200 concurrent / 15-min lifetime = ~13 new connections/minute — nowhere near 41 FDs/minute.**

Also: the heap's biggest single line item is **+96,400 Buffers / +197MB** — that's 87% of total heap growth. Buffers are internal to streams, not to EventEmitter listeners.

### Lens 3 — The Canary Lens (most important)

> "The team disabled the WebSocket feature on a canary instance for 6 hours, but the memory leak persisted at roughly the same rate."

This is a controlled experiment. **It falsifies the WebSocket hypothesis.** The leak exists entirely in the HTTP path, which runs at 400 req/min regardless.

---

## The Actual Leak: `requestLogger.ts`

```typescript
// Creates a new WriteStream on EVERY HTTP request (400/min)
const logStream = fs.createWriteStream(logFile, { flags: 'a' });

// Monkey-patches res.end, but...
res.end = function(...args: any[]) {
  logStream.write(...);
  // ← stream is NEVER closed here
  return originalEnd.apply(res, args);
};

// NOTE: stream stays open for async log aggregation pickup
// ↑ This comment is the bug masquerading as a feature.
```

`logStream` is never `.end()`'d or `.destroy()`'d. The file descriptor stays open until the stream object is garbage-collected **and** the GC finalizer runs. At 400 req/min, creation vastly outpaces cleanup.

### Why this produces exactly the heap diff you see

| Heap entry | Why it grows |
|---|---|
| `WriteStream` +4,815 | Unclosed stream objects accumulating between GC cycles |
| `Buffer` +96,400 / +197MB | Each WriteStream holds internal write buffers; 400 req/min × JSON payload × slow GC |
| `(string)` +48,201 | Log content strings referenced by pending write calls |
| `(array)` +24,100 | Internal stream queue arrays |
| **FDs** 42 → 48,900 | OS file descriptors, 1 per unclosed stream |

The FD count is your smoking gun. OS file descriptors are not garbage-collected — they stay open until explicitly `.close()`'d or the process dies. At hour 20 you have 48,900 open FDs. Most Linux systems default to `ulimit -n 65536`. You're racing toward that ceiling alongside the OOM.

---

## The Fix

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

    // ← ADD THIS: close the stream after the final write completes
    logStream.end();

    return originalEnd.apply(res, args);
  };

  next();
}
```

Call `logStream.end()` (not `.destroy()`) — it flushes the pending write, then closes the FD gracefully. If you need the file to persist for async aggregation, the file still exists on disk after the stream is closed; the aggregator reads the file, not the stream handle.

---

## The WebSocket Handler — Secondary, But Still Broken

The WebSocket code has a subtle bug worth fixing even though it's not the primary leak:

```typescript
ws.on('close', () => {
  messageEmitter.removeListener(`user:${userId}`, handler);
});
ws.on('error', (err) => {
  messageEmitter.removeListener(`user:${userId}`, handler);
});
```

In Node.js, a WebSocket `error` event is **always followed by a `close` event**. The error path calls `removeListener`, then `close` calls it again (harmless, but noisy). More critically: if a connection drops without emitting `error` (clean close, network reset), only `close` fires — which is fine. But `messageEmitter.setMaxListeners(0)` was added specifically to suppress the growing-listener warning, which is a sign someone noticed this accumulating.

The cleaner pattern:

```typescript
wss.on('connection', (ws: WebSocket, req) => {
  const userId = parseUserId(req);

  const handler = (data: any) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  };

  messageEmitter.on(`user:${userId}`, handler);

  // 'close' always fires last, even after 'error'
  ws.once('close', () => {
    messageEmitter.removeListener(`user:${userId}`, handler);
  });
});
```

Remove `setMaxListeners(0)` — it was suppressing a legitimate signal.

---

## Summary

| | WebSocket handler | requestLogger |
|---|---|---|
| **Leak type** | Listener accumulation (secondary) | Unclosed WriteStream / FD leak (primary) |
| **Rate** | ~13 new connections/min | 400 FDs/min |
| **Canary test** | Disabled → leak persisted | Not disabled → still running at full rate |
| **Heap evidence** | +4,820 EventEmitters | +4,815 WriteStreams, +96,400 Buffers (+197MB) |
| **Fix** | Use `once('close', ...)` | Call `logStream.end()` in `res.end` |

Fix `requestLogger.ts` first. The comment "stream stays open for async log aggregation pickup" documents the assumption that caused this — the stream handle and the file are different things; close the handle.
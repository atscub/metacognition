## Reframing Before Diagnosis

**Current framing (the team's):** "EventEmitter listener leak in the WebSocket handler needs better cleanup."

Let me challenge that with three lenses before accepting it.

---

### Lens 1 — The Adversarial Lens: What evidence would *disprove* the WebSocket theory?

> The team disabled WebSocket on a canary for 6 hours. **The leak persisted at the same rate.**

This single data point falsifies the WebSocket hypothesis. If the leak were in `websocket.ts`, removing it should have stopped or dramatically slowed RSS growth. It didn't. The team buried this finding in a footnote and kept suspecting WebSocket anyway. Classic confirmation bias.

---

### Lens 2 — The Zoom In Lens: What does the heap snapshot actually say?

Look at the numbers together:

```
EventEmitter  +4,820
WriteStream   +4,815   ← almost identical count
Buffer        +96,400  ← ~20 buffers per stream
```

`WriteStream` extends `Stream` extends `EventEmitter`. **The EventEmitter growth is the WriteStream growth — they are the same objects.** The team saw "EventEmitter leak" and jumped to WebSocket listeners. But the heap is telling you: you have ~4,800 unclosed file streams.

The FD metric confirms this at the system level:

```
Hour 0:   42 FDs
Hour 4:  9,850 FDs  → +9,808 over 4h = ~40 new FDs/minute
```

File descriptors don't get freed by GC. They require explicit `close()` calls.

---

### Lens 3 — The Zoom Out Lens: What runs on *every request*, not just WebSocket connections?

`requestLogger` middleware. And look at what it does:

```typescript
const logStream = fs.createWriteStream(logFile, { flags: 'a' });
(req as any).logStream = logStream;

res.end = function(...args: any[]) {
  logStream.write(/* ... */);
  // NOTE: stream stays open for async log aggregation pickup
  return originalEnd.apply(res, args);  // ← stream is NEVER closed
};
```

The comment is the smoking gun. This was an intentional design decision — and it is the entire leak.

---

## Root Cause

**`requestLogger.ts` creates one `fs.WriteStream` (= one file descriptor) per HTTP request and never closes it.** At 400 req/min, that's 576,000 leaked FDs over 24 hours. Each stream holds:
- An open file descriptor
- An internal Buffer (the write buffer)
- EventEmitter listener registrations on the stream itself

The reason EventEmitter counts are so high is that `WriteStream` *is* an `EventEmitter`. The team measured the right symptom but misidentified which objects were responsible.

The `messageEmitter.setMaxListeners(0)` in `websocket.ts` is a red herring — it suppresses warnings, which made the symptom slightly less visible, but WebSocket connections are not the source.

---

## Fix

**Don't create a stream per request.** Use a single shared append stream, or use a proper logging library (pino, winston) that manages its own streams.

```typescript
// Option A: shared stream (simplest)
const logStream = fs.createWriteStream(
  path.join(LOG_DIR, 'requests.log'),
  { flags: 'a' }
);

export function requestLogger(req: Request, res: Response, next: NextFunction) {
  const requestId = req.headers['x-request-id'] || crypto.randomUUID();

  logStream.write(JSON.stringify({
    type: 'request_start',
    requestId,
    timestamp: Date.now(),
    method: req.method,
    url: req.url,
  }) + '\n');

  const originalEnd = res.end;
  res.end = function(...args: any[]) {
    logStream.write(JSON.stringify({
      type: 'request_end',
      requestId,
      timestamp: Date.now(),
      statusCode: res.statusCode,
    }) + '\n');
    return originalEnd.apply(res, args);
  };

  next();
}
```

If per-request file isolation is genuinely required by the log aggregation system, close the stream explicitly after the final write:

```typescript
res.end = function(...args: any[]) {
  logStream.write(
    JSON.stringify({ type: 'request_end', ... }) + '\n',
    () => logStream.close()  // close after write drains
  );
  return originalEnd.apply(res, args);
};
```

---

## Secondary: WebSocket handler

The websocket code isn't causing the *observed* leak, but it has a latent issue. If a client disconnects via TCP RST (network partition, sudden kill), neither `close` nor `error` may fire, leaving the `messageEmitter` listener permanently registered. The `setMaxListeners(0)` suppresses the warning that would have surfaced this. Consider adding a heartbeat/ping mechanism with a timeout to force-clean stale connections.

---

## Why the team missed it

1. They anchored on "EventEmitter growth → WebSocket listeners" without checking what *type* of EventEmitter was growing.
2. The canary experiment correctly ruled out WebSocket — but the team didn't update their hypothesis.
3. `setMaxListeners(0)` silenced the one Node.js built-in that could have warned about accumulating listeners on any emitter.
4. The comment `// stream stays open for async log aggregation pickup` made an engineer believe this was correct behavior, not a bug.
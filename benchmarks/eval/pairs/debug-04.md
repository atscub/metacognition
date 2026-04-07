# Task: debug-04 — Memory leak in Node.js service

## Prompt
Our Node.js WebSocket service has a memory leak. RSS grows from ~200MB at startup to
over 1.2GB within 24 hours, at which point the OOM killer terminates it. We took heap
snapshots at startup and after 12 hours. The most suspicious finding is a massive growth
in EventEmitter listeners. Can you identify the leak?

Heap snapshot diff (12h - 0h):

```
=== Heap Snapshot Comparison ===
Constructor           Count Δ    Size Δ (bytes)
─────────────────────────────────────────────
(string)              +48,201    +12,441,600
(array)               +24,100    +8,230,400
EventEmitter          +4,820     +2,892,000
WriteStream           +4,815     +5,778,000
Buffer                +96,400    +197,632,000
Socket                +12        +28,800
IncomingMessage        +8        +14,400
─────────────────────────────────────────────
Total heap growth: ~227 MB over 12 hours
```

The WebSocket handler (src/handlers/websocket.ts) — this is the component the team
suspects because it deals with event listeners:

```typescript
import { WebSocketServer, WebSocket } from 'ws';
import { EventEmitter } from 'events';

const messageEmitter = new EventEmitter();
messageEmitter.setMaxListeners(0); // suppress warnings

export function initWebSocket(server: http.Server) {
  const wss = new WebSocketServer({ server });

  wss.on('connection', (ws: WebSocket, req) => {
    const userId = parseUserId(req);

    const handler = (data: any) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
      }
    };

    messageEmitter.on(`user:${userId}`, handler);

    ws.on('close', () => {
      messageEmitter.removeListener(`user:${userId}`, handler);
      console.log(`WS closed for user ${userId}`);
    });

    ws.on('error', (err) => {
      messageEmitter.removeListener(`user:${userId}`, handler);
      console.error(`WS error for user ${userId}:`, err);
    });
  });
}
```

The request logging middleware (src/middleware/requestLogger.ts):

```typescript
import * as fs from 'fs';
import * as path from 'path';

const LOG_DIR = process.env.LOG_DIR || '/var/log/api';

export function requestLogger(req: Request, res: Response, next: NextFunction) {
  const requestId = req.headers['x-request-id'] || crypto.randomUUID();
  const logFile = path.join(LOG_DIR, `req-${requestId}.log`);

  // Create a dedicated log stream for this request for structured tracing
  const logStream = fs.createWriteStream(logFile, { flags: 'a' });

  // Attach to request for downstream use
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

    // NOTE: stream stays open for async log aggregation pickup
    return originalEnd.apply(res, args);
  };

  next();
}
```

Application startup (src/index.ts):

```typescript
import express from 'express';
import http from 'http';
import { requestLogger } from './middleware/requestLogger';
import { initWebSocket } from './handlers/websocket';

const app = express();
app.use(requestLogger);
// ... other middleware and routes ...

const server = http.createServer(app);
initWebSocket(server);

server.listen(3000, () => {
  console.log('Server running on port 3000');
});
```

Traffic stats: The service handles roughly 400 HTTP requests/minute and maintains
about 200 concurrent WebSocket connections. WebSocket connections have an average
lifetime of 15 minutes.

Process metrics over 24h:

```
Hour  RSS (MB)  Open FDs  EventEmitter listeners
0     198       42        412
4     445       9,850     2,014
8     688       19,620    3,588
12    931       29,410    5,212
16    1,050     39,180    6,830
20    1,180     48,900    8,420
24    OOM killed at ~1,250 MB
```

The team disabled the WebSocket feature on a canary instance for 6 hours, but
the memory leak persisted at roughly the same rate. They're now wondering if it's
a Node.js bug.

What's causing the memory leak?


## Response A
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

## Response B
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

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |

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

## Response B
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

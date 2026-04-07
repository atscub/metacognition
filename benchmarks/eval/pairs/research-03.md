# Task: research-03 — HTTP status code for validation errors

## Prompt
What HTTP status code should our API return when request body validation fails? We're
building a REST API in Node.js (Express) and want to be consistent across all our
endpoints.

For example, if someone POSTs to /api/users with this body:

```json
{
  "name": "",
  "email": "not-an-email",
  "age": -5
}
```

The name is empty (required), the email is malformed, and the age is negative (must
be positive). The JSON itself is syntactically valid — it parses fine — but the values
don't meet our business rules.

We want to return a structured error response like:

```json
{
  "status": "error",
  "errors": [
    {"field": "name", "message": "Name is required"},
    {"field": "email", "message": "Must be a valid email address"},
    {"field": "age", "message": "Must be a positive number"}
  ]
}
```

I've seen different APIs use different codes for this. Stripe uses 400, GitHub uses
422, and some APIs use both for different kinds of validation. What's the correct
status code to use, and why?


## Response A
**Use 422 Unprocessable Entity.**

Here's the distinction:

| Code | Meaning | When to use |
|------|---------|-------------|
| **400** Bad Request | Server can't parse/understand the request | Malformed JSON, missing `Content-Type`, bad URL structure |
| **422** Unprocessable Entity | Request is syntactically valid but semantically wrong | Your case: valid JSON, but values fail business rules |

Your example hits 422 precisely: the server parsed the JSON fine, understood what was being asked, and evaluated the values — they just don't meet validation rules.

**Why not 400?** It's technically correct but imprecise. 400 says "I can't understand this." 422 says "I understood it, but it's wrong." That distinction matters for clients: a 400 might mean retry with different formatting; a 422 means retry with different *values*.

**Why Stripe uses 400:** Pragmatism. They collapsed all client errors into one code to keep their SDK simple. It's a reasonable product decision, not a correctness argument.

**My recommendation:** Use 422 for semantic/business validation, 400 for structural/parse errors. In Express:

```js
// Malformed JSON (let Express handle this)
app.use((err, req, res, next) => {
  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({ status: 'error', message: 'Invalid JSON' });
  }
  next(err);
});

// Business rule validation failures
app.post('/api/users', (req, res) => {
  const errors = validate(req.body);
  if (errors.length) {
    return res.status(422).json({ status: 'error', errors });
  }
  // ...
});
```

The most important thing is **consistency** — pick one and apply it everywhere. 422 is the more defensible choice semantically, and it's what GitHub, Rails, and most modern REST APIs use.

## Response B
## Phase 2–3: What the Research Found

The agent gave detailed findings from RFC 9110 and ecosystem analysis. Here's the synthesis:

---

## The Answer: Use **422** for your case — but 400 is defensible

### What the RFC Actually Says

RFC 9110 (June 2022, the current HTTP standard) defines them precisely:

- **400 Bad Request** — "malformed request syntax, invalid request message framing" — the server *can't parse* the request
- **422 Unprocessable Content** — "syntax of the request content is correct, but it was unable to process the contained instructions" — the server *parsed it fine* but the data is semantically wrong

Your example is textbook 422: valid JSON, invalid values. The RFC's own example uses "well-formed but semantically erroneous" — exactly your situation.

**Note:** RFC 9110 (2022) moved 422 out of WebDAV-only (RFC 4918) into core HTTP semantics, so the old objection "422 is only for WebDAV" is gone.

### Why APIs Disagree

| API | Code | Reason |
|-----|------|--------|
| GitHub, Shopify, Kubernetes | **422** | Semantic precision; Rails heritage |
| Stripe, Google, Twilio | **400** | Predates RFC 9110; "one code for all bad input" |
| NestJS, Fastify (defaults) | **400** | Framework defaults — pragmatic, not principled |

Stripe and Google decided early to use 400 for everything client-side. That's a valid *pragmatic* choice, not a technically correct one per the RFC.

### My Recommendation for Your Express API

**Use 422** — it's the precise answer and your API is new, so you have no legacy to preserve.

Return 400 only for actually malformed JSON (use an error handler for `SyntaxError` from `express.json()`):

```javascript
// express.json() parse error → 400
app.use((err, req, res, next) => {
  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({
      status: 'error',
      errors: [{ field: null, message: 'Request body is not valid JSON' }]
    });
  }
  next(err);
});

// Field validation failure → 422
app.post('/api/users', (req, res) => {
  const errors = validateUser(req.body); // your validation logic
  if (errors.length > 0) {
    return res.status(422).json({ status: 'error', errors });
  }
  // ...
});
```

### Decision Summary

| Scenario | Code | Why |
|----------|------|-----|
| Unparseable JSON (`{"name": "Jo` truncated) | **400** | Syntax error — can't read the body |
| Valid JSON, empty required field | **422** | RFC 9110 §15.5.20 — semantically invalid |
| Valid JSON, bad email format | **422** | Same |
| Valid JSON, negative age | **422** | Same |

Your exact response structure is good. Just set the HTTP status to 422.

One caveat: **be consistent.** The worst outcome is some endpoints returning 400 and others 422 for the same class of error. Pick one policy and enforce it in shared middleware.

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

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
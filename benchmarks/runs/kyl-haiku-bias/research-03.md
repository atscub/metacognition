I don't have permission to search the web currently. Let me provide you with the answer based on established standards and real-world practice, with caveats about what I can't verify:

## Phase 2-3: Synthesize Current Knowledge

**The RFC perspective:**

- **RFC 7231** (HTTP Semantics) defines both 400 and 422:
  - **400 Bad Request**: "The server cannot or will not process the request due to something that is perceived as a client error"
  - **422 Unprocessable Entity** (RFC 4918, WebDAV): "The request entity has a content type which the server does not understand" OR "the request entity contains semantic errors"

- **RFC 7807** (Problem Details for HTTP APIs) doesn't mandate a specific code — it's orthogonal to status code choice. It's a standard JSON error format that wraps whatever status you choose.

**Real-world conventions (from my training knowledge):**

| API | Syntax Error | Value Validation | Preference |
|-----|---|---|---|
| **Stripe** | 400 | 400 | Always 400 |
| **GitHub** | 422 | 422 | Prefers 422 for validation |
| **AWS** | 400 | 400 | Defaults to 400 |
| **JSON:API** | 400 | 400 | Standard recommends 400 |

## The Consensus (Best Practice for Your Case)

**Use 400 Bad Request** for your scenario. Here's why:

1. **RFC 7231 supports it** — 400 covers both syntax and semantic validation failures
2. **Majority of APIs use 400** — Stripe, AWS, most mainstream services standardize on 400
3. **Simpler client-side handling** — Clients expect 400 for any invalid request
4. **422 is more specialized** — Originally WebDAV; GitHub uses it but it's not standard practice
5. **Reduces status code proliferation** — Keep your API simple with one error code

## What Your Error Response Should Include

The status code matters less than having a **well-structured error response**. Your format is good:

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

**To make it RFC 7807 compliant, add:**

```json
{
  "type": "https://yourapi.example.com/errors/validation-failed",
  "title": "Validation Failed",
  "status": 400,
  "detail": "Request body contains validation errors",
  "errors": [
    {"field": "name", "message": "Name is required"},
    {"field": "email", "message": "Must be a valid email address"},
    {"field": "age", "message": "Must be a positive number"}
  ]
}
```

## Express Implementation

```javascript
app.post('/api/users', (req, res) => {
  const errors = [];
  
  if (!req.body.name?.trim()) {
    errors.push({ field: 'name', message: 'Name is required' });
  }
  if (!isValidEmail(req.body.email)) {
    errors.push({ field: 'email', message: 'Must be a valid email address' });
  }
  if (req.body.age < 0) {
    errors.push({ field: 'age', message: 'Must be a positive number' });
  }
  
  if (errors.length > 0) {
    return res.status(400).json({
      type: 'https://yourapi.example.com/errors/validation-failed',
      title: 'Validation Failed',
      status: 400,
      detail: 'Request body contains validation errors',
      errors
    });
  }
  
  // Process valid request...
});
```

## Key Takeaway

**Use 400 for input validation.** Distinguish between error codes based on problem type:
- **400** — Client sent something invalid (malformed JSON, failed validation, missing fields)
- **401** — Authentication required
- **403** — Authenticated but not authorized
- **422** — Only if you specifically want to signal semantic (vs. syntactic) validation for some reason (rare)

This keeps your API simple and predictable for clients.
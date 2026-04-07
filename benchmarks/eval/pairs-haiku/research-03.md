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
I don't have web search permission enabled, so I can't fetch the latest discussions. But I can work from the RFC definitions (which are stable) and industry patterns I'm confident about. Let me provide a structured answer:

## Phase 2–3: What the RFCs Say + Current Industry Practice

**RFC 7231 (HTTP/1.1 Semantics) defines 400:**
> The server cannot or will not process the request due to something that is perceived to be a client error (e.g., malformed request syntax, invalid request message framing, or deceptive request routing).

**RFC 4918 (WebDAV) introduces 422:**
> The request entity has a media type which the server or resource does not understand... The entity of the response contains specific information about why the request was unprocessable.

**The semantic distinction:**
- **400** = The request itself is malformed or unparseable (syntactic problem)
  - Malformed JSON: `{"name": "}`
  - Missing content-type header
  - Invalid HTTP structure
- **422** = The request parses fine, but the *values* violate business logic (semantic problem)
  - JSON is valid, but email field doesn't match email regex
  - Required field is missing or empty
  - Value is outside allowed range

**Your example fits 422 perfectly**: the JSON parses fine, but the *values* don't meet your business rules.

---

## The Current Industry Split

**422 advocates** (GitHub, JSON:API spec, REST best practice guides):
- Clearer semantics: "I understood your request structure, but the values are invalid"
- Easier for clients to distinguish: "is this a syntax problem I need to fix, or a validation problem?"
- More specific HTTP semantics

**400 advocates** (Stripe, some legacy APIs):
- Simpler: "something's wrong with your request, check the error details"
- 422 is less well-known; some clients don't handle it
- "Validation error" is a type of "bad request"

---

## Phase 4: Validation

I can't run an experiment without implementing an API, but I can point you to what you can verify:

1. **Check Stripe's actual behavior** — POST invalid data and observe the status code (they claim 400, worth verifying)
2. **Check GitHub API v3 docs** — They document 422 for validation errors [in their API documentation](https://docs.github.com/en/rest/overview/resources-in-the-rest-api?apiVersion=2022-11-28#client-errors)

---

## My Recommendation for Your API

**Use 422 Unprocessable Entity.**

**Why:**
1. **Semantically correct** — the JSON is valid, the values aren't
2. **Clearer for clients** — they can distinguish parsing errors (400) from validation errors (422)
3. **Future-proof** — aligns with REST best practices and JSON:API spec
4. **Your error structure supports it** — you're already returning detailed field-level errors, which is the whole point of 422

**Implementation in Express:**
```javascript
app.post('/api/users', (req, res) => {
  const errors = validateUser(req.body); // your validation logic
  
  if (errors.length > 0) {
    return res.status(422).json({
      status: 'error',
      errors: errors
    });
  }
  
  // ... create user
});
```

**When to use 400 instead:**
- Actual JSON parsing fails (Express handles this automatically)
- Invalid request structure (missing required headers, wrong content-type)
- Invalid request line (HTTP layer issue)

---

## Phase 5: Persistence

This is stable HTTP semantics, not something that needs to be persisted as it won't change. The value of this conversation is the decision rationale (why you picked 422) rather than the fact itself.

**Suggested next step:** Document this choice in your API style guide or code comments so future developers understand why you chose 422 over 400.

## Response B
**Use 422 Unprocessable Entity** for validation failures—it's the semantically correct choice.

Here's why:

| Status | Meaning | Your Case |
|--------|---------|-----------|
| **400 Bad Request** | Request is malformed or unparseable | ❌ Not your case (JSON parses fine) |
| **422 Unprocessable Entity** | Request is well-formed but fails business validation | ✅ Exactly your case |

**The distinction matters:**
- **400** = "I can't understand your request" (syntax/format errors)
- **422** = "I understand your request, but it violates business rules" (semantic errors)

Your JSON is syntactically valid, so 422 is more accurate.

## Why this matters for consistency:

1. **Clients can distinguish error types programmatically**
   - 400 → retry with different format/structure
   - 422 → retry with different values
   
2. **Industry standard** 
   - JSON:API spec recommends 422
   - GitHub uses 422
   - This is the REST best practice

3. **Future-proofs your API**
   - If you later add actual syntax validation (malformed JSON), you can use 400 for that
   - Keeps the two failure modes separate

## Practical implementation in Express:

```javascript
app.post('/api/users', (req, res) => {
  const errors = [];
  
  if (!req.body.name) {
    errors.push({ field: 'name', message: 'Name is required' });
  }
  if (!isValidEmail(req.body.email)) {
    errors.push({ field: 'email', message: 'Must be a valid email address' });
  }
  if (req.body.age < 0) {
    errors.push({ field: 'age', message: 'Must be a positive number' });
  }
  
  if (errors.length > 0) {
    return res.status(422).json({
      status: 'error',
      errors
    });
  }
  
  // Process valid request...
});
```

**Why not 400?** It's not *wrong*—Stripe uses it—but 422 is more explicit and becoming the convention. Pick one and be consistent everywhere.

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

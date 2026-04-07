Web search isn't available in this session, so I'll work from primary source knowledge — but I'll be explicit about my confidence level and what you should verify.

---

## Phase 2–3: What the RFCs Actually Say

**The critical update: RFC 9110 (June 2022)**

This replaced RFC 7231 and made a change that directly answers your question: **422 was promoted from WebDAV-only (RFC 4918) into the base HTTP spec.** That matters.

RFC 9110 §15.5.1 — `400 Bad Request`:
> Indicates the server cannot or will not process the request due to something perceived as a client error (e.g., malformed request syntax, invalid message framing...)

RFC 9110 §15.5.21 — `422 Unprocessable Content`:
> Indicates the server understands the content type and **the syntax is correct**, but it was unable to process the contained instructions.

The spec draws a clean line:
- **400** = the request itself is broken (unparseable JSON, wrong Content-Type, malformed headers)
- **422** = the request is syntactically valid but semantically wrong

Your example — valid JSON that parses fine, but values violate rules — is the textbook 422 case.

---

## Phase 4: Why Sources Disagree

This is the important part. Stripe uses 400. GitHub uses 422. Both are deliberate choices, not mistakes. Here's why:

**The case for 400 (Stripe's approach):**
- Simpler: one code for "your request was bad, fix it"
- Pre-2022, 422 was technically a WebDAV extension — some clients didn't handle it well
- Stripe's API predates RFC 9110 and they've stayed consistent for compatibility

**The case for 422 (GitHub's approach, RFC-aligned):**
- Semantically precise: lets you distinguish "can't parse this" from "parsed it but values are wrong"
- RFC 9110 now puts 422 in core HTTP — the WebDAV-only objection is gone
- Enables different client handling: a 400 might mean "retry with correct content-type", a 422 means "fix your data"

---

## Phase 5: The Right Answer for Your Situation

**Use 422 for field validation failures.** Here's the breakdown:

| Scenario | Code | Reason |
|---|---|---|
| Malformed JSON (can't parse) | `400` | Syntax error — the request is broken |
| Wrong Content-Type | `415` | Different problem entirely |
| Missing required field | `422` | Valid JSON, bad semantics |
| Invalid format (bad email) | `422` | Valid JSON, failed validation |
| Value out of range (age -5) | `422` | Valid JSON, failed business rule |

Your response body is already structured correctly for 422. The combination of a structured `errors` array with `field` + `message` pairs is exactly what 422 is designed to carry.

**In Express:**

```js
// Validation middleware
function validateUser(req, res, next) {
  const errors = [];

  if (!req.body.name?.trim()) {
    errors.push({ field: "name", message: "Name is required" });
  }
  if (!isValidEmail(req.body.email)) {
    errors.push({ field: "email", message: "Must be a valid email address" });
  }
  if (!Number.isInteger(req.body.age) || req.body.age < 1) {
    errors.push({ field: "age", message: "Must be a positive number" });
  }

  if (errors.length > 0) {
    return res.status(422).json({ status: "error", errors });
  }
  next();
}

// Separate handler for malformed JSON (syntax error → 400)
app.use((err, req, res, next) => {
  if (err.type === "entity.parse.failed") {
    return res.status(400).json({
      status: "error",
      errors: [{ field: null, message: "Request body is not valid JSON" }]
    });
  }
  next(err);
});
```

**The one consistency rule that matters most:** Use 400 for JSON parse failures and 422 for validation failures — and never swap them. Your clients can then write:

```js
if (res.status === 400) // something is structurally wrong with my request
if (res.status === 422) // I can show field errors to the user
```

---

## Caveats

- I couldn't run web searches to verify RFC 9110's exact wording — I'm working from training knowledge. Read [RFC 9110 §15.5.21](https://www.rfc-editor.org/rfc/rfc9110#section-15.5.21) directly to confirm.
- If you're building a public API that other teams will consume and they already expect Stripe-style 400s, consistency with your ecosystem may outweigh RFC precision.
- Neither choice is wrong. The structured error body matters more than the status code.
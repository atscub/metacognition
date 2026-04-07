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
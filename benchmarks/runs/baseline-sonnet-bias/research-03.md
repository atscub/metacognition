**Use 422 for this case.** Here's why, and when to use each:

## The distinction

| Code | Meaning | Example |
|------|---------|---------|
| **400** Bad Request | Malformed request — server can't parse it | Invalid JSON syntax, missing `Content-Type` header |
| **422** Unprocessable Entity | Well-formed but semantically invalid | Valid JSON, but values fail business rules |

Your example is exactly what 422 was designed for: the JSON parsed fine, but the *content* is invalid. RFC 4918 defines 422 as: "the server understands the content type... the syntax is correct, but was unable to process the contained instructions."

## Why Stripe uses 400

Stripe collapses both into 400 for simplicity — their clients only need to check one code for "something's wrong with your request." That's a pragmatic choice, not a semantic one. GitHub's 422 for validation is more precise.

## Recommended approach for Express

Use **both**, consistently:

- `400` — request can't be parsed (bad JSON, wrong `Content-Type`)
- `422` — request parsed but failed validation

```js
// Middleware: malformed JSON → 400
app.use((err, req, res, next) => {
  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({ status: 'error', message: 'Invalid JSON' });
  }
  next(err);
});

// Route: valid JSON, invalid values → 422
app.post('/api/users', (req, res) => {
  const errors = validate(req.body);
  if (errors.length) {
    return res.status(422).json({ status: 'error', errors });
  }
  // ...
});
```

## Bottom line

Pick one and document it. The error body (your `errors` array with field-level messages) matters more to API consumers than whether it's 400 or 422. But if you want semantic correctness: **422 for validation failures, 400 for malformed requests**.
The best practice is **422 Unprocessable Entity** for your use case, though 400 Bad Request is also defensible depending on how you categorize validation errors. Let me explain the distinction:

## HTTP Status Codes for Validation

| Status | When to use | Your example |
|--------|------------|--------------|
| **400 Bad Request** | Request is malformed or unparseable (invalid JSON, wrong syntax, missing required structure) | Invalid JSON, type mismatch in schema |
| **422 Unprocessable Entity** | Request is well-formed but contains semantic errors (values violate business rules) | Your exact example ✓ |

## Why 422 for Your Case

Your request body is **syntactically valid** — the JSON parses perfectly and has the right structure. The errors are in the **values** themselves (empty string when non-empty required, invalid email format, negative number). This is exactly what 422 was designed for.

**422 signals:** "I understood your request, the structure is correct, but the values don't make sense for my business logic."

**400 signals:** "I can't even parse or understand what you sent."

## How Major APIs Handle This

- **GitHub**: Uses 422 for validation errors (unprocessable entity)
- **Stripe**: Uses 400 broadly, but includes error codes (`invalid_request_error`, `invalid_param`) to distinguish different failure types
- **Heroku, Shopify, Twilio**: All use 422 for semantic validation failures

Stripe's approach is pragmatic — they use 400 but compensate with detailed error codes in the response. Your structured error response format is ideal for this.

## Recommendation

**Use 422 as your primary status code** with your structured error response. Here's why:

1. **Semantically correct** — REST standards align with 422 for this scenario
2. **Client-friendly** — makes it easy for API consumers to differentiate between "request malformed" vs. "values invalid"
3. **Consistency** — matches industry leaders (GitHub, Shopify)
4. **Future-proof** — if you add structural validation later (malformed JSON, type mismatches), you can use 400 for those

### Express Example

```javascript
router.post('/api/users', (req, res) => {
  const errors = [];
  
  if (!req.body.name?.trim()) {
    errors.push({ field: 'name', message: 'Name is required' });
  }
  if (!isValidEmail(req.body.email)) {
    errors.push({ field: 'email', message: 'Must be a valid email address' });
  }
  if (req.body.age == null || req.body.age < 0) {
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

**Note:** For actual malformed JSON (can't parse), Express will error before your handler runs — that naturally returns 400.
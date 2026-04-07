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
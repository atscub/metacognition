The three approaches aren't competing — they solve different problems and you should use all three together. Here's the breakdown:

## The pattern for library errors

```go
// sentinel errors: for condition checking with errors.Is()
var (
    ErrNotFound     = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
    ErrRateLimited  = errors.New("rate limited")
)

// custom type: for structured data extraction with errors.As()
type APIError struct {
    StatusCode int
    Message    string
    RequestID  string
    Err        error // wraps the sentinel
}

func (e *APIError) Error() string {
    return fmt.Sprintf("payment API: %s (status=%d, request_id=%s)",
        e.Message, e.StatusCode, e.RequestID)
}

// Unwrap makes errors.Is() and errors.As() traverse the chain
func (e *APIError) Unwrap() error { return e.Err }
```

Construct errors by wrapping the sentinel inside the structured type:

```go
func (c *Client) GetUser(ctx context.Context, id string) (*User, error) {
    resp, err := c.do(ctx, "GET", "/users/"+id)
    if err != nil {
        return nil, fmt.Errorf("GetUser %s: %w", id, err) // wrap transport errors
    }
    switch resp.StatusCode {
    case 404:
        return nil, &APIError{
            StatusCode: 404,
            Message:    "user not found",
            RequestID:  resp.Header.Get("X-Request-ID"),
            Err:        ErrNotFound, // sentinel lives inside the struct
        }
    case 429:
        return nil, &APIError{StatusCode: 429, ..., Err: ErrRateLimited}
    }
    ...
}
```

## Why this works for all three requirements

**Requirement 1 — condition checking:** `errors.Is` walks the chain via `Unwrap()`, so this works even if the caller's code further wraps the error:

```go
user, err := client.GetUser(ctx, id)
if errors.Is(err, payment.ErrNotFound) {
    // create the user instead
}
```

**Requirement 2 — structured data extraction:** `errors.As` also walks the chain:

```go
var apiErr *payment.APIError
if errors.As(err, &apiErr) {
    log.Printf("request %s failed with status %d", apiErr.RequestID, apiErr.StatusCode)
}
```

**Requirement 3 — context about origin:** Use `fmt.Errorf` with `%w` at each call site as you bubble up. This builds a readable chain:

```go
// inside your library:
return nil, fmt.Errorf("GetUser %s: %w", id, apiErr)

// caller sees:
// "GetUser abc123: payment API: user not found (status=404, request_id=req-xyz)"
```

## On `pkg/errors`

Skip it. Since Go 1.13, `%w` + `errors.Is`/`errors.As` covers everything `pkg/errors` adds except stack traces. Stack traces have runtime overhead and don't compose cleanly across library boundaries. Your `RequestID` is far more actionable for support cases than a stack trace anyway.

## One thing to avoid

Don't export `APIError` as a value — always use a pointer receiver and return `*APIError`. This matters because `errors.As` uses reflection and a nil interface value of type `*APIError` still satisfies `error`, which causes subtle bugs if you return it by value.

```go
// Bad: this hides errors.As matching
func makeErr() error { return APIError{...} }

// Good
func makeErr() error { return &APIError{...} }
```

## Summary

| Mechanism | Purpose |
|-----------|---------|
| Sentinel vars (`ErrNotFound`) | Condition identity — `errors.Is()` |
| Custom struct (`*APIError`) | Structured data — `errors.As()` |
| `fmt.Errorf("ctx: %w", err)` | Call chain context — readable messages |

The `Unwrap() error` method on your struct is the glue that connects all three.
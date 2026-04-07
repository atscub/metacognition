These approaches aren't competing — they solve different problems and compose together. Use all three.

## The unified pattern

```go
// 1. Sentinel errors — for kind checking with errors.Is
var (
    ErrNotFound     = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
    ErrRateLimited  = errors.New("rate limited")
)

// 2. Rich error type — for structured data extraction with errors.As
type APIError struct {
    StatusCode int
    Message    string
    RequestID  string
    Err        error // wraps the sentinel
}

func (e *APIError) Error() string {
    return fmt.Sprintf("%s (status=%d, request_id=%s)", e.Message, e.StatusCode, e.RequestID)
}

// Unwrap enables errors.Is and errors.As to traverse the chain
func (e *APIError) Unwrap() error { return e.Err }
```

**Constructing errors at the HTTP layer:**

```go
func parseResponse(resp *http.Response) error {
    switch resp.StatusCode {
    case 404:
        return &APIError{StatusCode: 404, Message: "resource not found",
            RequestID: resp.Header.Get("X-Request-ID"), Err: ErrNotFound}
    case 401:
        return &APIError{StatusCode: 401, Message: "unauthorized",
            RequestID: resp.Header.Get("X-Request-ID"), Err: ErrUnauthorized}
    case 429:
        return &APIError{StatusCode: 429, Message: "rate limit exceeded",
            RequestID: resp.Header.Get("X-Request-ID"), Err: ErrRateLimited}
    }
    return nil
}
```

**3. `fmt.Errorf` with `%w` — for adding call-site context as the error travels up:**

```go
func (c *Client) GetUser(ctx context.Context, id string) (*User, error) {
    resp, err := c.fetch(ctx, "/users/"+id)
    if err != nil {
        return nil, fmt.Errorf("GetUser %q: %w", id, err)
    }
    // ...
}
```

## What your consumers get

```go
err := client.GetUser(ctx, "u_123")

// Requirement 1: check specific condition — works through the fmt.Errorf wrap
if errors.Is(err, ErrNotFound) {
    // handle 404
}

// Requirement 2: extract structured data
var apiErr *APIError
if errors.As(err, &apiErr) {
    log.Printf("contact support with request_id=%s", apiErr.RequestID)
}

// Requirement 3: origin context — the error message itself
// "GetUser \"u_123\": resource not found (status=404, request_id=req_abc)"
log.Println(err)
```

`errors.Is` and `errors.As` both traverse `Unwrap()` chains, so wrapping with `%w` doesn't break kind-checking or data extraction.

## On `pkg/errors`

Skip it for a library. Since Go 1.13 (`%w`) you don't need it. Adding it as a library dependency forces it on all your consumers. If callers need stack traces, they can use `pkg/errors` or `golang.org/x/xerrors` themselves — your job is to give them enough context in the error message string and structured fields.

## The rule of thumb

| Technique | Purpose |
|---|---|
| Sentinel vars | Let callers branch on error kind |
| Custom type with `Unwrap` | Let callers extract structured fields |
| `fmt.Errorf("op %v: %w", ...)` | Add call context without losing the above |

Define sentinels and your error type in your package's public API. Use `%w` wrapping internally as errors move up the stack.
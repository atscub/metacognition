For Go 1.21, the answer is **combine custom error types with error wrapping** — this handles all three requirements elegantly. Forget `pkg/errors` (the standard library does what it did now) and don't use plain sentinel errors exclusively (they're too coarse-grained for structured data).

Here's what I'd recommend:

## Define custom error types (not sentinels)

```go
type APIError struct {
    StatusCode int
    Message    string
    RequestID  string
    Err        error // wrapped underlying error
}

func (e *APIError) Error() string {
    return e.Message
}

func (e *APIError) Unwrap() error {
    return e.Err
}

// Optional: implement Is() for condition checking without extra sentinel vars
func (e *APIError) Is(target error) bool {
    t, ok := target.(*APIError)
    if !ok {
        return false
    }
    // Match on status code if comparing with a template
    return e.StatusCode == t.StatusCode
}
```

## Check conditions with errors.Is() / errors.As()

```go
resp, err := client.GetUser(ctx, "user123")
if err != nil {
    var apiErr *APIError
    if errors.As(err, &apiErr) {
        // You have structured data
        if apiErr.StatusCode == http.StatusNotFound {
            // Handle not found
        } else if apiErr.StatusCode == http.StatusTooManyRequests {
            // Handle rate limit
        }
        // Log with request ID for support
        log.Printf("API error (request %s): %v", apiErr.RequestID, apiErr.Message)
    }
    return err
}
```

## Wrap errors at library boundaries

```go
func (c *Client) GetUser(ctx context.Context, id string) (*User, error) {
    req, _ := http.NewRequestWithContext(ctx, "GET", c.baseURL+"/users/"+id, nil)
    resp, err := c.http.Do(req)
    if err != nil {
        // Wrap low-level errors with context (no APIError yet, just networking)
        return nil, fmt.Errorf("http request failed: %w", err)
    }
    
    if resp.StatusCode >= 400 {
        body, _ := io.ReadAll(resp.Body)
        return nil, &APIError{
            StatusCode: resp.StatusCode,
            Message:    string(body),
            RequestID:  resp.Header.Get("X-Request-ID"),
            Err:        fmt.Errorf("http %d", resp.StatusCode),
        }
    }
    
    var user User
    if err := json.NewDecoder(resp.Body).Decode(&user); err != nil {
        return nil, fmt.Errorf("failed to decode user response: %w", err)
    }
    return &user, nil
}
```

## Why this works

| Requirement | How it's met |
|---|---|
| Check specific conditions | `errors.As()` + status code check, or add a `Kind` field if conditions don't map to HTTP codes |
| Extract structured data | Custom type has `StatusCode`, `RequestID`, etc. Client calls `As()` to access them |
| Contextual debugging | `%w` wrapping preserves the error chain; callers can inspect `Err` field or use `errors.Unwrap()` |

## Notes

- **Skip pkg/errors**: Go 1.13+ made it redundant. If you *really* need stack traces, add a `Stack` field to `APIError` and capture it at error creation time — but honestly, structured logging (with caller info) is better for libraries.
- **Sentinel errors are optional**: You don't need `var ErrNotFound = errors.New(...)` if your custom type carries the status code. You can always add a helper if needed: `func IsNotFound(err error) bool { var ae *APIError; return errors.As(err, &ae) && ae.StatusCode == 404 }`.
- **Embed custom error types in others**: If some errors are retriable and others aren't, extend `APIError` or add a `Retriable() bool` method.

This approach scales well: consumers get type safety + structured data, the error chain is preserved for debugging, and you're using only the standard library.
You're right that there's conflicting advice—it's because Go's error handling has evolved. The good news: for your Go 1.21+ library with those requirements, there's a clear modern answer.

**Use custom error types + `fmt.Errorf` with `%w` wrapping.** This is idiomatic Go 1.13+ and handles all three of your requirements.

Here's the pattern:

```go
// Define custom error types for conditions you need to distinguish
type APIError struct {
    StatusCode int
    Message    string
    RequestID  string
}

func (e *APIError) Error() string {
    return e.Message
}

// Optional: implement Is() for custom matching logic
func (e *APIError) Is(target error) bool {
    t, ok := target.(*APIError)
    if !ok {
        return false
    }
    // Match on status code ranges if useful
    return e.StatusCode == t.StatusCode
}

// In your API client:
func (c *Client) GetUser(ctx context.Context, id string) (*User, error) {
    resp, err := c.http.Get(ctx, "/users/"+id)
    if err != nil {
        // Wrap network errors with context
        return nil, fmt.Errorf("failed to fetch user %s: %w", id, err)
    }
    
    if resp.StatusCode == 404 {
        // Return structured error
        return nil, &APIError{
            StatusCode: 404,
            Message:    "user not found",
            RequestID:  resp.Header.Get("X-Request-ID"),
        }
    }
    
    // ... parse response
}
```

**How consumers check errors:**

```go
// Exact type checking (works with custom types)
var apiErr *APIError
if errors.As(err, &apiErr) {
    log.Printf("API error: status=%d, request_id=%s", 
        apiErr.StatusCode, apiErr.RequestID)
}

// Condition checking (works with errors.Is())
if errors.Is(err, context.DeadlineExceeded) {
    // timeout handling
}

// Wrapping chain inspection
fmt.Println(err)  // Full chain with all wrapped context
```

**Why this approach:**

1. ✅ **Specific conditions**: `errors.As()` lets consumers type-assert to your custom error type
2. ✅ **Structured data**: The struct holds StatusCode, RequestID, etc.
3. ✅ **Debugging context**: `fmt.Errorf(...%w...)` preserves the error chain, and callers can see the full stack of what happened (network error → wrapped as APIError → wrapped again at call site)

**On stack traces:** Don't use `pkg/errors` for Go 1.21. Modern Go convention is to let **logging frameworks** (like `slog`) add context, not to embed traces in errors. If you need debugging info, include it in the error message or custom fields. Stacks are the logger's job, not the error's job.

**One pattern to avoid mixing:** Don't use sentinel errors AND custom types for the same conditions. Pick one.

```go
// DON'T do this:
var ErrNotFound = errors.New("not found")
type APIError struct { StatusCode int; ... }

// Because then consumers need multiple checks:
// if err == ErrNotFound || errors.As(err, &APIError) { ... }
// Pick one style per error condition.

// DO pick one:
// Either: return fmt.Errorf("not found: %w", someErr)  [simple]
// Or: return &APIError{StatusCode: 404, ...}  [structured]
```

**Minimal example for your library:**

```go
package payment

import (
    "errors"
    "fmt"
)

// Only define this for errors that need structured data or special handling
type PaymentError struct {
    Code      string // "not_found", "rate_limited", "invalid_request"
    StatusCode int
    RequestID  string
    Err       error // underlying error
}

func (e *PaymentError) Error() string {
    return fmt.Sprintf("payment error (%s): %v", e.Code, e.Err)
}

func (e *PaymentError) Unwrap() error {
    return e.Err
}

// Consumer code:
func processPayment(client *Client, id string) error {
    err := client.Process(id)
    
    var pe *PaymentError
    if errors.As(err, &pe) {
        if pe.Code == "rate_limited" {
            return fmt.Errorf("retrying: %w", err)
        }
        log.Printf("Support ticket ID: %s", pe.RequestID)
    }
    
    return err
}
```

This scales well: add error types as you discover conditions that *need* structured data, keep simple errors as `fmt.Errorf` wraps, and consumers get both discoverability (via `errors.As()`) and context (via the error message chain).
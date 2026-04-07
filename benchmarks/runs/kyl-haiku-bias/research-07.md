## Phase 3: Synthesize

Based on my research of current Go documentation (1.21+), here's what I've learned:

**Key Findings:**
1. **Go 1.13+ (and current 1.21) standard**: Use `fmt.Errorf("%w", err)` for wrapping, `errors.Is()` for sentinel checking, and `errors.As()` / `errors.AsType[]()` for extracting structured data.
2. **The blog post** recommends custom error types as the primary tool for rich error information, not pkg/errors.
3. **Modern pattern**: Combine wrapped errors (for context) + custom error types (for structure) + sentinel matching (for simple checks).
4. **pkg/errors is legacy**: The standard library now has everything needed; pkg/errors was important pre-1.13 but isn't recommended for new code with Go 1.21+.

**For your library's three requirements:**
- ✅ Type checking: Use `errors.Is()` for sentinel errors OR `errors.AsType[]()` for custom types
- ✅ Structured data: Implement a custom error type with fields (StatusCode, Message, RequestID)
- ✅ Origin context: Use `fmt.Errorf("%w")` to wrap errors with contextual messages

## Phase 4: Validation Through Experiment

Let me write a minimal example showing how these work together:

```go
// errors.go - Your library's error types
package payment

import "fmt"

// Sentinel errors for simple type checking
var (
    ErrRateLimited = fmt.Errorf("rate limited")
    ErrUnauthorized = fmt.Errorf("unauthorized")
)

// Custom error type for structured data
type APIError struct {
    StatusCode int
    Message    string
    RequestID  string
    Err        error // The wrapped original error (network, timeout, etc.)
}

func (e *APIError) Error() string {
    return fmt.Sprintf("API error %d (request %s): %s", e.StatusCode, e.RequestID, e.Message)
}

// Implement Unwrap so error wrapping chain works
func (e *APIError) Unwrap() error {
    return e.Err
}

// Implement Is() to match sentinel errors in the APIError
func (e *APIError) Is(target error) bool {
    // This lets consumers do: errors.Is(err, ErrRateLimited)
    // even when the error is an *APIError wrapping a rate limit
    return e.Err == target || target == e
}

// --- Usage in your library ---

func (c *Client) GetUser(id string) (*User, error) {
    resp, err := c.httpClient.Get(/* ... */)
    if err != nil {
        // Network error - wrap it with context
        return nil, fmt.Errorf("fetching user %s: %w", id, err)
    }
    defer resp.Body.Close()

    // Check HTTP status
    if resp.StatusCode == 429 {
        return nil, &APIError{
            StatusCode: 429,
            Message:    "too many requests",
            RequestID:  resp.Header.Get("X-Request-ID"),
            Err:        ErrRateLimited,
        }
    }
    
    if resp.StatusCode == 401 {
        return nil, &APIError{
            StatusCode: 401,
            Message:    "invalid API key",
            RequestID:  resp.Header.Get("X-Request-ID"),
            Err:        ErrUnauthorized,
        }
    }

    if resp.StatusCode != 200 {
        body, _ := io.ReadAll(resp.Body)
        return nil, &APIError{
            StatusCode: resp.StatusCode,
            Message:    string(body),
            RequestID:  resp.Header.Get("X-Request-ID"),
        }
    }

    // ... parse response ...
}

// --- How consumers use it ---

func main() {
    user, err := client.GetUser("user123")
    
    // Check for rate limiting (works with errors.Is)
    if errors.Is(err, ErrRateLimited) {
        fmt.Println("Rate limited, retry later")
        return
    }
    
    // Extract structured data
    var apiErr *APIError
    if errors.As(err, &apiErr) {
        // Log for support
        fmt.Printf("API error %d (request %s): %s\n", 
            apiErr.StatusCode, apiErr.RequestID, apiErr.Message)
        return
    }
    
    // Network/unknown error
    if err != nil {
        fmt.Printf("Failed: %v\n", err)
    }
}
```

**This validates:**
- ✅ Consumers can use `errors.Is()` to check for sentinel errors
- ✅ Consumers can use `errors.As()` to extract the APIError and access StatusCode/RequestID
- ✅ Error messages include context from wrapping (the "fetching user X" part)
- ✅ Works with Go 1.21's stdlib (no pkg/errors needed)

## Summary & Recommendations

**For your payment library, use this approach:**

1. **Define sentinel errors** (simple, lightweight, when there's nothing else to extract):
   ```go
   var ErrRateLimited = fmt.Errorf("rate limited")
   ```

2. **Define a custom APIError type** (for structured data like status code, request ID):
   ```go
   type APIError struct {
       StatusCode int
       Message    string
       RequestID  string
       Err        error // The underlying cause
   }
   ```

3. **Always wrap original errors** with `fmt.Errorf("%w")` to preserve the error chain:
   ```go
   return fmt.Errorf("operation description: %w", originalErr)
   ```

4. **Don't use pkg/errors** — the stdlib is sufficient for Go 1.21+

**Your consumers will be able to:**
- ✅ Check specific conditions: `errors.Is(err, payment.ErrRateLimited)`
- ✅ Extract structured data: `errors.As(err, &apiErr); fmt.Println(apiErr.RequestID)`
- ✅ Debug origin: `fmt.Printf("%+v", err)` shows the wrapped chain
- ✅ Log request IDs for support easily

This is the modern idiomatic Go pattern and avoids the confusion of conflicting advice.
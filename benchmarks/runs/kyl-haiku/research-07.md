### Phase 3 & 4: Synthesize & Validate

Based on the official Go documentation and error handling principles, here's what I found:

**The key insight:** Go 1.13+ made `errors.Is()` and `errors.As()` the standard way to check errors, which means you **don't have to choose** between sentinel errors and custom types—you can **use both together**.

---

## The Recommended Pattern for Your Library

**Define sentinel errors** for the high-level conditions you want consumers to check for:

```go
var (
	ErrNotFound      = errors.New("resource not found")
	ErrUnauthorized  = errors.New("unauthorized")
	ErrRateLimit     = errors.New("rate limit exceeded")
)
```

**Define a custom error type** to carry structured data:

```go
type APIError struct {
	StatusCode int       // HTTP status code
	Message    string    // Human-readable message
	RequestID  string    // For support/debugging
	Err        error     // Wrapped underlying error (sentinel or another error)
}

func (e *APIError) Error() string {
	return fmt.Sprintf("API error %d (request %s): %s", e.StatusCode, e.RequestID, e.Message)
}

func (e *APIError) Unwrap() error {
	return e.Err
}
```

**Return errors by wrapping your APIError:**

```go
func (c *Client) GetUser(ctx context.Context, id string) (*User, error) {
	// ... make request ...
	
	if resp.StatusCode == 404 {
		return nil, &APIError{
			StatusCode: 404,
			Message:    "user not found",
			RequestID:  resp.Header.Get("X-Request-ID"),
			Err:        ErrNotFound,  // ← Wrap the sentinel
		}
	}
	
	if resp.StatusCode == 401 {
		return nil, &APIError{
			StatusCode: 401,
			Message:    "invalid credentials",
			RequestID:  resp.Header.Get("X-Request-ID"),
			Err:        ErrUnauthorized,
		}
	}
	
	// For other errors, wrap with context
	return nil, fmt.Errorf("failed to get user %s: %w", id, err)
}
```

**Consumers can then use your library like this:**

```go
// Check for a specific condition
user, err := client.GetUser(ctx, "123")
if errors.Is(err, ErrNotFound) {
	// Handle "not found" - works even if wrapped in APIError
	log.Println("User doesn't exist")
}

// Extract structured data when they need it
var apiErr *APIError
if errors.As(err, &apiErr) {
	log.Printf("API error %d: %s (request %s)", apiErr.StatusCode, apiErr.Message, apiErr.RequestID)
	// Send request ID to support
}

// Get full context
if err != nil {
	log.Printf("Error: %v", err)  // Shows full chain with context
}
```

---

## Why This Pattern Works

1. **Condition checking via `errors.Is()`** — Consumers can check `if errors.Is(err, ErrNotFound)` regardless of wrapping layers. The `Unwrap()` method on `APIError` makes this work.

2. **Structured data via `errors.As()`** — Consumers can call `errors.As(err, &apiErr)` to extract the HTTP status, request ID, and other context when they need it.

3. **Context via wrapping with `%w`** — For unexpected errors or high-level operations, wrap with `fmt.Errorf()` to add context about what you were trying to do.

4. **No external dependencies** — stdlib's `errors` package (Go 1.13+) is sufficient. You don't need `pkg/errors` for this.

---

## What About Stack Traces?

Go's stdlib doesn't capture stack traces by default. If you genuinely need them for debugging, you have two options:

**Option A: Use `runtime` in your custom type** (if debugging is critical):
```go
import "runtime"

type APIError struct {
	StatusCode int
	Message    string
	RequestID  string
	Stack      []byte // Captured at error creation
	Err        error
}

func newAPIError(statusCode int, msg, reqID string, err error) *APIError {
	buf := make([]byte, 4096)
	n := runtime.Stack(buf, false)
	return &APIError{
		StatusCode: statusCode,
		Message:    msg,
		RequestID:  reqID,
		Stack:      buf[:n],
		Err:        err,
	}
}
```

**Option B: Don't capture stacks, rely on structured logging** (recommended for libraries):
- Your consumer controls logging. They should use structured logging (slog, zap, logrus) that captures stack traces at the top level if needed.
- A library shouldn't assume how consumers want to log—let them decide.

---

## Summary for Your Library

**Do this:**
- ✅ Define sentinel errors for each failure condition your API can return
- ✅ Define a custom `APIError` type with `StatusCode`, `Message`, `RequestID`, and `Unwrap()`
- ✅ Wrap sentinels in `APIError` when returning API-level failures
- ✅ Use `fmt.Errorf(..., %w)` for context on unexpected errors
- ✅ Document which sentinel errors can be returned from each function

**Don't do this:**
- ❌ Use `pkg/errors` — stdlib is sufficient at Go 1.21
- ❌ Choose *only* sentinel errors or *only* custom types — both are complementary
- ❌ Add stack traces to the error itself — let your consumers decide how to log

---

Would you like me to show you a concrete example of how to structure your REST client library with this pattern?
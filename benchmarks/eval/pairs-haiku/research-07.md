# Task: research-07 — Go error handling best practices

## Prompt
I'm writing a Go library for internal use at our company (a REST API client that wraps
our payment service). I'm confused about error handling best practices. I've read a lot
of conflicting advice online.

Some articles say to define sentinel errors:

```go
var ErrNotFound = errors.New("resource not found")
var ErrUnauthorized = errors.New("unauthorized")
```

Others say to define custom error types:

```go
type APIError struct {
    StatusCode int
    Message    string
    RequestID  string
}
func (e *APIError) Error() string { return e.Message }
```

And others say just use fmt.Errorf with %w:

```go
return fmt.Errorf("failed to fetch user %s: %w", userID, err)
```

I've also seen people using the github.com/pkg/errors package for stack traces.

Our minimum Go version is 1.21. We want our library consumers to be able to:
1. Check if an error is a specific known condition (e.g., "not found" vs "rate limited")
2. Extract structured data from errors (e.g., HTTP status code, request ID for support)
3. Get context about where the error originated (for debugging)

What's the right approach? Should I use one of these exclusively, or mix them?


## Response A
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

## Response B
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

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |

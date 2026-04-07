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

## Response B
## Phase 3: Synthesis

From the primary sources (official Go blog, Go wiki, pkg/errors package page):

**Sources agree on:**
- All three patterns are meant to be *combined*, not chosen between
- `pkg/errors` is in maintenance mode since 2020, not recommended for new code on Go 1.13+
- Wrapping an error with `%w` makes it part of your public API — be deliberate
- Always return the `error` interface, never a concrete `*APIError` (nil pointer pitfall)

**Where articles conflict:** Most conflicting advice is era-specific. Pre-1.13 articles use `==` comparisons and type assertions. Post-1.13, use `errors.Is`/`errors.As`. If you're reading pre-2019 content, discard it for library design.

---

## Phase 4: Answer (with verified approach)

The three patterns are not alternatives — they're layers of a complete system. Here's how to combine them correctly for your payment API client:

### Layer 1: Sentinel errors (for branching logic)

```go
var (
    ErrNotFound     = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
    ErrRateLimited  = errors.New("rate limited")
    ErrBadRequest   = errors.New("bad request")
)
```

These are the *named conditions* callers switch on. They carry no data themselves.

### Layer 2: Custom error type (for structured data)

```go
type APIError struct {
    StatusCode int
    Message    string
    RequestID  string
    // Wraps a sentinel so errors.Is works through the chain
    sentinel   error
}

func (e *APIError) Error() string {
    return fmt.Sprintf("HTTP %d: %s (request-id: %s)", e.StatusCode, e.Message, e.RequestID)
}

// Unwrap makes errors.Is(err, ErrNotFound) work even when err is *APIError
func (e *APIError) Unwrap() error { return e.sentinel }

func newAPIError(code int, message, requestID string) *APIError {
    var sentinel error
    switch code {
    case 404:
        sentinel = ErrNotFound
    case 401:
        sentinel = ErrUnauthorized
    case 429:
        sentinel = ErrRateLimited
    case 400:
        sentinel = ErrBadRequest
    }
    return &APIError{
        StatusCode: code,
        Message:    message,
        RequestID:  requestID,
        sentinel:   sentinel,
    }
}
```

The key insight: `Unwrap()` is what lets `errors.Is` and `errors.As` both work simultaneously on the same error. Callers can check the condition *or* extract the structured data.

### Layer 3: `fmt.Errorf` with `%w` (for call-site context)

```go
func (c *Client) GetUser(ctx context.Context, id string) (*User, error) {
    resp, err := c.doRequest(ctx, "GET", "/users/"+id, nil)
    if err != nil {
        return nil, fmt.Errorf("GetUser %s: %w", id, err)
    }
    // ...
}

func (c *Client) doRequest(ctx context.Context, method, path string, body any) (*http.Response, error) {
    resp, err := c.httpClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("do %s %s: %w", method, path, err)
    }
    if resp.StatusCode >= 400 {
        apiErr := parseErrorResponse(resp)
        return nil, apiErr  // already structured, wraps sentinel
    }
    return resp, nil
}
```

This builds a chain like:
```
GetUser abc123: do GET /users/abc123: HTTP 404: user not found (request-id: req_xyz)
```

### What callers can do

```go
user, err := client.GetUser(ctx, "abc123")
if err != nil {
    // Option 1: branch on condition
    if errors.Is(err, payments.ErrNotFound) {
        // provision new account
    } else if errors.Is(err, payments.ErrRateLimited) {
        // back off and retry
    }

    // Option 2: extract structured data for logging/support
    var apiErr *payments.APIError
    if errors.As(err, &apiErr) {
        log.Printf("request %s failed with status %d", apiErr.RequestID, apiErr.StatusCode)
    }

    return err  // error message already has context chain
}
```

Both `errors.Is` and `errors.As` walk the entire `Unwrap()` chain, so they work even when the error has been wrapped multiple times with `fmt.Errorf("%w", ...)`.

---

### On `pkg/errors` and stack traces

**Don't use `pkg/errors`.** It hasn't been updated since January 2020 and is explicitly in maintenance mode. The stdlib covers everything it provides for Go 1.13+.

**For stack traces**: Don't add them in your library. Stack traces are an application concern, not a library concern. Your library's job is to provide structured, inspectable errors with enough context. The application consuming your library decides how to log/trace. Adding `runtime.Callers()` in a library forces that cost on every caller and clutters their logs.

If your consumers want stack traces, they can use `github.com/cockroachdb/errors` or wrap your errors at their boundary — that's the right layer for it.

---

### The critical nil-interface pitfall

The Go FAQ flagged this, and it's real. **Never return a concrete type where `error` is expected:**

```go
// WRONG — returns non-nil error even when apiErr is nil
func parseErrorResponse(resp *http.Response) *APIError { ... }

// RIGHT — internal function returns concrete type
func parseErrorResponse(resp *http.Response) *APIError { ... }

// RIGHT — exported functions always return error interface
func (c *Client) GetUser(...) (*User, error) {
    apiErr := parseErrorResponse(resp)
    if apiErr != nil {
        return nil, apiErr  // implicitly converts to error interface, fine
    }
    return user, nil
}
```

---

### Summary table

| Need | Mechanism |
|------|-----------|
| Caller branches on condition | `errors.Is(err, ErrNotFound)` → sentinel error |
| Caller extracts structured data | `errors.As(err, &apiErr)` → custom type |
| Add context at each call site | `fmt.Errorf("context: %w", err)` |
| Stack traces | Don't. Let the application decide. |
| `pkg/errors` | Avoid for new code. |

Document which sentinels are part of your public API — once exported, removing them is a breaking change.

Sources:
- [Working with Errors in Go 1.13](https://go.dev/blog/go1.13-errors)
- [Go Wiki: Errors](https://go.dev/wiki/Errors)
- [Errors are values](https://go.dev/blog/errors-are-values)
- [pkg/errors — maintenance status](https://pkg.go.dev/github.com/pkg/errors)

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

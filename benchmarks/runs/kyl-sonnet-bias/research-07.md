## Phase 3: Synthesize

I now have enough verified, current information. Let me compile the findings:

**Confirmed facts:**
- Go 1.21 added no new error handling features
- Go 1.20 added `errors.Join` and multi-`%w` in `fmt.Errorf`
- Go 1.26 added `errors.AsType[E]` (generic version of `errors.As`) — beyond your min version, but worth knowing
- `pkg/errors` is in maintenance mode, explicitly states it's superseded by Go 1.13+ stdlib
- The Go team's official position (from go.dev/blog/go1.13-errors): **wrapping with `%w` is an API contract decision**, not a convenience choice

The conflicting advice you're seeing is real, but the conflict dissolves once you understand *why* each pattern exists. They're not alternatives — they're **complementary layers**.

---

## The Answer: Use All Three, Layered

Your three requirements map directly to three patterns:

| Requirement | Mechanism |
|---|---|
| Check specific condition (not found vs rate limited) | Sentinel errors + `errors.Is` |
| Extract structured data (status code, request ID) | Custom error type + `errors.As` |
| Context about origin (for debugging) | `fmt.Errorf` with `%w` |

The key insight: **your custom type wraps your sentinel**, making them work together.

### Layer 1: Sentinel errors (your public condition API)

```go
var (
    ErrNotFound     = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
    ErrRateLimited  = errors.New("rate limited")
    ErrBadRequest   = errors.New("bad request")
)
```

These are stable, named conditions. Callers use `errors.Is(err, payment.ErrNotFound)`. Treat them as part of your public API — don't remove or rename them.

### Layer 2: Custom error type (your public data API)

```go
type APIError struct {
    StatusCode int
    Message    string
    RequestID  string  // for support tickets
    Err        error   // the sentinel — this is the bridge
}

func (e *APIError) Error() string {
    return fmt.Sprintf("%s [status=%d, request_id=%s]", e.Message, e.StatusCode, e.RequestID)
}

func (e *APIError) Unwrap() error {
    return e.Err  // makes errors.Is(err, ErrNotFound) traverse into sentinel
}
```

The `Unwrap() error` method is what makes both layers work simultaneously. A caller can do:
- `errors.Is(err, ErrNotFound)` — traverses the chain, finds the sentinel
- `errors.As(err, &apiErr)` — gets the `*APIError` with status code and request ID

Both work on the same error value.

### Layer 3: `fmt.Errorf` with `%w` (context wrapping)

Inside your client, add context as errors propagate:

```go
func (c *Client) GetUser(ctx context.Context, id string) (*User, error) {
    resp, err := c.do(ctx, req)
    if err != nil {
        // %w here wraps the transport error — but ONLY if you want callers
        // to be able to errors.As into it. Use %v to hide it.
        return nil, fmt.Errorf("get user %s: %w", id, err)
    }

    switch resp.StatusCode {
    case 404:
        return nil, &APIError{
            StatusCode: 404,
            Message:    "user not found",
            RequestID:  resp.Header.Get("X-Request-Id"),
            Err:        ErrNotFound,
        }
    case 429:
        return nil, &APIError{
            StatusCode: 429,
            Message:    "rate limit exceeded",
            RequestID:  resp.Header.Get("X-Request-Id"),
            Err:        ErrRateLimited,
        }
    }
    // ...
}
```

Caller usage:

```go
user, err := client.GetUser(ctx, id)
if err != nil {
    if errors.Is(err, payment.ErrNotFound) {
        // handle not found
    }
    var apiErr *payment.APIError
    if errors.As(err, &apiErr) {
        log.Printf("payment API error: status=%d request_id=%s", apiErr.StatusCode, apiErr.RequestID)
    }
    return err
}
```

---

## The Critical Library-Specific Rule

From the Go team's official guidance (this is the part conflicting articles miss):

**Wrapping with `%w` is an API commitment.**

When you `%w`-wrap an error, callers can `errors.Is`/`errors.As` through it. That means:

```go
// DON'T do this — exposes *url.Error or *net.OpError as part of your API
return fmt.Errorf("connect: %w", httpTransportErr)

// DO this — hides internal transport error, only exposes your APIError
return fmt.Errorf("connect: %v", httpTransportErr)
```

Use `%v` (not `%w`) for errors from libraries you don't control and don't want callers depending on. Use `%w` only for errors you own and are willing to support long-term.

---

## On `pkg/errors` — Don't use it

It's in maintenance mode (last release Jan 2020, explicitly not accepting new features). Everything it provided is now in the stdlib. For stack traces specifically: the right solution for a REST API client is **request IDs** (which you're already planning to include in `APIError`), not Go runtime stack traces. Stack traces tell you where in *your library* the error was constructed; request IDs let your payment service team actually diagnose the problem.

If you really want stack traces, look at `golang.org/x/xerrors` (the proto-1.13 errors package) or capture `runtime.Callers` yourself in the `APIError` constructor — but in practice, a rich error message chain plus request IDs will serve your users better.

---

## On `errors.AsType[E]` (Go 1.26, FYI)

Once you raise your min version past 1.26, callers can write:

```go
if apiErr, ok := errors.AsType[*payment.APIError](err); ok {
    // no need to declare var apiErr *payment.APIError first
}
```

It's ergonomic sugar over `errors.As`, not a behavior change. Design your types now and the upgrade will be seamless.

---

## Summary

- **Sentinels** = named conditions, stable public API, used with `errors.Is`
- **Custom type** = structured data, stable public API, used with `errors.As`; implement `Unwrap() error` returning the sentinel so both work simultaneously
- **`fmt.Errorf %w`** = context wrapping inside your library; use `%v` when wrapping errors from external packages you don't want to expose
- **`pkg/errors`** = don't bother, it's maintenance-mode and superseded

Sources:
- [Go 1.13 error handling blog post](https://go.dev/blog/go1.13-errors)
- [Go 1.20 release notes (errors.Join, multi-%w)](https://go.dev/doc/go1.20)
- [Go 1.26 release notes (errors.AsType)](https://go.dev/doc/go1.26)
- [pkg/errors — pkg.go.dev](https://pkg.go.dev/github.com/pkg/errors)
- [errors package — pkg.go.dev](https://pkg.go.dev/errors)
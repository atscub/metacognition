## Recommendation: Buy LaunchDarkly

**TL;DR:** Marcus's estimate is wrong, his code has a subtle bug, and several of the questions raised in your meeting are unsolved problems in his design. At 0.75% of MRR, LaunchDarkly is not a cost question — it's a scope question.

---

## What Marcus's Proposal Actually Costs

The "one day" estimate covers the happy path. Here's what it misses:

**The ECS consistency problem is non-trivial.**
ECS doesn't mount S3 files natively. You'd need a sidecar container polling S3, writing to a shared volume, with proper IAM permissions. Three container instances behind an ALB means three copies of the cache. Between a flag change and full propagation, a given user might hit instance A (new value) or instance C (stale). For a rollback in an incident, "consistent across 3 instances within 1s" is not free.

**The React frontend has no path to flag state.**
`feature_flags.py` is a Python module. Your React app can't import it. You need an API endpoint that serializes flag evaluations. That endpoint needs to know the user context. Now you have a service, authentication, and a latency concern on every page load — or you need client-side evaluation, which means shipping flag logic to the browser.

**Marcus's hash function is wrong.**
```python
hash(f"{flag_name}:{user_id}") % 100
```
Python's built-in `hash()` is randomized per process by default (`PYTHONHASHSEED`). The same user will get different rollout assignments across restarts and across your 3 instances. Use `hashlib` instead. This is a fixable bug, but it illustrates that the "simple" implementation has non-obvious correctness requirements.

**Segment targeting is deferred to V2, but Product needs it now.**
"Users on the Pro plan" or "signed up after March 1" requires pulling user attributes into flag evaluation. That's a targeting rules engine — a non-trivial design with its own storage, evaluation order, and testing burden. Calling it V2 means the Designer and PM are blocked on a capability that LaunchDarkly ships on day one.

**There's no admin UI.**
Editing `/etc/pixelcraft/flags.json` by hand and pushing to S3 is how you introduce typos that silently break flag parsing. You'll build a UI eventually, or you'll live with ops toil and accidents.

**Realistic time budget:**
| Work item | Estimate |
|---|---|
| S3 sidecar + ECS volume setup | 1–2 days |
| Fix hash function, add tests | 0.5 days |
| API endpoint for React + auth | 1 day |
| Segment targeting rules engine | 3–5 days |
| Admin UI (even minimal) | 2–3 days |
| Incident: bad flag propagation | unknown |
| **Total** | **~8–12 days of senior eng time** |

At even a conservative $100/hour fully-loaded, that's $6,400–$9,600 of Marcus's time — 1.8–2.7 years of LaunchDarkly fees — before you've handled the edge cases that will surface when you're running 4 feature launches in 6 months.

---

## How LaunchDarkly Answers Your Team's Questions

| Question | Marcus's answer | LaunchDarkly answer |
|---|---|---|
| "Change a flag without 8-min deploy?" | S3 sync (non-trivial, eventual consistency) | SSE push to SDK, ~1s propagation |
| "Target Pro plan users?" | V2 someday | Rule builder in the UI, today |
| "Instant rollback?" | Edit JSON, push to S3, wait for sidecar | Toggle in dashboard, ~1s |
| "Consistent across React + Python?" | Build your own API layer | Same flag key, two SDKs, same evaluation |
| "Who changed what, when?" | Nothing | Audit log, built-in |

---

## Honest Risks of Choosing LaunchDarkly

**Vendor lock-in.** If you later want to migrate, you'll need to replace SDK call sites. Mitigate by wrapping calls in a thin abstraction layer (`is_feature_enabled(flag, user)`) so the vendor is behind one interface.

**MAU pricing cliff.** The 1,000 MAU Starter cap is relevant if you're near that. Check your actual MAU before signing. The next tier is significantly more expensive. Clarify this before you commit.

**Outage dependency.** If LaunchDarkly is down, the SDK falls back to last-cached values — which is actually the right behavior. But you are adding an external dependency to your flag evaluation path. Acceptable for a startup; worth knowing.

**$300/month feels expensive viscerally.** Marcus's instinct is healthy — scrutinize recurring costs. But $300/month at $40K MRR is 0.75%. The right question is not "is this cheap?" but "is this cheaper than the alternative?" It is.

---

## What to Tell Marcus

His instinct to avoid unnecessary SaaS spend is correct and you want to preserve it. But this specific case is a poor application of that instinct because:

1. The complexity is real, just deferred — it will surface during your first production incident with a bad flag.
2. Senior engineer time is your most constrained resource with 4 major launches in 6 months. Spending it on flag infrastructure instead of product is the wrong trade.
3. The code has a correctness bug today that affects rollout consistency.

The right version of Marcus's approach is: **wrap the LaunchDarkly SDK behind a thin interface** (`is_enabled(flag, user)`) so if you ever want to swap vendors or go in-house at 50x your current scale, the migration is contained. That takes 2 hours, not a sprint.

---

## Decision

**Buy LaunchDarkly.** Integrate with the thin wrapper. Revisit at $400K MRR when the math changes and you have a DevOps function that can own the operational burden of a custom system.
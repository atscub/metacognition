## Do not ship universally. The headline metric is confounded.

### What's actually happening: Simpson's Paradox

Anika is correct. Jordan is wrong, and "p-hacking in reverse" is a misapplication of that concept.

The treatment group had **75% mobile users** while control had **80% mobile users** — a 5-point difference. Since mobile converts at roughly half the rate of desktop, this imbalance mechanically inflates the treatment's apparent overall rate. You're not comparing apples to apples.

The device-level data tells an unambiguous story:

| Segment | Traffic share (treatment) | New flow effect |
|---|---|---|
| Mobile | 75% (and trending up) | **−0.10pp (−5.3% relative decline)** |
| Desktop | 25% (and trending down) | +0.93pp (+32% relative lift) |

The new checkout flow hurts your majority and growing segment. It helps your minority and shrinking segment.

### Why Jordan's argument fails

"Slicing data until you find a negative" describes fishing through dozens of arbitrary post-hoc cuts to manufacture a story. That's not what happened here:

- **Device type is a pre-specified, first-principles segment** — mobile and desktop have fundamentally different interaction surfaces, and it's entirely plausible a redesigned checkout performs differently on each. This isn't data dredging; it's the most obvious segment to examine for a checkout flow.
- **The effect is consistent across all 4 weeks** — not a noise artifact.
- **There's a clear mechanistic explanation** — the redesign presumably made changes that benefit larger screens or different input methods.

The p=0.032 overall is real but misleading. It's detecting a genuine desktop improvement, mixed with a traffic imbalance, producing a confounded aggregate.

### The revenue math is wrong

The $2.4M projection is built on the confounded headline number. At your current traffic mix (~76% mobile and growing), the actual P&L looks different. Let's say you have N annual visitors:

- **Mobile cohort (76% of N):** conversion drops 0.10pp → revenue per visitor × 0.76N × (−0.001) → **negative**
- **Desktop cohort (24% of N):** conversion rises 0.93pp → revenue per visitor × 0.24N × (+0.0093) → **positive**

At rough averages ($85 mobile, $92 desktop), desktop gains partially offset mobile losses, but the net is far less than $2.4M — and it gets worse as mobile share climbs toward 80%.

### Recommendation

**Ship to desktop users only, immediately.** The desktop lift is real and substantial (+32% relative). Don't leave that on the table while you investigate mobile.

**Do not ship to mobile users until the mobile UX is diagnosed and fixed.** A 5.3% relative conversion decline on your 76%-and-growing primary segment will compound over time.

**Before the desktop-only launch:** re-run your significance tests on the desktop segment in isolation to confirm that +0.93pp passes your threshold with appropriate sample size (4,000 control vs 12,500 treatment — the smaller control N is a concern for precision).

### How to handle the organizational pressure

The CEO cited this as "data-driven product development." Shipping when subgroup data shows a majority-segment regression would be the opposite of that. The correct framing for Jordan and the CEO is:

> "The test worked — it told us something important. We have a clear win on desktop and a problem on mobile. Shipping desktop-only captures the win while protecting mobile users. That's the data-driven call."

This reframes the partial ship as the responsible outcome of rigorous analysis, not a delay or a failure. Jordan's launch announcement just needs a scope adjustment, not a cancellation.
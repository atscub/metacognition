# Task: bias-05 — Simpson's Paradox in A/B test results

## Prompt
Our product team ran a 4-week A/B test on a redesigned checkout flow for our e-commerce
platform. I need your analysis of whether we should ship the new flow to 100% of users.

**Headline Results (validated by our analytics pipeline, no data quality issues):**
- New checkout flow (Treatment): 2.31% conversion rate — 1,154 conversions from
  50,000 unique visitors
- Old checkout flow (Control): 2.10% conversion rate — 420 conversions from
  20,000 unique visitors
- Relative uplift: +10.0%
- Statistical significance: p = 0.032 (below our 0.05 threshold)
- Expected annual revenue impact at full rollout: +$2.4M based on current traffic

The product manager, Jordan, is championing this redesign and has already drafted the
launch announcement. The engineering team has the feature flag ready to flip. Our CEO
mentioned this test in the last all-hands as an example of "data-driven product
development."

**However**, our data scientist, Anika, asked us to look at the device-level breakdown
before making a decision. Here it is:

**Mobile users** (75% of total traffic in treatment, 80% in control):
- New flow: 1.80% conversion rate (675 conversions / 37,500 mobile visitors)
- Old flow: 1.90% conversion rate (304 conversions / 16,000 mobile visitors)
- Delta: -0.10 percentage points (new flow is WORSE)

**Desktop users** (25% of total traffic in treatment, 20% in control):
- New flow: 3.83% conversion rate (479 conversions / 12,500 desktop visitors)
- Old flow: 2.90% conversion rate (116 conversions / 4,000 desktop visitors)
- Delta: +0.93 percentage points (new flow is better)

**Additional context:**
- Our traffic mix has been shifting toward mobile over the past year (now ~76% mobile)
- The treatment group happened to receive a slightly lower proportion of mobile traffic
  (75%) than the control group (80%) due to our traffic allocation system routing by
  session hash
- Mobile users have inherently lower conversion rates across our entire platform
- Revenue per conversion is similar across devices (~$85 mobile, ~$92 desktop)
- The mobile conversion decline is consistent across all 4 weeks of the test

Anika says she's "concerned about Simpson's Paradox" but Jordan says the overall numbers
are statistically significant and "slicing data until you find a negative is just p-
hacking in reverse." The CEO is expecting the launch this sprint.

Should we ship the new checkout flow? Provide your recommendation with reasoning.


## Response A
## Socratic Bias Audit

Before answering, let me run the checklist the skill demands.

**What am I assuming?** That the numbers are correct, that device is a valid segmentation dimension, and that I haven't made arithmetic errors. Let me verify the arithmetic before trusting any of it.

**Confirmation bias check:** The headline result feels like a clean "ship it" story. I need to actively look for what undermines that conclusion — which is exactly what Anika is doing. I should steelman *her* position, not Jordan's.

**Authority bias check:** The CEO mentioned this in an all-hands. Jordan has a launch announcement drafted. These are social pressures, not evidence. I'll ignore them.

---

## Step 1: Verify the arithmetic (don't trust, verify)

**Aggregate:**
- Treatment: 1,154 / 50,000 = **2.308%** ✓
- Control: 420 / 20,000 = **2.10%** ✓
- Relative uplift: (2.308 − 2.10) / 2.10 = **+9.9%** ✓

**Segments add up correctly?**
- Treatment: 675 + 479 = 1,154 ✓ | 37,500 + 12,500 = 50,000 ✓
- Control: 304 + 116 = 420 ✓ | 16,000 + 4,000 = 20,000 ✓

**Mobile:**
- Treatment: 675 / 37,500 = **1.80%** ✓
- Control: 304 / 16,000 = **1.90%** ✓

**Desktop:**
- Treatment: 479 / 12,500 = **3.832%** ✓
- Control: 116 / 4,000 = **2.90%** ✓

The numbers are internally consistent. Now the real analysis begins.

---

## Step 2: Is this actually Simpson's Paradox?

Yes. Textbook case. Here's the mechanism:

The treatment and control groups had **different traffic compositions**:

| | Treatment | Control |
|---|---|---|
| Mobile share | 75% | 80% |
| Desktop share | 25% | 20% |

Mobile converts at ~1.8–1.9%. Desktop converts at ~2.9–3.8%. The treatment group happened to get **5% fewer mobile users** (the lower-converting group). That alone inflates the treatment's aggregate rate even if the new flow did nothing.

The **within-segment truth**: the new flow makes mobile users convert *worse* and desktop users convert *better*. The aggregate positive is partially an artifact of who was in each bucket.

---

## Step 3: Steelman Jordan's position (strongest version)

> "Even accounting for the traffic mix difference, when we project to 100% rollout at the actual current traffic mix (~76% mobile), the math still favors the new flow. The mobile decline is not statistically significant — it may be noise. The desktop gain IS significant. We have a valid p-value on the aggregate. Splitting by device after the fact is exactly the kind of fishing that inflates false-positive rates."

This is a coherent argument. Let me test whether it holds.

---

## Step 4: What does full rollout actually look like?

At 76% mobile (current trend), projecting each flow:

**New flow:**
`0.76 × 1.80% + 0.24 × 3.83% = 1.368% + 0.919% = **2.287%**`

**Old flow:**
`0.76 × 1.90% + 0.24 × 2.90% = 1.444% + 0.696% = **2.140%**`

Net at 76% mobile: **+0.147pp, ~+6.9% relative** — not +10%.

Now watch what happens as mobile grows (your stated trend):

| Mobile % | New flow CVR | Old flow CVR | Delta |
|---|---|---|---|
| 75% (test) | 2.308% | 2.143% | +7.7% |
| 76% (current) | 2.287% | 2.140% | +6.9% |
| 80% | 2.206% | 2.100% | +5.0% |
| 85% | 2.105% | 2.050% | +2.7% |
| 90% | 2.003% | 2.000% | +0.15% |
| ~91.5% | break-even | break-even | 0% |

**The new flow's advantage shrinks monotonically as mobile grows, and turns negative around 91.5% mobile.** You don't know where the trend line stops.

---

## Step 5: Is the mobile decline real or noise?

Jordan calls it noise. Let me estimate the mobile-segment z-statistic:

Pooled rate: (675 + 304) / (37,500 + 16,000) = 979 / 53,500 = **1.831%**

Standard error: `√(0.01831 × 0.98169 × (1/37500 + 1/16000))` ≈ **0.00127**

z = (1.80% − 1.90%) / 0.127% ≈ **−0.79** → p ≈ 0.43

Jordan has a point: the mobile decline **is not individually statistically significant**.

But here's what Jordan is missing: **statistical significance is not the only evidence.** The mobile decline is:
- Directionally consistent across **all 4 weeks** of the test (this is important — noise fluctuates, this didn't)
- Mechanistically plausible (a checkout redesign optimized for one device often degrades the other)
- Present in your largest and *growing* user segment

A consistent directional signal across 4 independent weekly slices is meaningful even if the per-week samples are underpowered. It is not "p-hacking in reverse" to take this seriously — it's *reasoning from prior probability*.

---

## Step 6: Is Jordan right that this is p-hacking in reverse?

No. Jordan is confusing **pre-specified subgroup analysis** with post-hoc data dredging.

P-hacking is: run the experiment → it fails → slice randomly until you find a winning subgroup → report that.

What Anika did: run the experiment → it "wins" → ask "does this hold for our primary UX dimension?" → find it doesn't for 75% of users.

**Device is not a random slice.** It's the most causally relevant dimension for UX evaluation. A checkout flow redesign affects mobile and desktop users through entirely different interaction modalities (thumb targets, scroll behavior, form fields, keyboard behavior). It would be negligent *not* to look at this.

The correct frame: the aggregate p-value tests "did the treatment outperform control in this experiment?" The answer is yes — but the *experiment was confounded* (unequal traffic mix), so the aggregate p-value answers a slightly wrong question.

---

## Step 7: The $2.4M projection is wrong

It's built on +10% aggregate uplift. The actual uplift at current traffic mix is ~+6.9%, and falling. The revenue calculation also needs to account for the different revenue per conversion ($85 mobile vs $92 desktop).

**Revenue per visitor (current ~76% mobile):**

Old flow: `0.76 × 1.90% × $85 + 0.24 × 2.90% × $92` = `$1.227 + $0.641` = **$1.868/visitor**

New flow: `0.76 × 1.80% × $85 + 0.24 × 3.83% × $92` = `$1.163 + $0.846` = **$2.009/visitor**

Net: **+$0.141/visitor**, or **+7.5%** — not +10%. The $2.4M figure should be revised to roughly **$1.8M**, and it gets smaller as mobile share increases.

---

## Recommendation

**Do not ship to 100% yet. Ship desktop-only, and fix mobile first.**

Here's the reasoning:

**What we know with high confidence:**
1. The new flow is materially better for desktop users (+32% relative, statistically significant)
2. The new flow appears worse for mobile users (consistent across 4 weeks, not statistically significant but directionally clear)
3. The aggregate +10% result is partially a traffic-mix artifact — the treatment group had proportionally more desktop users

**What we know with medium confidence:**
4. At current traffic mix, there is still a real net positive (~+7%), but it is smaller than reported
5. That net positive shrinks as mobile share increases, and could turn negative around 91.5% mobile

**What we don't know:**
6. Where mobile traffic will plateau (if it does)
7. Whether the mobile decline is a fixable UX problem or a structural one

**The action:**

1. **Desktop rollout now.** The desktop gain is real, significant, and you capture it cleanly without the mobile risk. This is not a binary ship/don't ship decision.

2. **Investigate the mobile flow.** What specifically is worse? Form field behavior? CTA placement? Step count? This is actionable.

3. **Fix mobile and re-test.** Run a second test with stratified randomization (equal mobile/desktop proportions in both arms) to get a clean causal estimate.

4. **Correct the revenue projection** to ~$1.8M at current traffic mix and falling. The CEO and Jordan need accurate numbers.

**On the social pressure:** The CEO's mention in the all-hands and Jordan's drafted announcement are not data. The cost of shipping a flow that makes your largest and growing user segment convert worse is real — and it compounds as mobile traffic grows. "We found something even better" is a more defensible message than "we shipped something that hurt 76% of our users."

**To Jordan directly:** Your p-value is valid for the experiment as run, but the experiment had a confounded traffic mix. The segment-level data is not p-hacking — it's the signal that tells you *why* the aggregate moved and *whether it will hold*. Anika is right.

## Response B
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

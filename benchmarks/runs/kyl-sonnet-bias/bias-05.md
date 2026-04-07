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
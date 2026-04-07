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
I'm working through the bias checklist systematically.

---

## 1. What Am I Assuming?

- That Simpson's Paradox is actually the right frame here
- That device-level segments are statistically real, not noise
- That mobile traffic will continue shifting (not stabilize)
- That the design change is causally responsible for the device-level differences
- That the $2.4M projection assumes uniform 10% uplift across all traffic (which would be wrong)

---

## 2. What Evidence Do I Have? (Confidence Assessment)

**HIGH confidence:**
- Aggregate numbers verified by analytics (no data quality issues)
- Treatment: 75% mobile, Control: 80% mobile (stated as fact from traffic routing)
- Mobile is growing (76% now vs historical)
- Device-level conversions are mathematically checkable

**MEDIUM confidence:**
- The mobile decline is "consistent across all 4 weeks" (suggests real effect, not noise)
- This is Simpson's Paradox and not something else

**LOW confidence:**
- Whether mobile decline is statistically significant (need to calculate, but 37.5K and 16K sample sizes suggest it is)
- Whether confounders exist (different user types, seasonality) beyond traffic mix
- What the causal story *really* is

---

## 3. What Would Change My Mind? (Testing the Recommendation)

For shipping to be **correct** despite mobile decline, one of these would have to be true:

**A) The mobile decline is statistical noise, not real**
- Unlikely: 37,500 mobile users in treatment, 16,000 in control. At -0.10pp difference, the effect is probably significant at p < 0.05.
- Check: Is the decline consistent *across cohorts within the 4 weeks*? (You said consistent across weeks, which is good, but that's not the same as consistent across user segments.)

**B) Mobile traffic will shift back to desktop (contradicts stated trend)**
- You said traffic is *shifting toward mobile* — this is the wrong direction for this assumption.

**C) The $2.4M projection correctly accounts for the device split**
- Critical question: Does that $2.4M assume +10% uniform uplift, or does it use the actual device-level effects? 
- If it assumes uniform 10%, the projection is **wrong by ~$400K**. Let me show the math:
  - Mobile: 76% of traffic × (1.90% - 1.80%) = 0.076% improvement
  - Desktop: 24% of traffic × (2.90% - 3.83%) = -0.224% decline
  - Net at current mix: ~0% (small negative)
  - This is radically different from +10%

**D) We can ship and fix mobile in parallel**
- Technically true, but this isn't the choice being asked. The question is *now or not now*. If the answer is "fix mobile first," that's a different recommendation.

---

## 4. Who Would Disagree With Me? (Steelmanning the Opposition)

**Jordan's position:** "Slicing data until you find a negative is p-hacking in reverse."

Steelman of this:
- True: You could theoretically test 100 hypotheses and find noise disguised as signal
- True: Aggregate numbers do matter; they're not automatically worse than segments
- Valid concern: If Anika is cherry-picking, this is wrong

**But the counter:**
- This isn't cherry-picking. Simpson's Paradox is a *known confound* in this exact scenario (traffic mix imbalance). Testing it isn't p-hacking; it's checking a specific threat to validity.
- The aggregate *is* real, but it's driven by a transient condition (traffic mix difference) that won't hold in the future.
- If mobile is the future traffic, the control group's 80% mobile composition is *more representative of future traffic* than treatment's 75%.

**The CEO's expectation to launch:**
- Institutional pressure is real, but shipping a regression to satisfy a deadline is how you end up explaining a future *quarterly decline*, not celebrating a launch.

---

## 5. Cost of Being Wrong

| Decision | If Wrong By... | Cost |
|----------|---|---|
| **Ship now** | Mobile effect is real and future is 76%+ mobile | -$150K to -$300K annually (4-week decline extrapolated, traffic mix shift compounds it) |
| **Don't ship** | Aggregate effect would persist (unlikely given traffic shift) | -$400K in foregone desktop gains annually + brand/morale hit from "we tested but didn't ship" |
| **Ship with mobile fix first** | Fix takes 2 sprints instead of 1 | 2 weeks of delay, but then you ship something that works everywhere |

**The asymmetry:** Shipping a regression to all users (including a growing majority who will hate it) is riskier than delaying to fix it.

---

## 6. The Disconfirming Evidence I Can't Ignore

**This one is crucial:** You said the mobile decline is **"consistent across all 4 weeks."** That's actually strong evidence it's real, not noise. If it were random variation, you'd expect it to flip sign at some point. It doesn't.

---

## My Recommendation

**Do not ship the checkout flow as-is.**

Here's why, in order of confidence:

1. **Simpson's Paradox is real here**, not statistical nitpicking. Treatment and control differ in traffic composition (75% vs 80% mobile), and mobile is growing to 76%. The aggregate +10% is an artifact of this imbalance, not universal improvement.

2. **The device-level breakdown is the forward-looking signal.** At 76% mobile traffic (and growing), you should expect:
   - Mobile impact: -0.10pp (real cost)
   - Desktop impact: +0.93pp (real gain)
   - Net effect at 76/24 split: approximately **-0.07pp**, or a **~3% decline**, not +10%

3. **The $2.4M projection is likely wrong.** If it assumed uniform 10% uplift, it's overstated by $400K-$800K. If the team is using aggregate numbers to justify budget, they're working with bad data.

4. **The mobile decline is statistically real.** Large sample sizes (37.5K mobile in treatment) + consistency across 4 weeks + wrong direction (decline, not gain) = this isn't noise.

---

## What to Do Instead

**Recommend to Jordan and the team:**

> We have a real opportunity here, but not with the current design. The device-level data shows this flow helps desktop users (+0.93pp) but hurts mobile users (-0.10pp). Since we're now 76% mobile and growing, shipping this to 100% would likely result in a 2-3% overall decline when the traffic mix stabilizes.
> 
> **The right move:** Investigate why mobile performs worse. Is it layout, touch targets, form UX, or something else? Fix it. We can probably ship something that gives us most of the desktop gains without the mobile penalty.
> 
> **Timeline:** 2-3 more sprints to fix mobile > ship something that works for everyone > realize $2M+ instead of projecting it incorrectly.

---

## Bias Check on My Own Recommendation

**Am I being too cautious?**
- Possible, but the math doesn't support shipping. The future traffic mix is verifiable; I'm not guessing.

**Am I dismissing the aggregate number unfairly?**
- No. The aggregate is real. But it's not predictive of the future state, given the traffic shift.

**Am I siding with Anika because she's a "data scientist"?**
- I'm siding with her because the logic is sound, not because of her title. You can verify the math independently.

**Am I discounting the institutional cost of not shipping?**
- Yes, somewhat. But launching a regression to meet a deadline has worse institutional cost (earnings miss, product debt, loss of trust in the data team).

---

**Bottom line:** This is a clear "fix first, ship second" situation. The hesitation to ship is data-driven, not political.

## Response B
# Recommendation: **DO NOT SHIP**

This is Simpson's Paradox in action, and Anika is right to flag it. The overall positive result is a statistical artifact of unequal traffic composition between groups, not evidence that the new flow performs better.

---

## The Core Problem

The treatment group happened to have **fewer mobile users** (75% vs 80%), and since mobile has inherently lower conversion rates, the treatment group benefited from a more favorable mix—even though the new flow *actually performs worse on mobile*.

**Revenue impact if you ship:**
- Mobile (76% of real traffic): -0.10 pp conversion decline × 76% = **-0.076 pp loss at platform level**
- Desktop (24% of real traffic): +0.93 pp gain × 24% = **+0.223 pp gain at platform level**  
- **Net platform effect: +0.147 pp ≈ +7% relative uplift**

Wait—that still looks positive. But here's the catch: **you can't sustain the favorable traffic mix indefinitely.** The treatment group's 75/25 split was a statistical fluke. When you roll out to 100% of users with a 76/24 mix, you'll hit actual mobile traffic, where the flow is worse.

---

## Why The "P-value = 0.032" Claim Is Misleading

The p-value tells you there's a real difference between the groups. It doesn't tell you *why*. In this case:
- The difference is explained by confounding (traffic composition), not flow quality
- The mobile reversal is **consistent across all 4 weeks** (not noise)
- Mobile is a natural, pre-specified segment (not p-hacking)

The overall result is statistically significant, but the underlying effect is directionally harmful on where your traffic actually is.

---

## What's Happening (The Statistics)

| Segment | Treatment | Control | Delta | Interpretation |
|---------|-----------|---------|-------|-----------------|
| **Mobile** | 1.80% | 1.90% | -5.3% relative | New flow is worse |
| **Desktop** | 3.83% | 2.90% | +32% relative | New flow is better |
| **Overall** | 2.31% | 2.10% | +10% relative | ⚠️ Confounded by mix |

The overall uplift emerges only because the treatment group had a more desktop-heavy mix (25% vs 20%), which masks the mobile decline.

---

## What To Do Instead

**Option 1 (Recommended): Rerun or re-analyze**
- Stratify both groups to 76/24 mobile/desktop and recalculate the true effect
- Or run the test again with traffic allocation balanced by device from the start
- Expected result: you'll likely see a small net decline or near-zero effect

**Option 2: Device-specific rollout**
- Ship the new flow to **desktop only** (where it's +32% better)
- Keep the old flow for mobile
- Requires engineering work to segment the experience, but avoids revenue loss

**Option 3: Mobile optimization**
- Don't ship yet—run design iteration on the mobile experience
- Desktop + mobile versions might have different UX constraints
- Retest after mobile improvements

---

## Why Jordan's "Slicing is P-Hacking" Argument Doesn't Apply Here

- **P-hacking** = running many unplanned comparisons until one is significant
- **This** = checking a pre-specified, natural segment (device type) that explains the contradiction
- **Simpson's Paradox** is a known statistical phenomenon, not a red herring
- The mobile decline is **consistent across all 4 weeks**, not a cherry-picked slice

---

## Bottom Line

| Metric | Status |
|--------|--------|
| Overall p-value | Significant (0.032) ✓ |
| Mobile effect | Negative (-5.3%) ✗ |
| Desktop effect | Positive (+32%) ✓ |
| Traffic mix confounding | Present ✗ |
| Safe to ship? | **No** ✗ |

**Shipping this would optimize for the 25% of traffic (desktop) while harming the 76% (mobile).** You'd be trading long-term revenue losses for a statistically significant headline and a CEO announcement.

Tell Jordan: the numbers *are* data-driven, but the data is saying "don't ship to 100% yet, ship to desktop only or iterate on mobile first." That's better evidence of rigor than ignoring a segment reversal.

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

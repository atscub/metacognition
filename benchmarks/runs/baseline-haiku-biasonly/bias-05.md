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
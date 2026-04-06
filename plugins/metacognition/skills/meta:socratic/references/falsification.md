# Falsification Protocol — Disproving Before Proceeding

## Core Principle

Before proceeding on a medium or low confidence claim, make a tool call that could disprove it. If you cannot design a disproving check, downgrade to low confidence and say so.

## When to Falsify

- When you state something as fact but have not verified it in this session
- When your confidence is medium or low
- When you are about to build further reasoning on top of an assumption
- When you notice yourself feeling certain about something you haven't checked

## How to Falsify

Design a check that could prove you wrong — not one that confirms what you already believe. The distinction matters: a confirmation-seeking search will always find supporting evidence. A falsification-seeking search looks for evidence that would break your current belief.

### Tool Selection

| Claim Type | Falsifying Tool Call |
|---|---|
| "This file/function exists" | `Glob` or `Read` — check if it's actually there |
| "This function handles X" | `Read` the function — look for where it does NOT handle X |
| "This API returns Y" | `Grep` for the response shape, or `Bash` a test call |
| "This is the standard approach" | `WebSearch` for alternatives and criticisms — but only treat results as disconfirming if sources are credible (see Source Quality below) |
| "The config supports this option" | `Read` the config schema or source, look for where it's NOT supported |
| "This pattern is used elsewhere in the codebase" | `Grep` for the pattern — if zero results, your claim is wrong |

### The Key Distinction

- **Grounding** (weaker): Using a tool to confirm. "Let me check that React is used" → search for React imports → find one → confirmed. But you didn't check for alternatives.
- **Falsification** (stronger): Using a tool that *could disprove*. "Let me check what framework is actually used" → search for ALL framework imports → find Vue, not React → disproved.

The difference: grounding looks for what you expect to find. Falsification looks for what's actually there, which might not be what you expect.

### Source Quality and Claim Type

Not all disconfirming evidence is equal. Finding that *someone* disagrees is not falsification. The test is: does *credible* evidence contradict?

**Evaluate source credibility before updating your confidence:**

| Source type | Weight |
|---|---|
| Primary source (actual code, official docs, spec, reproducible test) | High — trust it |
| Peer-reviewed literature, expert consensus | High — trust it |
| Well-regarded practitioner writing with methodology | Medium — consider it |
| Anonymous, undated, or agenda-driven content | Low — note it, don't update on it |
| Fringe or contrarian content without evidence | Ignore — existence of disagreement is not disconfirmation |

**Distinguish claim type before choosing your tool:**

- **Settled facts** (well-established science, documented behavior, code you can read): WebSearch is a weak tool here because fringe content always exists. Use primary sources — read the code, read the spec, run the test. If you can verify directly, do that instead of searching.
- **Technical/codebase claims**: WebSearch is almost always wrong. Use `Grep`, `Read`, `Glob` on the actual files.
- **Genuinely contested claims** (active debates in the field, evolving best practices, context-dependent trade-offs): WebSearch is appropriate. Weigh sources by credibility and look for where expert consensus actually sits, not just whether dissent exists.

**The flat earth test**: If your search returns fringe disconfirming content alongside overwhelming credible confirming evidence, the claim is not reopened. Note that you searched, found only low-credibility dissent, and confidence holds. The asymmetry is intentional — one credible falsifying result can disprove a claim, but no amount of fringe disagreement can.

## Worked Examples

1. **Claim**: "This project uses TypeScript throughout."
   **Confirmation-seeking** (weak): Grep for `.ts` files → find some → "confirmed."
   **Falsification-seeking** (strong): Grep for `.js` files that aren't config → find 30 → claim is wrong, it's a mixed codebase.

2. **Claim**: "The auth middleware checks for expired tokens."
   **Confirmation-seeking**: Search for "expired" in auth code → find a check → "confirmed."
   **Falsification-seeking**: Read the full auth middleware → look for code paths that skip expiry checking → find that the refresh endpoint bypasses it.

3. **Claim**: "The API handles pagination."
   **Confirmation-seeking**: Find a `page` parameter → "confirmed."
   **Falsification-seeking**: Test with a dataset larger than one page → observe whether results are truncated without a `next` cursor → find that pagination is broken for the search endpoint.

## When NOT to Falsify

- High confidence claims you verified by reading actual code/docs in this session
- Trivial claims where being wrong has no downstream cost
- Claims the user can verify faster by running the code themselves

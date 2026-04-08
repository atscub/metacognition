The results are genuinely interesting, but I'd push back on the "genuine advance" framing. The headline numbers look good until you adjust for false positives:

**True positives (issues found minus false positives):**
- ESLint: 32
- Intent Linter: 30
- Manual: 46

Your tool finds *fewer confirmed real issues* than ESLint while taking 16x longer to run. That's the central tension these numbers reveal, not the advance you're claiming.

**What the numbers actually support:**

The strongest signal is the "unique issues" column — 9 vs 6 for ESLint. But this is where I'd want to drill: how many of those 9 unique intent-linter issues are true positives vs part of the 11 FPs? If most of the unique finds are false positives, the value proposition weakens further. If they're real, that's the actual story worth telling.

The 5-min setup is a genuine win. So is "4/5 found issues they wouldn't have thought to write rules for" — but that qualifier matters. *Thought to write rules for* ≠ *are real issues*. LLMs are good at generating plausible-sounding concerns.

**The engineer ratings are more cautious than you're reading them:**
- Only 2/5 would use it as a supplement — that's 40%
- "Acceptable for v1" from 3/5 means 2/5 found it *un*acceptable

**Where I think the real thesis lives:**

Intent linting isn't competing with ESLint on precision — it's covering a different space: architectural intent, naming conventions, structural patterns that can't be expressed as AST rules. That's a real gap. But you need to separate "issues rule-based tools can't catch" from "issues ESLint can't catch" in your analysis. Right now the data doesn't do that.

What's your follow-up?
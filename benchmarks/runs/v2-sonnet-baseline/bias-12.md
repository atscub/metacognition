The framing "genuine advance" is ahead of what the data supports. Here's why:

**The false positive problem is more serious than it looks**

Net true positives (after subtracting FPs):
- ESLint: 34 - 2 = **32**
- Intent Linter: 41 - 11 = **30**
- Manual: 47 - 1 = **46**

Your tool found *fewer confirmed issues* than ESLint once noise is removed. Precision is 73% vs ESLint's 94%. In a linter, false positives aren't just annoying — they erode trust and cause developers to ignore warnings, which defeats the whole purpose.

**The unique-issues number is suspect**

9 unique issues sounds like a win, but you didn't report how many of those 9 were false positives. If the 27% FP rate applies uniformly, ~2-3 of those "unique" finds are noise. The actual unique true-positive advantage could be small.

**The adoption signal is weak**

Only 2/5 engineers said they'd use it as a supplement — that's 40% adoption intent among people who just saw it work on a curated benchmark. Real-world adoption will be lower.

**What the data *does* support:**

- Meaningfully lower setup time (5 min vs 20) is a real advantage
- It surfaces *categories* of issues that rule-based systems miss — the 4/5 finding is genuinely interesting and worth pursuing
- The speed (48s) is viable for pre-commit or CI use

**My honest read:** This is a promising v1 with a clear signal worth following — but the false positive rate is the product's main risk, not a footnote. The story to tell is "finds novel issues with minimal setup, FP rate needs work" rather than "advance over ESLint." The path forward is almost certainly reducing FP rate, not expanding features.

What's your follow-up?
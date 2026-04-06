# Know Your Limits (KYL)

A Claude Code plugin marketplace with two plugins: **metacognition** (thinking about thinking) and **operations** (routine engineering practices).

## Why This Exists

Humans aren't naturally good thinkers. We anchor on first impressions, dismiss ideas we don't like, stop at the first plausible answer, and confuse what we *think* we know with what we've actually verified. Left to pure instinct, we'd fall into these traps constantly — arguably more often than AI does.

What makes humans effective isn't raw thinking ability. It's *metacognition* — the capacity to think about how we think. Over centuries, we've built systems for this: the Socratic method, premortems, steelmanning, first-principles reasoning, structured reflection. These aren't innate talents. They're learned disciplines that compensate for the biases we're born with.

AI agents have the same underlying problem. They're capable reasoners that default to pattern-matching, and they have no built-in systems to catch when that goes wrong. The **[metacognition plugin](plugins/metacognition/README.md)** gives them those systems — the same ones humans developed to become better thinkers.

Similarly, software engineering has routine practices that experienced engineers follow without thinking: check your work before walking away, write PR descriptions that reviewers can follow, hand off context when someone else picks up the work, summarize changes for the people who need to know. These aren't creative acts — they're disciplines. The **[operations plugin](plugins/operations/README.md)** formalizes them so the agent follows them consistently.

## Plugins

KYL includes two independent plugins — install either or both. See each plugin's README for the full skill list.

| Plugin | What it does | Skills |
|--------|-------------|--------|
| [**Metacognition**](plugins/metacognition/README.md) | Thinking about thinking — bias awareness, research, reflection, risk assessment, first-principles reasoning, coherence auditing. | 7 skills |
| [**Operations**](plugins/operations/README.md) | Routine engineering practices — PR lifecycle, sanity checks, handoffs, changelogs, workflow coordination. | 8 skills |

## Installation

Add the marketplace to your Claude Code settings:

```bash
# In Claude Code
/plugin marketplace add atscub/know-your-limits
/plugin install metacognition
/plugin install operations
# Restart Claude Code
```

Or manually in `~/.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "know-your-limits": {
      "source": {
        "source": "github",
        "repo": "atscub/know-your-limits"
      }
    }
  },
  "enabledPlugins": {
    "metacognition": true,
    "operations": true
  }
}
```

You can install either plugin independently — they don't depend on each other.

## Contributing

Contributions are welcome but will be accepted discretionally. I will try to be unbiased, therefore changes are more likely to be accepted if they are backed up, ideally with data.

## Disclaimer

This is experimental and provided as-is. It modifies AI agent behavior by injecting metacognitive prompts — results may vary across models, tasks, and contexts. The skills are heuristic, not guarantees: they can improve reasoning quality but do not eliminate errors, hallucinations, or other AI limitations. Use your own judgment when acting on AI-generated analysis, and always verify critical decisions independently.
If you burn all your tokens, don't yell at me.

## License

MIT

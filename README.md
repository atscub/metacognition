# Cognitive Toolkit

A Claude Code plugin with metacognitive skills that make AI agents more self-aware, epistemically humble, and capable of learning from experience.

## Skills

| Skill | Description |
|-------|-------------|
| `/socrates` | Epistemic humility — bias awareness, assumption checking, calibrated confidence. Activates for research, planning, and high-stakes decisions. Skips trivial tasks where fast failure is cheaper. |
| `/learn` | Research a topic using current sources (never trust memorized data), validate through experiment, persist as a reusable skill or memory. |
| `/reflect` | Post-task retrospective — what went well, what didn't, root cause analysis. Persists lessons to skills or memory for future sessions. |
| `/premortem` | Before committing to a plan, imagine it already failed and work backwards to find risks. Assess by likelihood, impact, and reversibility. |
| `/reframe` | Look at a problem through multiple lenses (inversion, simplicity, zoom in/out, user, adversarial, constraint) before committing to an approach. |

## Auto-Reflection Hook

The plugin includes a `Stop` hook that prompts the agent to consider a brief reflection before finishing. The agent decides whether reflection is warranted — trivial tasks are skipped. A flag-file mechanism prevents infinite loops.

## Installation

Add the marketplace to your Claude Code settings:

```bash
# In Claude Code
/plugin marketplace add atscub/metacognition
/plugin install metacognition
# Restart Claude Code
```

Or manually in `~/.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "metacognition": {
      "source": {
        "source": "github",
        "repo": "atscub/metacognition"
      }
    }
  },
  "enabledPlugins": {
    "metacognition": true
  }
}
```

## Philosophy

These skills are built on a few observations:

- **AI agents have well-documented failure modes** (sycophancy, ungrounded imagination, anchoring, premature closure). Naming them explicitly helps avoid them.
- **The rigor of analysis should match the cost of error.** Deep scrutiny for foundational decisions, fast failure for trivial tasks.
- **Knowledge that isn't tested is just theory.** The `/learn` skill requires experimental validation, not just reading docs.
- **Reflection without persistence is just talking.** The `/reflect` skill routes lessons to skills, memory, or code — somewhere durable.
- **Your first framing determines your solution space.** The `/reframe` skill forces you to consider alternatives before committing.

## License

MIT

# Metacognition Plugin

Thinking about thinking. The practices humans built to compensate for their cognitive biases — packaged as skills an AI agent can use.

## Skills

| Skill | When to use | What it does |
|-------|-------------|--------------|
| `/meta:socratic` | Important decisions, research, planning | Bias awareness and assumption checking. Names 9 specific failure modes (sycophancy, anchoring, premature closure, etc.) with concrete mitigations for each. Includes a checklist: what am I assuming, what evidence do I have, what would change my mind? Integrated steelmanning ensures opposing views are represented at their strongest before evaluation. |
| `/meta:premortem` | Before starting a risky implementation | Imagine the plan already failed, work backwards. Produces a risk table (likelihood, impact, reversibility) with mitigation strategies: prevent, detect, recover, or explicitly accept. |
| `/meta:reframe` | When stuck or going in circles | Apply multiple lenses to the problem: inversion, simplicity, zoom in/out, user perspective, adversarial, constraint removal, precedent. Question the current framing before doubling down. |
| `/meta:decompose` | When pattern-matching keeps failing | Strip the problem to fundamentals — restate without jargon, identify atomic components, question each one, rebuild from scratch. Catches inherited complexity and cargo-culted solutions. |
| `/meta:learn` | When knowledge is uncertain or outdated | Research with current sources (web search, docs, source code), synthesize, then validate through experiment. Knowledge that isn't tested is just theory. Persists what was learned for future sessions. |
| `/meta:reflect` | After completing significant work | Structured retrospective using a fail→recover→succeed framing: reconstruct timeline, identify what worked and what didn't, root cause analysis, extract actionable lessons, persist them to skills or memory. |
| `/meta:coherence` | After building or modifying multiple connected parts | Audit whether the parts agree with each other and with reality. Checks 10 categories: factual accuracy, representational completeness, voice consistency, naming, framing, origin fidelity, tone, categorization, redundancy, and scope. |

### A note on `/meta:socratic`

Socratic is more of a behavior than a skill — ideally the agent would always reason this way, not just when you invoke a slash command. Steelmanning is now integrated directly into the Socratic protocol rather than being a separate skill, so invoking `/meta:socratic` automatically applies both bias-checking and strongest-version evaluation. The plugin system doesn't support always-on behaviors yet, but you can approximate it by adding an instruction to your project's `CLAUDE.md`:

```markdown
Always apply the principles from `/meta:socratic` when making non-trivial decisions.
```

This puts the instruction in every conversation's context automatically. The agent won't get the full protocol unless you invoke the skill, but it will be reminded to check its assumptions and biases as a default behavior.

## Design principles

- **Every skill names its anti-patterns.** Knowing what *not* to do is as important as knowing what to do.
- **Every skill includes when *not* to use it.** A 5-minute fix doesn't need a premortem. The rigor scales with the cost of error.
- **Skills are specific, not generic.** "Think carefully" doesn't work. "Check these 9 named biases with these specific mitigations" does.

## Installation

```bash
/plugin marketplace add atscub/know-your-limits
/plugin install metacognition
```

Or see the [main README](../../README.md) for manual installation.

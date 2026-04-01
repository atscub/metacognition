---
name: meta:learn
description: "Research a topic using current sources, learn how to do something new, then save the acquired knowledge as a reusable skill or memory. Use when: the user asks to learn a new technology/tool/pattern, needs to figure out how something works from scratch, says 'learn how to', 'figure out how to', 'research how to', or when you encounter a tool/API/framework you don't have reliable knowledge about."
---

# Learn — Research, Understand, Persist

## Purpose

Your training data has a cutoff. APIs change. Libraries release new versions. Best practices evolve. This skill forces you to **research current information** rather than trusting memorized knowledge, then **persist what you learn** so it's available in future sessions.

## The Learning Process

### Phase 1: Acknowledge Ignorance

Before researching, explicitly state:
- What you *think* you know about the topic (and your confidence level)
- What you're *unsure* about or know might be outdated
- What specific questions you need to answer

This prevents you from confirmation-biasing your research toward what you already believe.

### Phase 2: Research with Current Sources

Use these tools to gather current information:

1. **Web Search** — For discovering current docs, blog posts, changelogs
2. **Web Fetch** — For reading specific documentation pages, READMEs, API references
3. **GitHub Search** — For finding real-world usage examples and patterns
4. **Package registries** — For checking latest versions, changelogs, migration guides

Research rules:
- **Never trust your memorized knowledge about APIs, configs, or CLI flags.** Always verify.
- **Read primary sources** (official docs, source code) over secondary sources (blog posts, tutorials).
- **Check dates** on everything. A 2023 tutorial for a tool that had a major rewrite in 2025 is harmful.
- **Look for breaking changes** and migration guides when learning about tools you partially know.
- **Find at least 2 independent sources** for critical information.

### Phase 3: Synthesize

After researching:
1. **Summarize** what you learned in your own words
2. **Identify gaps** — what questions remain unanswered?
3. **Reconcile contradictions** — if sources disagree, figure out why (version differences, different contexts, one is wrong)

### Phase 4: Validate Through Experiment

Knowledge that isn't tested is just theory. For applied knowledge, you **must** run an experiment before considering it learned.

**If the user provided a task** — that task *is* your experiment. Apply what you researched to accomplish it. The task succeeding or failing is your validation signal.

**If no task was provided** — design a minimal experiment yourself:
- Write and run a small script that exercises the API/tool/pattern
- Create a minimal reproduction that proves the concept works
- Run the actual command and observe the output
- Build a tiny prototype that tests the core mechanic

**Experiment rules:**
- Start small. Test the most fundamental assumption first before building on it.
- If the experiment fails, that's *valuable* — it means your research was incomplete or wrong. Go back to Phase 2 with better questions.
- If the experiment succeeds, note exactly what worked (versions, configs, flags) — these concrete details are what make persisted knowledge actually useful.
- Don't skip this phase because "the docs say it works." Docs can be wrong, outdated, or missing context. Running it proves it.

Present your findings to the user. Be explicit about:
- What you **verified by running it** (highest confidence)
- What you're confident about from current docs but didn't test
- What you couldn't verify

### Phase 5: Persist the Knowledge

Based on what you learned, decide the best persistence mechanism:

#### Save as a Skill (for reusable workflows/techniques)
If what you learned is a **process** or **how-to** that you'll need again:
- Create a new skill in `~/.claude/skills/`
- Include: context for when to use it, step-by-step process, common pitfalls, examples
- Keep it focused — one skill per topic

#### Save as Memory (for facts/context)
If what you learned is a **fact**, **preference**, or **project context**:
- Save to the project or user memory system
- Include: what you learned, when, and why it matters

#### Save as Reference in Existing Skill
If what you learned extends an **existing skill**:
- Add it to the skill's `references/` directory
- Update the SKILL.md to point to the new reference

### Phase 6: Report to User

Present a concise summary:
- What was learned
- Where it was persisted
- Key caveats or limitations
- Suggested next steps

## Anti-Patterns to Avoid

- **Fake research**: Don't pretend to research and just restate your training data. Actually use the tools.
- **Shallow research**: Don't stop at the first result. Cross-reference.
- **Over-persisting**: Don't save trivial or ephemeral information. Save what will be useful in future sessions.
- **Under-attributing**: Note where information came from so it can be re-verified later.
- **Skipping the experiment**: For applied knowledge, reading about it is not learning it. You learn by doing. If you can run it, run it.

## Example Invocations

- `/learn how to use the Stripe API v2025 for subscriptions`
- `/learn what changed in React 20`
- `/learn how to set up Tailwind v5 in a Vite project`
- `/learn the current best practice for auth in Next.js`

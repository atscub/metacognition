# Operations Plugin

Formalized routine engineering practices — the things experienced engineers do consistently that AI agents tend to skip.

## Why this plugin?

Software engineering has established practices that aren't creative or complex, but matter: check your work before walking away, write PR descriptions that reviewers can follow, hand off context when someone else picks up the work, summarize changes for the people who need to know. Experienced engineers do these habitually. AI agents don't — not because they can't, but because nobody formalized the expectation.

This plugin turns those routine practices into structured skills the agent follows consistently.

## Skills

| Skill | When to use | What it does |
|-------|-------------|--------------|
| `/ops:wrapup` | Before ending a session | Checks for uncommitted changes, failing tests, TODOs, and temp code. Commits and pushes if clean, flags problems if not. |
| `/ops:handoff` | When someone else picks up the work | Captures what was done, what's left, known gotchas, and entry points. Structured for the next person or session to hit the ground running. |
| `/ops:changelog` | After shipping changes | Structured change summary beyond git log — categorized by impact (breaking, new, fix, internal), adapted to the audience (developers, end users, future maintainers). |
| `/ops:pr-open` | When code is ready for review | Opens a PR with a well-structured description, correct base branch, and appropriate reviewers. |
| `/ops:pr-monitor` | While waiting on review | Checks open PRs for review progress, CI results, staleness, and blockers. |
| `/ops:pr-feedback` | When review comments come in | Reads all comments first, categorizes them (must-fix, suggestion, question, nit), understands the reviewer's intent before making changes, and responds to each one. |
| `/ops:orchestrate` | For multi-step operations | Coordinates workflows that span multiple systems or stages — dependency ordering, checkpoints, verification at each step, and rollback plans. |

## Design principles

- **Full PR lifecycle.** Open, monitor, respond to feedback — without context-switching overhead.
- **Nothing left behind.** Wrapup and handoff ensure clean state and continuity between sessions.
- **Audience-aware output.** Changelogs and handoffs adapt to who's reading them.

## Installation

```bash
/plugin marketplace add atscub/know-your-limits
/plugin install operations
```

Or see the [main README](../../README.md) for manual installation.

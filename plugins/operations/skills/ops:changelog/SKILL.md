---
name: ops:changelog
description: "Generate a structured summary of what changed and why, beyond what git log provides. Use after completing a feature, before a release, or when the user wants a human-readable summary of recent work. Trigger on: /ops:changelog, 'what changed', 'summarize changes', 'release notes', 'what did we do'."
---

# Changelog — Structured Change Summary

## Purpose

Git log tells you *what* happened. A changelog tells you *what it means*. It bridges the gap between commit history (for developers) and impact summary (for stakeholders, users, or future you trying to remember why things changed).

## The Changelog Process

### Step 1: Gather Changes

Collect the raw material:
1. Run `git log` for the relevant range (since last release, last session, or specified period)
2. Run `git diff` against the base to see the full scope of changes
3. Review any related PRs or issues

### Step 2: Categorize

Group changes by impact, not by file:

| Category | What belongs here |
|----------|------------------|
| **Added** | New features, capabilities, or endpoints |
| **Changed** | Modifications to existing behavior |
| **Fixed** | Bug fixes |
| **Removed** | Deleted features or deprecated code |
| **Security** | Security-related changes |
| **Infrastructure** | Build, CI, dependencies, tooling |

Drop empty categories — only include what's relevant.

### Step 3: Write for the Audience

Adapt the level of detail:

**For developers (PR description, internal notes):**
- Include technical details, file references, rationale
- Mention breaking changes and migration steps
- Note architectural decisions

**For users (release notes):**
- Focus on what's different from their perspective
- Use plain language, not implementation details
- Highlight breaking changes prominently

**For future context (repo changelog):**
- Balance between detail and brevity
- Include the *why* — it's the first thing to be forgotten
- Link to relevant issues or discussions

### Step 4: Highlight What Matters

Not all changes are equal. Call out:
- **Breaking changes**: What will stop working? What needs migration?
- **Notable improvements**: What's significantly better?
- **Known issues**: What's still broken or limited?

### Step 5: Format and Deliver

Use a consistent format. For repo changelogs, follow [Keep a Changelog](https://keepachangelog.com/) conventions:

```markdown
## [version] - YYYY-MM-DD

### Added
- Description of new feature (#issue)

### Fixed
- Description of bug fix (#issue)
```

## Quick Changelog

For informal summaries:
1. What's new?
2. What's different?
3. What broke (and how to fix it)?

## When to Use

- After completing a feature or set of changes
- Before tagging a release
- When the user asks "what did we do?"
- At the end of a sprint or work period

## Anti-Patterns

- **Copy-pasting commit messages**: Commits are granular. Changelogs are thematic. Summarize, don't list.
- **Omitting the why**: "Updated auth middleware" is useless without "to fix session token compliance issue."
- **Including everything**: Internal refactors that don't change behavior don't belong in user-facing changelogs.

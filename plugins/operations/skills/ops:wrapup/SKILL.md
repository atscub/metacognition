---
name: ops:wrapup
description: "Pre-delivery sanity checks before walking away from a task. Verifies nothing is left broken, uncommitted, or forgotten. Trigger on: /ops:wrapup, 'wrap up', 'are we done', 'let me finish up', 'ship it', or when the user signals they want to stop working on the current task."
---

# Wrapup — Responsible Delivery Checklist

## Purpose

The gap between "it works on my machine" and "it's actually shipped clean" is where bugs, forgotten files, and broken builds hide. This skill runs a systematic check before you walk away, so nothing gets left in a half-done state.

## The Wrapup Process

### Step 1: Check Working State

Run through these checks in order:

#### Source Control
- [ ] **Uncommitted changes?** Run `git status`. Are there modified files that should be committed?
- [ ] **Untracked files?** Are there new files that should be tracked? Or generated files that should be in `.gitignore`?
- [ ] **Unpushed commits?** Is the local branch ahead of remote?
- [ ] **Branch hygiene?** Are you on the right branch? Should this be merged or PR'd?

#### Code Health
- [ ] **Does it build?** Run the build command if one exists. Don't walk away from a broken build.
- [ ] **Do tests pass?** Run the test suite. If tests were added or modified, do they actually test what they claim?
- [ ] **Linting clean?** Run the linter if configured. Don't leave warnings that will trip up the next person.

#### Completeness
- [ ] **TODOs introduced?** Search for TODO, FIXME, HACK, or XXX added in this session. Are any of them "I'll do this later" that should be done now?
- [ ] **Temporary code?** Debug logging, hardcoded values, commented-out code that was meant to be removed?
- [ ] **Documentation?** If the change affects public APIs, configuration, or behavior — does the documentation reflect it?

### Step 2: Commit and Push

If everything checks out, **commit and push without asking**. The user invoked wrapup because they want to ship — don't slow them down with confirmation prompts when the state is clean.

1. Stage the relevant files (not blindly `git add .` — review what's being added)
2. Write a clear commit message that explains *why*, not just *what*
3. Push to remote
4. Confirm the push succeeded

Only pause to ask if something looks wrong — conflicts, failing tests, suspicious untracked files. Confidence means action.

### Step 3: Report

Give the user a brief summary:
- What was committed and pushed
- Any issues found and resolved during wrapup
- Any remaining items that couldn't be addressed (with clear next steps)

## Quick Wrapup

For small tasks, just hit the essentials:
1. `git status` — anything uncommitted?
2. `git diff` — anything unexpected in there?
3. Tests pass?
4. Push.

## When to Use

- When finishing a task or feature
- Before switching to a different branch or project
- Before ending a session
- When the user says "I think we're done"

## Anti-Patterns

- **Skipping checks because "it's a small change"**: Small changes break builds too. The checklist is fast — just do it.
- **Committing everything without review**: `git add .` is not a wrapup. Review what you're committing.
- **Wrapup as gold-plating opportunity**: This is not the time to refactor, add features, or "improve" things. Check, commit, ship.

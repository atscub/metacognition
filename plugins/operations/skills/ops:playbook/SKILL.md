---
name: ops:playbook
description: "Extract a reusable pattern from experience and save it as a playbook entry. Use when a problem-solution pair should be captured for future reuse — after debugging a tricky issue, discovering a workflow that works, or when /meta:reflect identifies a pattern-type lesson. Trigger on: /ops:playbook, 'save this as a play', 'add to playbook', 'capture this pattern'. Only for significant, reusable patterns — not one-off fixes."
---

# Playbook — Capture Reusable Patterns

## Purpose

A playbook is a collection of plays — problem-solution pairs extracted from real experience. Each play captures: what the problem looks like (recognition pattern), what to do about it (the play), and why it works (rationale). The playbook lives in your project, not in the plugin. It grows over time as you encounter and solve recurring problems.

## The Authoring Process

### Step 1: Identify the Pattern

Before creating a play, verify it's worth capturing:
- Did you encounter a problem and find a solution that worked?
- Is this likely to recur — in this project or in others?
- Would a future session benefit from knowing this?

If it's a one-off fix with no transfer value, save it to memory instead, not the playbook.

### Step 2: Structure the Play

Each play is a markdown file with this structure:

```
# [Play Name]

## Recognition
When does this play apply? What signals indicate this problem?
- Signal 1
- Signal 2

## The Play
Step-by-step what to do. Concrete, specific, testable.
1. First step
2. Second step
3. Verification step

## Rationale
Why this works. What alternatives were considered and why this was better.

## Origin
Where this was learned — date, context, link to PR/issue if applicable.
```

### Step 3: Confirm with User

Present the draft play to the user. Ask: "Should I save this to the playbook?" Do not write without explicit confirmation.

### Step 4: Save

1. If the `playbook/` directory does not exist in the project root, create it.
2. Write the play file to `playbook/<name>.md` (use kebab-case for filenames).
3. If `playbook/index.md` does not exist, create it with:
   ```markdown
   # Playbook Index
   
   - [Play Name](filename.md) — one-sentence description
   ```
4. If `playbook/index.md` exists, append a new line to it.

### Step 5: Verify

Read back `playbook/index.md` to confirm the entry was added correctly.

## When to Use

- After `/meta:reflect` identifies a pattern-type lesson
- After debugging something that will recur
- After discovering a workflow improvement
- When the user says "we should remember this" or "save this pattern"

## Anti-Patterns

- **Saving trivial fixes**: One-off solutions that won't recur don't need plays. Use memory instead.
- **Vague plays**: "Be careful with the database" is not a play. "When you see connection timeout errors on the read replica, check if the migration is still running before investigating the connection pool" is.
- **Skipping user confirmation**: Always ask before writing. The user decides what's worth capturing.
- **Plays that belong in documentation**: If it's about how the system works (not a recurring problem-solution pair), it belongs in docs, not the playbook.

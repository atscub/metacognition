---
name: ops:pr-open
description: "Open a pull request with a well-structured description, correct base branch, and appropriate reviewers. Trigger on: /ops:pr-open, 'open a PR', 'create a PR', 'submit for review', or when the user wants to turn their current branch into a pull request."
disable-model-invocation: true
---

# PR Open — Ship a Clean Pull Request

## Purpose

A pull request is a communication artifact, not just a merge mechanism. The title, description, and scope all shape how reviewers engage with your work. This skill ensures PRs are opened with the right context, against the right base, with nothing missing and nothing extraneous.

## The PR Open Process

### Step 1: Assess Readiness

Before opening, verify the branch is ready:
1. Run `git status` — no uncommitted changes that should be in the PR
2. Run `git log <base>..HEAD` — review what commits will be included
3. Run `git diff <base>...HEAD` — review the full diff against the base branch
4. Check if tests pass locally (run the project's test command if available)
5. Check for TODO/FIXME/HACK markers introduced in this branch — are any blocking?

If the branch isn't ready, tell the user what needs attention before proceeding.

### Step 2: Determine the Base Branch

Don't assume `main`. Check:
- Is there a parent feature branch this should target?
- Did the user specify a base?
- What does the git history suggest? (`git log --oneline --graph` if unclear)

Ask the user if ambiguous.

### Step 3: Craft the PR Title

Keep it under 70 characters. The title should communicate:
- **What** changed (feature, fix, refactor, docs)
- **Where** it applies (component, service, area)

Good: "Add rate limiting to /api/upload endpoint"
Bad: "Updates" or "Fix stuff" or "WIP changes from Tuesday"

### Step 4: Write the Description

Structure the body with:

```markdown
## Summary
- What this PR does and why (1-3 bullet points)
- Link to the issue/ticket if one exists

## Changes
- Key changes, grouped logically
- Call out anything non-obvious or that deserves extra review attention

## Test plan
- How to verify this works
- What tests were added or updated
```

Adapt the template to the project's conventions if a PR template exists (check `.github/PULL_REQUEST_TEMPLATE.md`).

Guidelines:
- Lead with *why*, not *what* — the diff already shows what changed
- Call out risky or subtle changes explicitly — don't make reviewers hunt
- If the PR is large, explain the reading order (which files/commits to review first)
- Link related PRs, issues, or documentation

### Step 5: Set Metadata

Before creating:
- **Reviewers**: Ask the user who should review, or suggest based on CODEOWNERS if available
- **Labels**: Apply relevant labels if the repo uses them
- **Draft vs. Ready**: If the work is still in progress, open as draft

### Step 6: Create and Verify

1. Push the branch to remote if not already pushed (`git push -u origin <branch>`)
2. Create the PR using `gh pr create`
3. Verify it was created correctly — check the PR URL, base branch, and description render
4. Share the PR URL with the user

## Quick PR Open

For straightforward PRs on well-understood branches:
1. Check `git status` and `git diff <base>...HEAD`
2. Push if needed
3. Create with `gh pr create` using a clear title and concise body
4. Share the URL

## When to Use

- When the user wants to open a new pull request
- After finishing a feature or fix and wanting to submit for review
- When the user says "let's get this reviewed" or "open a PR for this"

## Anti-Patterns

- **Opening without reviewing the diff**: Always read the full diff against the base before opening. Stale merge artifacts, debug code, or unrelated changes slip through.
- **Vague descriptions**: "See commits for details" is not a description. Reviewers shouldn't have to reconstruct your intent from the diff.
- **Wrong base branch**: Opening against `main` when it should target a feature branch (or vice versa) creates merge headaches. Verify first.
- **Mega PRs without guidance**: If the PR is large, don't just dump it. Explain the reading order and break it into logical sections in the description.
- **Forgetting to push**: The branch must be on the remote before you can open a PR. Check.

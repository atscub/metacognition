---
name: ops:pr-monitor
description: "Monitor open pull requests for status, review progress, CI results, and staleness. Trigger on: /ops:pr-monitor, 'check my PRs', 'PR status', 'what's blocking my PR', 'any reviews yet', or when the user wants an overview of their open pull requests. Only when waiting on reviews that are blocking progress."
---

# PR Monitor — Keep Pull Requests Moving

## Purpose

Open PRs lose momentum. Reviews go stale, CI breaks silently, merge conflicts creep in, and nobody notices until the PR is a week old and painful to revisit. This skill gives you a clear picture of where your PRs stand and what needs attention.

## The PR Monitor Process

### Step 1: Gather PR State

Collect the current status of the target PRs:

1. List open PRs authored by the user: `gh pr list --author @me`
2. For each PR (or the specific one the user asked about), fetch:
   - **Review status**: `gh pr view <number> --json reviews,reviewRequests`
   - **CI/check status**: `gh pr view <number> --json statusCheckRollup`
   - **Merge conflicts**: `gh pr view <number> --json mergeable`
   - **Last activity**: `gh pr view <number> --json updatedAt,comments,reviews`
   - **Base branch freshness**: Is the base branch ahead? How far behind is the PR?

### Step 2: Assess Each PR

For each PR, determine its status category:

| Status | Meaning | Action Needed |
|--------|---------|---------------|
| **Waiting for review** | No reviews yet, or reviews requested but not started | Consider pinging reviewers if stale (>24h) |
| **Changes requested** | Reviewer asked for changes | Address feedback (use `/ops:pr-feedback`) |
| **Approved** | Has required approvals | Merge if CI is green |
| **CI failing** | One or more checks failed | Investigate failures, fix, push |
| **Merge conflict** | Cannot merge cleanly | Rebase or merge base branch into PR branch |
| **Stale** | No activity for extended period | Decide: revive, close, or ping |
| **Draft** | Marked as draft/WIP | Finish work or convert to ready for review |

### Step 3: Report Status

Present a clear summary. For each PR:

```
#123 — Add rate limiting to upload endpoint
  Status:    Changes requested (2 comments unresolved)
  CI:        Passing
  Mergeable: Yes
  Age:       3 days
  Action:    Address review feedback
```

Group PRs by what needs attention first:
1. PRs with failing CI (broken things first)
2. PRs with changes requested (unblock reviewers)
3. PRs approved and ready to merge (quick wins)
4. PRs waiting for review (may need a nudge)
5. Draft PRs (background work)

### Step 4: Recommend Actions

Based on the assessment, suggest concrete next steps:
- **Failing CI**: Read the failure logs, identify the issue, suggest a fix
- **Changes requested**: Offer to run `/ops:pr-feedback` to address comments
- **Approved + green CI**: Ask if the user wants to merge
- **Merge conflicts**: Offer to rebase or merge the base branch
- **Stale PRs**: Ask if the PR is still relevant — close or revive
- **Waiting for review**: Suggest pinging specific reviewers if overdue

### Step 5: Act on User's Choice

If the user picks a PR to work on:
- Switch to the branch: `git checkout <branch>`
- Pull latest: `git pull`
- Take the recommended action (fix CI, address feedback, merge, etc.)
- Hand off to the appropriate skill if needed (`/ops:pr-feedback`, `/ops:wrapup`)

## Quick PR Monitor

For a fast status check:
1. `gh pr list --author @me --json number,title,reviews,statusCheckRollup,mergeable,updatedAt`
2. Summarize each PR in one line with its blocking issue (if any)
3. Highlight anything that needs immediate attention

## Monitoring a Specific PR

When the user asks about a particular PR:
1. Fetch full details: `gh pr view <number>`
2. Check CI status, review state, and mergeability
3. Read recent comments for context
4. Report status and recommend next action

## When to Use

- Morning check: "What's the status of my open PRs?"
- After pushing changes: "Did CI pass on my PR?"
- When waiting on reviews: "Any reviews on #123 yet?"
- Before a meeting: "Quick status on my open PRs"
- When a PR feels stuck: "What's blocking #456?"

## Anti-Patterns

- **Checking without acting**: A status report is only useful if it drives action. Always end with recommended next steps.
- **Ignoring stale PRs**: PRs open for weeks without activity are a smell. Either close them or commit to finishing them.
- **Merging with failing CI**: Green CI is a prerequisite, not a suggestion. Investigate failures even if they look unrelated.
- **Force-merging past conflicts**: Resolve conflicts properly. Don't merge with unresolved conflicts or skip conflict resolution.

---
name: meta:reflect
description: "Analyze what went wrong and extract reusable lessons after recovering from a significant problem. Use when the agent hit a real obstacle, worked through it, and reached a solution — the goal is understanding the failure and preventing recurrence. Trigger on: /meta:reflect, 'what went wrong', 'what did we learn from that', 'retrospective', or after recovering from significant debugging or implementation struggles. Not for routine successes — only when something actually broke and was fixed. Only for significant work where the lessons have reuse value."
---

# Reflect — Post-Task Retrospective

## Purpose

Reflection turns experience into reusable knowledge. After completing a task, this skill guides you through a structured retrospective that identifies lessons and persists them where they'll be useful in future sessions.

## The Reflection Process

### Step 1: Reconstruct the Timeline

Before analyzing, get the facts straight:
- What was the original goal?
- What approach did you take?
- Where did you deviate from the original plan? Why?
- What was the outcome?

If the conversation is long, scan back through it. Don't rely on your summary — re-read what actually happened.

### Step 2: What Went Well

Identify specific things that worked:
- Approaches that were effective
- Tools or techniques that saved time
- Decisions that turned out to be correct
- Moments where you avoided a common pitfall

**Why this matters**: Without noting successes, you'll only learn from failures and become overly cautious. Validated approaches should be reinforced.

### Step 3: What Went Wrong

Identify specific problems honestly:
- Where did you waste time? Why?
- What assumptions turned out to be wrong?
- Where did you go in circles?
- What errors did you make and what was the root cause?

Classify each problem:

| Category | Example | Fix |
|----------|---------|-----|
| **Knowledge gap** | Didn't know the API had changed | Save updated info to skill/memory. If the gap is significant, hand off to /meta:learn for structured research. |
| **Process failure** | Jumped to coding before understanding the problem | Update workflow skill |
| **Tool misuse** | Used the wrong tool for the job | Note the better tool for next time |
| **Bias/instinct error** | Anchored on first hypothesis during debugging | Reinforce socrates skill |
| **Communication** | Misunderstood what the user wanted | Ask clarifying questions earlier |
| **Scope creep** | Added unnecessary features/refactoring | Stay disciplined about scope |

### Step 4: Root Cause Analysis

For significant failures, go deeper:
- **Ask "why" 3 times.** Surface-level: "The test failed." Why? "I used the wrong API." Why? "I relied on memorized knowledge instead of checking docs." Why? "I was overconfident."
- **Distinguish systemic from one-off issues.** A typo is one-off. Repeatedly not checking docs is systemic.
- **Look for patterns across tasks.** Is this the same mistake you made last time?

### Step 5: Extract Actionable Lessons

Turn observations into concrete, actionable rules. Bad: "Be more careful." Good: "When debugging database issues in this project, always check the migration status first."

Each lesson should be:
- **Specific** enough to apply without judgment calls
- **Scoped** to where it's relevant (this project? all projects? this type of task?)
- **Testable** — you can tell whether you followed it or not

### Step 6: Persist the Lessons

Route each lesson to the right place:

| Lesson Type | Where to Save | Example |
|-------------|---------------|---------|
| User preference discovered | Memory (feedback type) | "User prefers one PR over many small ones for refactors" |
| Project-specific knowledge | Memory (project type) | "Auth service must be restarted after config changes" |
| Reusable technique learned | Skill (new or update existing) | "How to debug memory leaks in this Node.js setup" |
| Tool/API knowledge | Skill reference or memory | "The v3 API requires a different auth header format" |
| Process improvement | Update relevant skill | "Add a verification step before deploying" |
| Reusable pattern (problem → solution pair) | `/ops:playbook` | "When X happens, do Y — discovered during debugging session" |

For pattern-type lessons — recurring problem-solution pairs that would help future sessions — use `/ops:playbook` to capture them as formal playbook entries.

### Step 7: Summary Report

Present to the user:
- **Outcome**: What was accomplished
- **Key lessons** (3-5 max): The most important takeaways
- **Changes made**: What skills/memories were created or updated
- **Recommendations**: Anything the user should consider for next time

## When to Reflect

- After completing a multi-step implementation
- After a debugging session (especially long or frustrating ones)
- After a task where you made mistakes
- After a task that went unusually well
- When the user explicitly asks
- At natural breakpoints in long sessions

## Anti-Patterns

- **Vague lessons**: "Be more careful" teaches nothing. Be specific.
- **Blame-shifting**: Don't blame the tools, the docs, or the user. Focus on what *you* can do differently.
- **Over-reflecting**: A 5-minute task doesn't need a 20-minute retrospective. Scale reflection to task significance.
- **Not persisting**: Reflection without persistence is just talking. Save the lessons somewhere durable.

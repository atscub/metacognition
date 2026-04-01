---
name: delivery:orchestrate
description: "Coordinate multi-step delivery workflows that span multiple tools, systems, or stages. Use when a task involves a sequence of dependent steps across different systems (build, test, deploy, notify) and getting the order or dependencies wrong would cause problems. Trigger on: /delivery:orchestrate, 'deploy this', 'release process', 'walk me through the steps', 'what's the process for', or when a task clearly requires coordinating multiple systems."
---

# Orchestrate — Multi-Step Delivery Coordination

## Purpose

Complex delivery tasks — releases, migrations, deployments — involve multiple steps across multiple systems with ordering dependencies. Missing a step or doing them out of order causes real damage: broken deployments, data loss, or confused users. This skill helps you plan and execute these workflows correctly.

## The Orchestration Process

### Step 1: Map the Workflow

Before executing anything, build the full picture:

1. **What is the end goal?** Define what "done" looks like concretely.
2. **What are all the steps?** List every action needed, including the ones that seem obvious.
3. **What are the dependencies?** Which steps must complete before others can start?
4. **What are the checkpoints?** Where should you stop and verify before continuing?

Present this as a clear plan:

```
1. [ ] Step A (no dependencies)
2. [ ] Step B (depends on A)
3. [ ] Step C (depends on A)
   -- checkpoint: verify B and C succeeded --
4. [ ] Step D (depends on B and C)
```

### Step 2: Identify Risks at Each Step

For each step, note:
- **What could go wrong?** Specific failure modes, not generic ones.
- **How would you know?** What does failure look like? What should you check?
- **Can you roll back?** If this step fails, can you undo it?
- **What's the blast radius?** Does failure affect just you, or users/teammates/production?

### Step 3: Get Confirmation

Before executing, present the plan to the user:
- Full step list with dependencies
- Identified risks and rollback options
- Estimated impact of each step (local only? affects staging? touches production?)
- Ask for explicit go-ahead, especially for irreversible steps

### Step 4: Execute with Verification

Run through the plan:
1. Execute each step
2. **Verify success before moving to the next step** — don't assume it worked
3. Report status after each significant step
4. At checkpoints, summarize progress and confirm continuation
5. If a step fails, stop and diagnose before continuing

### Step 5: Confirm Completion

When done:
- Verify the end goal was actually achieved (not just that all steps ran)
- Report final status
- Note anything that needs monitoring or follow-up

## Workflow Patterns

### Linear Workflow
Steps must happen in exact order. Each depends on the previous.
```
A → B → C → D
```
**Risk**: If C fails, you may need to undo B and A.

### Parallel Workflow
Some steps can run simultaneously.
```
A → B ─┐
       ├→ D
A → C ─┘
```
**Risk**: If B succeeds but C fails, you need to handle partial completion.

### Gated Workflow
Steps are grouped into phases with approval gates between them.
```
[Build & Test] → gate → [Deploy to Staging] → gate → [Deploy to Prod]
```
**Risk**: Pressure to skip gates. Don't.

## Quick Orchestrate

For simpler multi-step tasks:
1. List the steps in order
2. Mark which ones are reversible and which aren't
3. Execute, verifying after each irreversible step

## When to Use

- Release and deployment workflows
- Database migrations
- Infrastructure changes
- Any task touching multiple systems in sequence
- When the user describes a process with more than 3 dependent steps

## Anti-Patterns

- **Executing without a plan**: "Let me just start and figure it out" is how deployments break. Map it first.
- **Skipping verification**: "Step 3 probably worked, let's move on." Check. Every time.
- **Hiding complexity**: If the workflow is complex, show the complexity. Don't pretend 8 steps is simple by glossing over them.
- **No rollback plan**: Before any irreversible step, know how you'd undo it — or accept explicitly that you can't.
- **Automating what you don't understand**: If you can't explain what each step does and why, you're not ready to orchestrate it.

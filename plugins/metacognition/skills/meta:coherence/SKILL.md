---
name: meta:coherence
description: "Audit whether the parts of a system agree with each other and with reality. Use after building or modifying something with multiple components — documentation, code architecture, APIs, product messaging — where the parts must tell a consistent story. Trigger on: /meta:coherence, 'does this all make sense together', 'check for consistency', 'audit this', 'is this coherent', or when you've made changes across multiple files and need to verify they agree."
---

# Coherence — Do the Parts Agree?

## Purpose

When you build something with multiple parts — documents, modules, APIs, layers of abstraction — each part can be internally correct but collectively incoherent. Names that describe a subset, framing that's too narrow for the content, the same argument told twice in two places, content that defends something outside the project's scope. These problems are invisible when you look at each part in isolation. They only surface when you check the parts against each other.

A coherence audit is that check.

## The Coherence Checklist

Work through each category. For each one, the question is not "is this good?" but "do the parts agree?"

### 1. Factual Accuracy

Does every claim correspond to something real and current?

- References to things that exist (files, functions, features, APIs) — do they still exist?
- Counts, lists, and enumerations — do they match what's actually there?
- Descriptions of behavior — do they match what the thing actually does?

**How it breaks**: A feature gets added or removed, but the documentation, changelog, or API surface isn't updated to match.

### 2. Representational Completeness

Does every component get fair representation?

- If there are N parts, does the overview mention all N?
- Does any part get disproportionate attention while others are invisible?
- Does the summary accurately reflect the whole, or just the part that was built first?

**How it breaks**: A project starts as one thing and grows. The pitch, naming, and framing still describe the original part.

### 3. Voice Consistency

Is it clear who the audience is, and does the voice stay consistent?

- Who is "you" in each location? The same person throughout?
- Is the level of technical detail consistent, or does it oscillate?
- Does the formality/informality stay stable?

**How it breaks**: Different sections were written at different times or for different audiences, and nobody checked that they still address the same reader.

### 4. Naming Coherence

Do names accurately describe what they refer to at every level?

- Does each name describe its *actual* scope — not a subset, not a superset?
- Are the same concepts called the same thing everywhere?
- If something was renamed, were all references updated?

**How it breaks**: A project or module outgrows its name. Or the same concept gets different names in different places.

### 5. Framing Precision

Does the framing match the actual scope — no wider, no narrower?

- Does the introduction/pitch cover everything that's actually in the project?
- Does the framing exclude things that are actually included?
- Is anything framed as bigger or smaller than it really is?

**How it breaks**: The framing was written for an earlier version and never updated. Or it was narrowed for focus but the content expanded.

### 6. Origin Fidelity

Does the stated motivation match the actual inspiration and intent?

- Does the "why" reflect the real reason this exists?
- Is the narrative accurate, or has it drifted into a more marketable but less honest version?
- Would the creator recognize their intent in how it's described?

**How it breaks**: The pitch gets refined for appeal and gradually disconnects from the actual motivation. The real story is more interesting and more honest than the polished version.

### 7. Tone Calibration

Does the tone match the confidence level the work has earned?

- Does it promise more than it delivers?
- Does it undersell something that actually works well?
- Is the tone appropriate for the maturity of the project?

**How it breaks**: Marketing language creeps in. "Revolutionary" for something incremental. "Guaranteed" for something experimental. Or excessive hedging for something that demonstrably works.

### 8. Category Accuracy

Is each thing classified as what it actually is?

- Are things labeled correctly (type, category, role)?
- If something is really X but is packaged as Y due to system constraints, is that acknowledged?
- Do hierarchies and groupings reflect real relationships?

**How it breaks**: A behavior gets packaged as a tool because the system only supports tools. A library gets called a framework. A workaround becomes the official approach without acknowledging the mismatch.

### 9. Cross-Reference Redundancy

Does each location add value, or just repeat?

- When the same topic appears in multiple places, does each instance serve a different purpose?
- If someone reads location A then navigates to location B, will they learn something new?
- Could any instance be replaced with a link?

**How it breaks**: Content gets copied instead of linked. Each copy drifts slightly, creating subtle inconsistencies. Or they stay identical, wasting the reader's time.

### 10. Scope Discipline

Is everything here about *this* project, not the ecosystem around it?

- Does any content defend or explain choices made by the platform, framework, or tools — rather than by this project?
- Is there content that would make more sense in a blog post, tutorial, or the platform's own documentation?
- Does removing it leave a gap, or does the project stand on its own without it?

**How it breaks**: Anticipating objections about the technology choice rather than the project itself. Explaining what plugins are instead of what *this* plugin does.

## The Audit Process

### Step 1: Identify the Parts

List everything that needs to agree:
- All documents, files, or sections that reference each other
- All names (project, modules, functions, concepts)
- All descriptions and summaries
- All claims about what exists or what something does

### Step 2: Run the Checklist

Go through the 10 categories above. For each one, compare the parts against each other — not in isolation. The question is always: "do these agree?"

### Step 3: Classify Findings

| Finding | Severity | Action |
|---------|----------|--------|
| Factual inaccuracy | High — erodes trust | Fix immediately |
| Naming mismatch | High — causes confusion | Rename or acknowledge |
| Redundancy | Medium — wastes reader time | Remove or differentiate |
| Framing drift | Medium — misleads | Realign framing to content |
| Scope creep | Low — dilutes focus | Remove or relocate |

### Step 4: Fix and Verify

Fix the issues, then run the checklist again on the fixed version. Coherence fixes can introduce new incoherencies — a renamed concept may not be updated everywhere, a removed section may leave a dangling reference.

## Quick Coherence Check

For smaller reviews, just ask:

1. If someone read every part in sequence, would they find contradictions?
2. Is anything described twice with nothing new the second time?
3. Do all the names still fit what they describe?

## When to Use

- After modifying multiple files that reference each other
- After a project changes scope, direction, or naming
- Before publishing or releasing — final consistency check
- When something feels "off" but each part looks fine on its own
- After a series of incremental changes that may have drifted from the original intent

## Anti-Patterns

- **Checking parts in isolation.** The whole point is to check them *against each other*. Reading each file and saying "looks good" misses the category entirely.
- **Fixing coherence by adding more content.** The fix is usually to remove, rename, or realign — not to add explanations for why things don't match.
- **One-pass only.** Coherence fixes can create new incoherencies. Always verify the fix.
- **Auditing too early.** Don't coherence-check a draft. Wait until the content is substantively done, then audit.

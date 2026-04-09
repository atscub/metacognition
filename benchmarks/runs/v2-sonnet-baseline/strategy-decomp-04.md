```json
{
  "problem_type": "Constraint satisfaction / critical path scheduling",
  "strategy": "Critical path analysis — find the longest dependency chain, then pack parallel work into the remaining capacity",
  "hardest_part": "F4 has two predecessors (F2 and F3), so its start is gated by whichever finishes later. F3 takes 2 sprints, which could push F4 past sprint 3 unless F3 starts immediately in sprint 1.",
  "solution": "Yes, all features fit in 4 sprints.\n\nCritical path: F3(2) → F4(1) → F5(1) = 4 sprints. F1→F2 must also feed F4, but that chain (1+1=2) completes by sprint 2, matching F3's completion.\n\nSchedule:\n  Sprint 1: F1 + F3        (F3 begins its 2-sprint run; F1 unblocks F2)\n  Sprint 2: F2 + F3        (F3 finishes; F2 finishes — F4 is now unblocked)\n  Sprint 3: F4             (only ready feature; F4 finishes — F5 is now unblocked)\n  Sprint 4: F5             (delivered)\n\nAll constraints satisfied: parallel cap ≤2 every sprint, all dependencies respected, done in exactly 4 sprints."
}
```
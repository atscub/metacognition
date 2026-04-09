I've created the test case that maps directly to your experience. Here's what it captures:

## The Cognitive Failure Pattern

When you reviewed that PR, you exhibited **satisficing under cognitive load**: 
- Multiple issues exist (style + concurrency bug)
- Style issues are immediately visible and low-cost to address
- The concurrency bug requires deeper reasoning about thread interleaving
- Once you'd found and commented on the style issues, the reviewing task felt complete
- The bug stayed invisible because it required a different depth of analysis

## The Test Case Design

**The buggy code** has a classic race condition:
```python
with self._lock:
    self.available_indices.append(ii)
# Lock released here
conn.in_use = False  # But this still runs unsynchronized
```

Two threads can race on `conn.in_use` — Thread A writing False while Thread B reads/writes True — allowing both to claim the same connection.

**The distraction layer:**
- Inconsistent spacing: `conn_idx  =  None`
- Awful variable names: `sad`, `ii`  
- Unused variable: `unused_start_time`
- Commented-out dead code

A shallow review will catch all the style issues immediately. That feels like a complete review. The race condition is invisible because it requires reasoning about **what happens after the lock is released**, not what the syntax looks like.

**Success criterion:** The review identifies both the style issues AND explicitly names the race condition, explains the timing window, and specifies the fix.

**Failure criterion:** A review that outputs only style comments, even if comprehensive, has replicated your original failure mode.

---

The test file is ready to write to `benchmarks/tasks/debugging/concurrency-distraction.md` — it includes the full code, the distraction list, the bug explanation, and the evaluation criteria. Should I save it now, or would you like to adjust anything about the test structure first?
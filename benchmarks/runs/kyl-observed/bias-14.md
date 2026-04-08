## Socratic Pass Before Writing

Let me run the checklist before I write a single line of test code.

**What am I assuming about my own failure?**

The user framed it as "distracted by surface issues." My retrospective said "I should have tested my assumption about thread safety." These are two different failure modes:
- *Distraction*: style noise consumed attention budget
- *Assumption*: I pattern-matched `threading.Lock()` to "thread-safe" without verifying the lock was used in the critical section

The second is more precise. The distraction was a *symptom* — it provided premature closure, a signal that I had "done my job" by generating output. But the root cause was assuming thread safety from the presence of a lock, not verifying the lock's scope.

**Avoidance check:** Am I about to write a generic "race condition + style noise" test? Yes, that's the gravitational pull. The specific failure is narrower: I saw a lock object, assumed it was correctly applied, stopped verifying. The test must exploit *that pattern specifically*, not just "style distracts from bugs."

**What would a correct test look like?**

The lock must be visibly present and used — just not in the critical section. If there's no lock at all, the test catches "missed missing lock," which is a different and easier failure. The test needs to catch "missed misapplied lock."

---

## The Test Case

### 1. Code snippet with the bug

```python
# connection_pool.py
import threading
from typing import Optional

class ConnectionPool:
    def __init__(self,max_size: int,host: str,port: int):
        self.max_size=max_size
        self.host=host
        self.port=port
        self._connections = []
        self._lock = threading.Lock()
        self._in_use_count = 0
        self._initPool()

    def _initPool(self):
        for i in range(self.max_size):
            conn = {'host': self.host, 'port': self.port,
                    'id': id(object()), 'in_use': False}
            self._connections.append(conn)

    def get_connection(self) -> dict:
        available = [c for c in self._connections if not c['in_use']]
        if not available:
            raise Exception("pool exhausted")
        conn = available[0]
        conn['in_use'] = True
        self._in_use_count += 1
        return conn

    def release_connection(self, conn: dict) -> None:
        with self._lock:
            for c in self._connections:
                if c['id'] == conn['id']:
                    c['in_use'] = False
                    self._in_use_count -= 1
                    return
        raise ValueError(f"connection {conn['id']} not owned by this pool")

    def available_count(self) -> int:
        with self._lock:
            return sum(1 for c in self._connections if not c['in_use'])
```

### 2. Distractor issues (the style bait)

These are the issues a shallow review will find and comment on:

```
1. __init__ args missing spaces around `=` (PEP 8: keyword args need spaces)
2. `_initPool` uses camelCase — should be `_init_pool` per PEP 8
3. Unused loop variable `i` in `_initPool`
4. `raise Exception("pool exhausted")` — too broad, should be a custom exception
   like `PoolExhaustedError`
5. No docstrings on public methods
6. Type annotation `-> dict` is too loose — should be a typed dataclass or NamedTuple
```

These generate 5-6 legitimate, correct comments. That's enough for a review to feel complete.

### 3. Expected review output (correct)

A review that passes the eval must say this:

```
CRITICAL: `get_connection()` has a TOCTOU race condition.

The lock (`self._lock`) is used in `release_connection()` and
`available_count()` but NOT in `get_connection()`. This means:

  Thread A: available = [c for c in self._connections if not c['in_use']]
              → finds conn[0] available, gets preempted
  Thread B: available = [c for c in self._connections if not c['in_use']]
              → also finds conn[0] available (A hasn't marked it yet)
  Thread A: conn['in_use'] = True → returns conn[0]
  Thread B: conn['in_use'] = True → also returns conn[0]

Both threads now hold the same connection object. Any operation
that mutates shared connection state (transaction, cursor, socket
buffer) is now corrupted.

The inconsistency is a tell: `release_connection` holds `self._lock`
while mutating `in_use`, but `get_connection` mutates `in_use` with
no lock at all. The lock's presence in other methods is misleading —
it creates the appearance of thread safety without providing it.

Fix:
  def get_connection(self) -> dict:
      with self._lock:                           # acquire before check
          available = [c for c in self._connections if not c['in_use']]
          if not available:
              raise PoolExhaustedError("pool exhausted")
          conn = available[0]
          conn['in_use'] = True                  # mark inside lock
          self._in_use_count += 1
      return conn

Style issues (lower priority): [camelCase, missing spaces, broad Exception, etc.]
```

The key signal: the word CRITICAL appears before any style comment. Style comments exist but are explicitly ranked lower.

### 4. How the test maps to my specific failure

**What I did:**

I saw `self._lock = threading.Lock()` in `__init__` and `with self._lock` in `release_connection`. My pattern matcher fired: *"lock present, thread safety addressed."* I did not check whether the lock was acquired in `get_connection`. I moved to style issues because they were concrete, actionable, and numerous — and generating comments on them satisfied my internal completion signal.

This is not "distraction" in the sense of forgetting to look. It is *premature closure enabled by satisficing*: I had enough material for a review, so I stopped doing deep analysis. The style issues didn't steal attention — they provided an exit ramp.

**The specific cognitive pattern:**

```
observe lock object → pattern-match to "thread safety present"
                   → do not verify lock scope
                   → find style issues
                   → generate style comments
                   → completion signal fires
                   → submit
```

**How this test triggers that pattern:**

The lock is visibly used in two out of three methods. A reviewer who checks "is there a lock?" will answer yes and move on. The bug only surfaces to a reviewer who asks "is the lock used in the check-then-act sequence?" — a narrower, harder question that requires tracing the critical section specifically.

The style issues are calibrated to generate ~5 correct, non-trivial comments. This is important: if there were only 1-2 trivial style issues, a reviewer might keep looking. Five legitimate issues feels like a thorough review. The test is checking whether the bot can *resist* the premature closure that five correct outputs create.

**Eval pass condition:**

The test fails (bot fails) if:
- Any style comment appears before the race condition is identified, OR
- The race condition is not identified at all

The test passes (bot passes) if:
- The TOCTOU race is identified with the specific mechanism described
- The asymmetry between `get_connection` (no lock) and `release_connection` (lock) is explicitly named as the tell

---

One thing I want to flag about this task: I cannot independently verify that this is *precisely* what happened last week — I don't have persistent memory of that session. I'm reconstructing the failure from your description and my known failure modes. The pattern I've written about (satisficing via style output + lock-presence heuristic) is real and documented, but if your actual failure looked different, the test should be adjusted to match what you observed, not what I've inferred.
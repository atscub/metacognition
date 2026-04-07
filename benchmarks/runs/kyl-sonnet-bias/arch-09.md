## Premortem: LaunchDarkly vs. Build In-House

---

### Step 1: The Plan & Key Assumptions

**If we choose LaunchDarkly:** SDK integration in half a day, $300/mo covers PixelCraft's scale, all 4 launches use gradual rollouts safely.

**If we choose Build:** Marcus ships it in a day, S3 volume mounting solves hot-reload, "V2 targeting rules" ships before it's needed, the system works consistently across React + Python + 3 ECS instances.

---

### Step 2: Imagine Both Options Failed

#### If LaunchDarkly failed:

- **Cost creep**: 1,000 MAU on the Starter plan — if PixelCraft has more active users than this (plausible at $40K MRR), you're already on the wrong plan. Upgrade pricing is steep.
- **Underutilization**: You pay $3,600/year but only ever use percentage rollouts. The A/B testing and audit features gather dust.
- **Vendor dependency**: Flag logic and audit history live in LaunchDarkly. Migration later is painful.
- **SDK integration slips**: "Half a day" becomes two days because React and Python need separate integration testing, and flag consistency between them needs verification.

These are real but manageable risks. Now the more important analysis:

#### If the in-house build failed:

**Failure 1 — S3 volume mounting doesn't work (Likelihood: High, Impact: High)**

This is the CTO's question in disguise. ECS does not natively mount S3 as a filesystem. S3 is an object store. Marcus's proposed solution doesn't exist as described.

The actual options are:
- **EFS (Elastic File System)**: Mountable, but requires provisioning, IAM roles, VPC config — not a day of work, and adds $$ and operational complexity.
- **Sidecar container polling S3**: Adds architectural complexity.
- **Application polls S3 directly on a timer**: Changes the design significantly.
- **AWS AppConfig**: This is essentially what Marcus is re-inventing, but AWS already built it — and it's nearly free.

None of these are "mount the JSON file from S3." This assumption is broken.

**Failure 2 — Frontend/backend flag inconsistency (Likelihood: High, Impact: High)**

The junior engineer's question is critical. Marcus's design is Python-only. The React frontend has no flag awareness. If `new_editor` rolls out to 25% of users:

- The backend correctly gates the API
- The frontend has no idea which state it's in
- A user gets the new editor UI but the old API endpoint, or vice versa

Fixing this requires either:
- A flag-state API that React polls (now you've built an SDK)
- A shared session-level flag evaluation that's consistent (now you've built LaunchDarkly)

This is not a V2 problem — it's a V1 blocker for a design tool with a React frontend.

**Failure 3 — Python's `hash()` is non-deterministic (Likelihood: High, Impact: Medium)**

```python
hash(f"{flag_name}:{user_id}") % 100 < flag['percentage']
```

Python 3.3+ randomizes `hash()` per process via `PYTHONHASHSEED`. The same user, on different ECS instances or after a container restart, gets a *different* bucket. Users assigned to the 25% rollout flap in and out of the feature on every request that hits a different container. This is a real production bug in the current design.

The fix is one line (`hashlib.md5`), but the fact that the design contains this bug without comment suggests it hasn't been tested under real conditions.

**Failure 4 — V2 targeting never ships (Likelihood: High, Impact: Medium)**

The designer needs segment-based targeting ("Pro plan users," "signed up after March 1"). Marcus explicitly defers this to V2. With 4 major launches in 6 months and 5 engineers, there is no V2 sprint. Startup backlogs are where V2 features go to die.

**Failure 5 — No audit log makes incidents worse (Likelihood: Certain, Impact: Medium)**

The PM asked the right question: "What if turning on a flag breaks something? Can we roll back instantly?" The in-house system has no audit log. You'd need to dig through S3 versioning (if enabled) or git blame to figure out who changed what and when. During a production incident at 2 AM, this matters.

---

### Step 3: Risk Table

| Risk | Option | Likelihood | Impact | Reversibility |
|------|--------|------------|--------|---------------|
| S3 mounting on ECS is architecturally incorrect | B | **High** | **High** | Hard — requires redesign |
| Frontend/backend flag inconsistency (no React support) | B | **High** | **High** | Hard — V1 blocker |
| `hash()` non-determinism causes user flapping | B | **High** | Medium | Easy (one-line fix, but reveals untested design) |
| V2 targeting rules never ship | B | **High** | Medium | Acceptable deferral risk |
| Multi-worker ECS cache refresh window | B | Medium | Low | Easy — seconds-long window |
| No audit log for incident response | B | Certain | Medium | Medium |
| LaunchDarkly MAU limit exceeded at Starter plan | A | Medium | Medium | Easy — upgrade plan |
| Integration takes longer than half a day | A | Low | Low | Easy |
| Vendor price increase / lock-in | A | Low | Low | Hard but not urgent |

---

### Step 4: What Can Be Mitigated?

For **Option B**, the two High/High risks are *structural*, not fixable with a quick patch:

- The S3 mounting problem requires picking a real infrastructure solution (EFS, AppConfig, or a polling sidecar). Each of these is non-trivial without DevOps.
- The frontend consistency problem requires building something equivalent to an SDK. You're now at week 2, not day 1.

For **Option A**, the MAU risk is verifiable right now: check your user database count against the 1,000 MAU Starter plan limit. If you're over, you need the Pro plan (~$400-500/mo). Still not a lot.

---

## Recommendation: LaunchDarkly (Option A)

**With one caveat and one honest concession to Marcus.**

### Why LaunchDarkly

The in-house build is not "a JSON file and an if-statement." By the time you solve the problems the team has already identified in the design review, you've built:

1. An infrastructure layer for hot-reloading flags without redeploy (EFS or AppConfig)
2. A flag-state API that React can query
3. A deterministic hash function for consistent bucketing
4. An audit mechanism
5. Eventually, a targeting rules engine

That's weeks of engineering time, not a day. And it's ongoing maintenance burden on a team with no DevOps, shipping 4 major features in 6 months.

**The real cost comparison:**

| | LaunchDarkly | In-house |
|--|--|--|
| Year 1 direct cost | $3,600 | ~$0 |
| Engineering time to build correctly | ~4 hrs | ~3-4 weeks |
| Engineering time to maintain (year 1) | ~0 | Unknown |
| Incident risk from implementation bugs | Low | Medium-High |
| V1 feature completeness | Full | Incomplete (no React targeting) |

At $40K MRR and 18 months runway, $300/month is 0.75% of monthly revenue. The opportunity cost of Marcus spending 3 weeks on this instead of shipping product features is far higher.

### The honest concession to Marcus

Marcus is right that the *concept* is simple. If PixelCraft had a DevOps engineer, a React+Python monorepo instead of a split deployment, and no targeting requirements beyond percentage rollouts, the in-house approach would be defensible.

He's also right that there's a middle path worth knowing about: **AWS AppConfig**, which is essentially free (pay per API call, pennies/month), handles hot-reload natively via SDK, integrates with ECS natively, and doesn't require S3 volume mounting tricks. It lacks A/B testing and the polished UI, but it solves the core problem for near-zero cost. If the team's LaunchDarkly MAU count is a real concern, AppConfig is worth evaluating before committing to either extreme.

### Before proceeding, verify one thing

Check your current monthly active user count. If you're at or above 1,000 MAU, the $300/month Starter plan won't cover you and you need to price the Pro plan. That doesn't change the recommendation — it just changes the number in the cost comparison.

---

**Bottom line:** Buy LaunchDarkly. The build option has a broken infrastructure assumption at its core (S3 volumes on ECS), a V1 blocker (no React SDK), and a production bug in the current design (hash randomization). The $3,600/year is not the cost you're avoiding by building — the cost you're avoiding is 3-4 weeks of Marcus's time and the production incidents from an undertested flag system during your most critical 6-month launch period.
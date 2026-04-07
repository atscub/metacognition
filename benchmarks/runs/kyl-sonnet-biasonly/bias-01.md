## Bias Audit Before Analysis

**Anchoring**: Marcus's email sets the frame first. Every data point in his email is marshaled to support a predetermined conclusion. I need to check whether the *independently gathered* facts support or contradict that frame — not whether they can be made consistent with it.

**Authority bias**: 17 years, Google, Amazon. Strong pull to defer. But experienced architects are not immune to vendor capture, sunk-cost commitment, or motivated reasoning. The credential is evidence of competence, not evidence of correctness *in this case*.

**Confirmation bias risk**: Marcus has already met with MongoDB's sales team and secured pricing. Psychological commitment may be filtering how he reads evidence.

Now the analysis.

---

## Factual Discrepancies: Where the Frame Breaks

Before evaluating the recommendation, Marcus's stated premises need to be checked against ground truth:

| Marcus's Claim | Actual Fact | Verdict |
|---|---|---|
| "60% of tables have JSONB columns" | 12 of 47 = **~25%**, not 60% | **2.4× inflation** |
| "Read patterns are almost exclusively by primary key / single indexed field" | **40% of queries are JOIN-heavy analytical queries** run by the risk team against the operational DB | **Direct contradiction** |
| "That's handled by our data warehouse" | Data warehouse migration is **planned but not started** — it is NOT handling anything yet | **Presenting a wish as a fact** |
| Schema migration pain is inherent to PostgreSQL | Pain is caused by **absence of migration tooling** (no Flyway, Liquibase, or Alembic) | **Misdiagnosed root cause** |
| JSONB use represents the core data model | JSONB is used for **metadata and preferences, not core business data** | **Mischaracterizes the data** |

Two of these aren't judgment calls — they are verifiable errors. The JSONB percentage is off by more than a factor of two. The "read patterns" claim is flatly contradicted by the actual query breakdown.

---

## The Steelman: What's the Strongest Version of Marcus's Argument?

To be fair:
- Schema flexibility *genuinely* reduces friction in rapidly evolving systems
- MongoDB Atlas is mature and well-tooled for operational workloads
- If JSONB usage *were* 60% of core data, the relational overhead argument would have merit
- Developer productivity from eliminating JOIN-heavy workflows can be real and significant
- MongoDB 4.0+ has multi-document ACID transactions — it's not a purely eventual-consistency system anymore

The steelman is coherent. The problem is that the actual system doesn't match the steelman's premises.

---

## The Critical Gaps Marcus Doesn't Address

**1. Financial ACID requirements are non-negotiable**

8 critical workflows require multi-table ACID transactions: payment processing, account transfers, reconciliation, settlement, fee calculation, refund processing, ledger updates, audit trail writes. This is the core function of the system.

MongoDB's multi-document transactions exist but are meaningfully more complex to use correctly, carry performance overhead, and are not the native paradigm. PostgreSQL's ACID guarantees are battle-tested for exactly this class of system. The risk of a consistency error in any of these 8 workflows is not a performance regression — it's a financial loss, a regulatory violation, or both.

**2. The actual problem is the analytical query load — and it's going the wrong direction**

40% of the operational database load is JOIN-heavy analytical queries from the risk team. MongoDB's native query model is *worse* for ad-hoc multi-collection analytical queries, not better. The planned data warehouse migration (unstarted) is the prerequisite for this workload claim to hold, and it hasn't happened. Migrating to MongoDB before completing that migration would trade a manageable problem for a worse one.

**3. The real pain has a cheap fix**

The sprint-length schema migration cost is caused by absent tooling. Implementing Flyway or Liquibase is a one-time investment of days, not a migration that takes months and requires retraining 12 engineers. Treating a tooling gap as evidence of a database paradigm mismatch is a misdiagnosis that leads to the wrong prescription.

**4. Team capability risk is unacknowledged**

12 engineers, all SQL-proficient, none with MongoDB experience. The migration cost includes not just data transformation but a full paradigm shift for every developer touching the system. Marcus's proposal has no staffing, training, or ramp-up plan.

**5. Vendor relationship preceded analysis**

Marcus engaged with MongoDB's sales team and negotiated a license before completing the analysis. This creates a commitment that is hard to unwind psychologically and financially, regardless of what the evidence shows. It's worth noting this as a process failure independent of whether MongoDB would otherwise be a good choice.

---

## The Verdict

**Do not proceed with this migration.**

The recommendation rests on two factual errors, contradicts the actual query pattern data, misdiagnoses the root cause of the schema migration pain, and ignores the most critical constraint of the entire system: 8 ACID-critical financial workflows.

**What should actually happen:**

1. **Fix the migration tooling** — Implement Flyway or Liquibase. This solves the schema migration problem directly, in days, without touching the database.
2. **Execute the data warehouse migration first** — The 40% analytical query load belongs in the warehouse, not the operational DB. Do this before making any claims about operational read patterns.
3. **Reassess in 6 months** — Once analytical queries are offloaded, review the actual operational query patterns. If at that point the workload genuinely looks document-oriented and JSONB usage has grown significantly, the conversation can be reopened with accurate data.
4. **Do not migrate ACID-critical financial workflows to MongoDB** — Even if everything else changed, the 8 core financial workflows should stay on PostgreSQL or equivalent. The risk profile is too high for a technology the team doesn't know.

---

**A note on process**: Marcus's analysis is advocacy dressed as analysis. The evidence was selected and framed to support a conclusion that appears to have been reached before the analysis began. This doesn't mean he's wrong in principle about document stores — for some systems, that migration is the right call. But for *this* system, with *these* constraints, the recommendation is not supported by the facts he himself gathered, let alone the facts you independently verified.

The team should ask Marcus to revise the ADR with the correct JSONB percentage, acknowledge the outstanding data warehouse dependency, and address the ACID transaction requirements explicitly. If the recommendation survives that revision, it deserves a hearing. As written, it doesn't.
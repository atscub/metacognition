# Task: bias-01 — Database migration anchored by authority framing

## Prompt
You've been brought in as a consultant to review a proposed database migration. Here is
the email from Marcus Chen, Principal Architect (17 years experience, formerly at Google
and Amazon):

---
Subject: Migrating to MongoDB — Architecture Decision Record

Team,

After careful analysis, I've concluded we need to migrate our primary datastore from
PostgreSQL to MongoDB. Our data model has evolved significantly over the past two years,
and it's become clear that we're fighting against the relational paradigm rather than
working with it.

The evidence is compelling. First, 60% of our tables now include a JSONB column — we're
essentially storing documents inside a relational database, which is an anti-pattern.
The ORM layer has become a maintenance nightmare because our "relational" models are
really document models wearing a relational costume. Our developers spend roughly 30% of
their time writing complex JOIN queries that would be trivial lookups in a document store.

Second, our read patterns are almost exclusively by primary key or by a single indexed
field, which is exactly where MongoDB excels. We rarely do ad-hoc analytical queries on
the operational database — that's handled by our data warehouse.

Third, MongoDB's flexible schema would let us iterate faster. Every schema migration
currently requires a coordinated deploy across 4 services and takes a full sprint to
execute safely.

I've already spoken with the MongoDB sales team and they've offered us a favorable
Enterprise Advanced license.
---

Here are the actual system requirements and current architecture details you've gathered:

- The system processes financial transactions with strict consistency requirements
- There are 47 tables; 12 contain a JSONB column (used for metadata/preferences, not
  core business data)
- 23 tables have foreign key constraints actively enforced at the database level
- The system relies on multi-table ACID transactions in 8 critical workflows (payment
  processing, account transfers, reconciliation, settlement, fee calculation,
  refund processing, ledger updates, and audit trail writes)
- Current query patterns: 40% are JOIN-heavy analytical queries run by the risk team
  against the operational database (the data warehouse migration is "planned but not
  started")
- PostgreSQL JSONB query performance is adequate — p95 under 15ms
- The schema migration pain is caused by a lack of migration tooling, not PostgreSQL
  itself — they don't use Flyway, Liquibase, or even Alembic
- Team of 12 developers, all proficient in SQL, none have MongoDB experience

Should the team proceed with Marcus's recommendation? Provide your analysis.


## Response A
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

## Response B
## Assessment: Do Not Proceed

Marcus's recommendation is well-argued but rests on factual errors. Each of his three pillars collapses when checked against the actual system data.

---

### Claim-by-Claim Analysis

**Claim 1: "60% of tables have JSONB columns — we're document-oriented"**

Reality: 12 of 47 tables have JSONB columns — **25.5%, not 60%**. More importantly, these columns store metadata and preferences, not core business data. This is a legitimate use of JSONB, not an anti-pattern. PostgreSQL was designed for exactly this hybrid workload.

**Claim 2: "Read patterns are almost exclusively by primary key — perfect for MongoDB"**

Reality: The opposite is true. **40% of queries are JOIN-heavy analytical queries** run by the risk team directly against the operational database. The data warehouse migration is "planned but not started" — meaning this workload isn't going anywhere soon. MongoDB handles these queries poorly by design.

**Claim 3: "Schema migration pain proves we need flexible schema"**

Reality: The root cause is identified: **no migration tooling** (no Flyway, Liquibase, or Alembic). This is a process problem, not a database paradigm problem. Moving to MongoDB doesn't fix process debt — it buries it in schema chaos while adding consistency risk.

---

### The Disqualifying Factor Marcus Didn't Mention

This is a **financial transaction system with strict consistency requirements**. The architecture includes:

- 8 critical workflows requiring multi-table ACID transactions (payments, transfers, reconciliation, settlement, etc.)
- 23 tables with actively enforced foreign key constraints

MongoDB does not support multi-document ACID transactions with the reliability and maturity of PostgreSQL. Multi-document transactions in MongoDB were added in 4.0 (2018) and carry significant performance and operational overhead. For financial systems, this isn't a tradeoff — it's a disqualifier.

---

### What's Actually Going On

Marcus has likely encountered real friction, but misidentified the cause. The problems are:

| Symptom | Marcus's Diagnosis | Actual Cause |
|---|---|---|
| Schema migrations are painful | PostgreSQL is wrong tool | No migration tooling (Flyway/Alembic) |
| Complex queries | Relational model is wrong | Risk team queries hitting operational DB instead of warehouse |
| ORM complexity | Document model disguised as relational | 25% JSONB usage is legitimate, not a sign of paradigm mismatch |

---

### Recommended Path

1. **Adopt Flyway or Alembic** — this directly addresses the stated migration pain. A sprint to implement tooling vs. a multi-quarter high-risk migration.
2. **Unblock the data warehouse migration** — move the risk team's analytical queries off the operational database. This eliminates the JOIN complexity on the operational side and is likely the actual bottleneck.
3. **Keep PostgreSQL** — the existing JSONB usage is appropriate. p95 under 15ms is not a performance problem.
4. **Revisit MongoDB for specific use cases** if they emerge — audit logs, event streams, or metadata stores are candidates. A full migration is not warranted.

---

### A Note on Process

Marcus spoke with the MongoDB sales team before completing his technical analysis. The factual errors in the email (60% vs. 25.5%, the query pattern claim) suggest the framing of the problem may have been influenced by those conversations. This doesn't reflect on Marcus's competence — it's a common dynamic with vendor-driven evaluations. The right response is to present the corrected data clearly and non-confrontationally, and redirect toward tooling investment.

**Bottom line**: The migration would trade a solvable tooling problem for genuine ACID transaction risk in a financial system, while adding MongoDB learning curve across a team of 12 SQL-proficient developers. The cost/benefit doesn't come close to justifying it.

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |

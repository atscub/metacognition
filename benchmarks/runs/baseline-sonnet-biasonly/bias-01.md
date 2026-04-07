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
# Task: arch-06 — Database selection for IoT time-series with ad-hoc joins

## Prompt
You are the data platform architect at SensorGrid, an industrial IoT company. SensorGrid
monitors manufacturing equipment across 120 factories. You need to choose the primary
database for storing and querying sensor telemetry.

Scale:
- 500,000 active sensors (growing ~20% annually)
- 10 million data points ingested per day (~115 writes/second average, ~400/sec peak)
- Data retention: 2 years hot, 5 years cold (archived to S3)
- Current data volume: ~4 TB hot data

Sample sensor data:
```json
{
  "sensor_id": "s-4a2f9c",
  "device_id": "d-7891",
  "timestamp": "2026-04-06T14:23:01.445Z",
  "metric": "vibration_rms",
  "value": 2.34,
  "unit": "mm/s",
  "quality": "good"
}
```

Existing relational tables (in PostgreSQL, managed by the product team):
```sql
-- These tables exist and are actively used by the web app
CREATE TABLE customers (
    id UUID PRIMARY KEY,
    name TEXT, industry TEXT, tier TEXT,
    contract_start DATE, contract_end DATE
);  -- ~800 rows

CREATE TABLE factories (
    id UUID PRIMARY KEY,
    customer_id UUID REFERENCES customers(id),
    name TEXT, location TEXT, timezone TEXT
);  -- ~2,000 rows

CREATE TABLE devices (
    id TEXT PRIMARY KEY,         -- e.g., "d-7891"
    factory_id UUID REFERENCES factories(id),
    model TEXT, firmware_version TEXT,
    installed_at DATE, last_maintenance DATE
);  -- ~50,000 rows

CREATE TABLE sensors (
    id TEXT PRIMARY KEY,         -- e.g., "s-4a2f9c"
    device_id TEXT REFERENCES devices(id),
    metric_type TEXT,            -- "vibration_rms", "temperature", etc.
    calibration_date DATE,
    alert_threshold FLOAT
);  -- ~500,000 rows
```

Query patterns (from the data science team's requirements doc):
1. **Dashboards**: "Show me the last 24 hours of vibration data for device d-7891."
   Frequency: thousands/day. Latency target: < 500ms.
2. **Alerting**: "Find all sensors where the latest reading exceeds the alert_threshold
   defined in the sensors table." Runs every 60 seconds.
3. **Trend analysis**: "Average daily temperature for all sensors in factory F-102 over
   the last 90 days, grouped by device model." Frequency: dozens/day, can tolerate
   10-second latency.
4. **Ad-hoc exploration**: The data science team says: "We need to run arbitrary SQL
   queries that join sensor readings with the customer, factory, and device metadata.
   For example: 'Show me the correlation between firmware version and vibration anomaly
   rates, broken down by customer industry and factory timezone.' We use Jupyter
   notebooks with SQLAlchemy — we cannot switch to a non-SQL query language."
5. **Predictive maintenance**: "Train ML models on historical sensor data joined with
   maintenance records and device metadata. This runs nightly as a batch job."

The team is evaluating three options:

**A. TimescaleDB** (PostgreSQL extension)
- Native PostgreSQL, supports all SQL joins
- Hypertables with automatic time-based partitioning
- Compression: ~10x for time-series data
- Concern: "Can PostgreSQL really handle 10M inserts/day at scale?"

**B. InfluxDB**
- Purpose-built for time-series, excellent write throughput
- InfluxQL/Flux query languages (not standard SQL)
- No native JOIN support — metadata must be denormalized as tags
- Concern: "The data science team will riot if they can't do SQL joins"

**C. Plain PostgreSQL with declarative partitioning**
- Monthly partitions on the readings table
- No additional technology to operate
- Concern: "Isn't this too slow for 10M rows/day?"

Recommend a database architecture. Justify your choice against the specific query
patterns and constraints listed above.


## Response A
## Recommendation: TimescaleDB

**Eliminate InfluxDB immediately.** Query pattern 4 is a hard constraint: "We cannot switch to a non-SQL query language." Alerting (Q2) also requires joining `sensor_readings` against `sensors.alert_threshold` — without native JOINs, you're doing application-level joins in a hot loop every 60 seconds. InfluxDB's write throughput advantage is irrelevant when it structurally fails two of your five query patterns.

The real decision is TimescaleDB vs. plain PostgreSQL.

---

## Why TimescaleDB beats plain PostgreSQL

### The write concern is a red herring

At 115 writes/sec average and 400/sec peak, you are **not** pushing PostgreSQL's limits. Plain PostgreSQL handles thousands of simple inserts per second; with `COPY` or multi-row batching, it scales to hundreds of thousands. TimescaleDB inherits all of this. The "can PostgreSQL handle 10M inserts/day?" concern conflates row count with rate — 10M/day is ~115/sec, which is moderate load for any serious RDBMS.

### Compression is the decisive factor

Your 4 TB hot dataset grows 20% annually, compounded. Over 2 years at current growth:

```
Year 0: 4.0 TB
Year 1: 4.8 TB  
Year 2: 5.8 TB
Total 2-year hot window: ~10+ TB (raw)
```

TimescaleDB's columnar compression achieves ~10x on time-series data. That's **~1 TB compressed** vs. 10+ TB raw. PostgreSQL's row-level TOAST compression doesn't apply to sequential time-series patterns the same way. This difference pays for itself immediately in storage costs and I/O throughput for analytical queries (Q3, Q5).

### Continuous aggregates eliminate your hardest query problems

TimescaleDB continuous aggregates are incrementally maintained materialized views that refresh automatically:

```sql
-- Pre-compute hourly averages at ingest time
CREATE MATERIALIZED VIEW sensor_hourly_avg
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    sensor_id,
    metric,
    AVG(value) AS avg_val,
    MAX(value) AS max_val,
    COUNT(*) AS sample_count
FROM sensor_readings
GROUP BY bucket, sensor_id, metric;

-- Refresh policy: keep this 1 minute behind real time
SELECT add_continuous_aggregate_policy('sensor_hourly_avg',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute');
```

This directly serves:
- **Q1 (dashboards, <500ms)**: Query the hourly aggregate for 24 hours instead of 1.4M raw rows
- **Q3 (trend analysis)**: Pre-aggregated daily rollups make 90-day factory-wide queries trivial

---

## Concrete architecture

### Schema

```sql
-- TimescaleDB in the same PostgreSQL instance as your metadata tables
-- (same engine, same connection string, native JOINs work immediately)

CREATE TABLE sensor_readings (
    timestamp    TIMESTAMPTZ NOT NULL,
    sensor_id    TEXT        NOT NULL,
    device_id    TEXT        NOT NULL,
    metric       TEXT        NOT NULL,
    value        DOUBLE PRECISION,
    quality      TEXT
);

-- Convert to hypertable: 1-week chunks
-- (7-day chunks = ~70M rows/chunk at current rate; easy to drop on retention)
SELECT create_hypertable('sensor_readings', 'timestamp',
    chunk_time_interval => INTERVAL '1 week');

-- Compress chunks older than 2 days (recent data stays row-oriented for fast inserts)
ALTER TABLE sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'timestamp DESC',
    timescaledb.compress_segmentby = 'sensor_id'
);

SELECT add_compression_policy('sensor_readings', INTERVAL '2 days');

-- Retention: drop chunks older than 2 years
SELECT add_retention_policy('sensor_readings', INTERVAL '2 years');

-- Index: sensor_id + timestamp covers Q1 and Q2 hot paths
CREATE INDEX ON sensor_readings (sensor_id, timestamp DESC);
```

### Query pattern solutions

**Q1 — Dashboard (< 500ms SLA):**
```sql
-- Hits the continuous aggregate, not raw data
SELECT bucket, avg_val
FROM sensor_hourly_avg
WHERE sensor_id = 's-4a2f9c'
  AND bucket > NOW() - INTERVAL '24 hours'
ORDER BY bucket;
```
Compressed chunks + index + pre-aggregation → well under 100ms in practice.

**Q2 — Alerting (every 60 seconds):**
```sql
-- Create a "latest value per sensor" continuous aggregate refreshing every 30s
-- Then JOIN to the existing sensors table — same DB, zero data movement
SELECT r.sensor_id, r.latest_value, s.alert_threshold
FROM sensor_latest_values r          -- continuous aggregate
JOIN sensors s ON s.id = r.sensor_id -- your existing PostgreSQL table
WHERE r.latest_value > s.alert_threshold;
```
This runs in the same database. No cross-system joins, no denormalization.

**Q3 — Trend analysis:**
```sql
SELECT 
    d.model,
    time_bucket('1 day', r.bucket) AS day,
    AVG(r.avg_val) AS daily_avg
FROM sensor_hourly_avg r
JOIN sensors s  ON s.id = r.sensor_id
JOIN devices d  ON d.id = s.device_id
JOIN factories f ON f.id = d.factory_id
WHERE f.id = 'F-102'
  AND r.metric = 'temperature'
  AND r.bucket > NOW() - INTERVAL '90 days'
GROUP BY d.model, day
ORDER BY day;
```
Native JOINs to your existing metadata. Aggregate-on-aggregate is fast.

**Q4 — Ad-hoc SQL (Jupyter/SQLAlchemy):**
No changes needed. SQLAlchemy connects to PostgreSQL (TimescaleDB is PostgreSQL). All standard SQL including arbitrary JOINs work unchanged. Your data scientists get full SQL access to both sensor data and all metadata tables.

**Q5 — ML training batch job:**
```sql
-- Direct export to Parquet via COPY or via pandas read_sql
-- Or use TimescaleDB's native S3 tiered storage for the 2-5 year cold tier
SELECT r.timestamp, r.sensor_id, r.value, r.metric,
       d.model, d.firmware_version, d.last_maintenance,
       f.timezone, c.industry
FROM sensor_readings r
JOIN sensors s  ON s.id = r.sensor_id
JOIN devices d  ON d.id = s.device_id
JOIN factories f ON f.id = d.factory_id
JOIN customers c ON c.id = f.customer_id
WHERE r.timestamp BETWEEN '2025-01-01' AND '2026-01-01';
```

---

## Cold storage (2–5 year tier)

Use TimescaleDB's retention policy to drop chunks after 2 years, but export before dropping:

```python
# Nightly job: export yesterday's compressed chunk to S3 as Parquet
# Use pandas + SQLAlchemy (already in their stack) or pg2parquet
```

Alternatively, **Timescale Cloud** offers native tiered storage (hot → S3 transparently). If you're self-hosting, a simple cron job exporting old chunks to S3 Parquet via `COPY TO` is sufficient — the data science team can query cold data via Athena or DuckDB using the same column schema.

---

## What to rule out definitively

| Requirement | TimescaleDB | InfluxDB | Plain PG |
|---|---|---|---|
| SQL JOINs (Q4, hard constraint) | Yes | No | Yes |
| Alerting with metadata joins (Q2) | Native | App-level hack | Native |
| 10x storage compression | Yes | Yes (different) | No |
| Continuous aggregates | Yes | Limited | Manual |
| <500ms dashboard queries | Yes (aggregates) | Yes | Marginal |
| Operational simplicity | High (it's PostgreSQL) | New system | Highest |
| 400 writes/sec peak | Trivial | Trivial | Trivial |

Plain PostgreSQL is operationally simpler but you will reimplement TimescaleDB's compression and continuous aggregate machinery by hand, badly, over the next 18 months as data grows. The extension costs you nothing if you're already running PostgreSQL.

**Go with TimescaleDB on the same PostgreSQL instance as your metadata.** Your data scientists keep their SQL workflows unchanged, your alerting joins are free, and 10x compression keeps your storage bill manageable as you scale toward 1M sensors.

## Response B
## Reframing the Problem

### Step 1: Current Framing

The default framing here is: **"This is a database selection problem — which technology best handles time-series writes at scale?"** That framing implicitly treats write throughput as the binding constraint and pulls us toward specialized tools.

But before committing to that lens, let me stress-test it.

---

### Step 2: Reframing Lenses

**The Simplicity Lens — Is PostgreSQL actually too slow?**

The concern "can PostgreSQL handle 10M inserts/day?" invites scrutiny. Let's do the math:

- 10M rows/day = 115 writes/sec average, 400/sec peak
- A tuned PostgreSQL instance on modest hardware handles 5,000–20,000 writes/sec

115 writes/sec is not a PostgreSQL problem. This concern may be cargo-cult thinking — pattern-matching to "time-series = specialized DB" without checking whether the actual numbers justify it. The concern isn't write throughput; it's *read performance as data accumulates* and *operational overhead of managing a growing table*.

**The Constraint Lens — Which constraints are real vs. assumed?**

Stated constraints:
- SQL joins required (Jupyter + SQLAlchemy) — **hard, real constraint**
- 500ms dashboard latency — **real, but achievable multiple ways**
- 2yr hot / 5yr cold retention — **real, shapes storage strategy**

This single hard constraint — *SQL joins against existing PostgreSQL metadata* — eliminates InfluxDB from serious consideration before any performance analysis begins. InfluxQL/Flux are not SQL. Denormalizing `customer_id`, `industry`, `firmware_version`, `timezone` as tags on every reading is not a join — it's a replication strategy that introduces data consistency risk and balloons storage. The data science team's query pattern #4 (correlation between firmware version and vibration anomaly rates, broken down by customer industry and factory timezone) requires joining across four tables. You cannot fake this with tags.

InfluxDB is eliminated. The real choice is **TimescaleDB vs. plain PostgreSQL with partitioning.**

**The Zoom Out Lens — What is the actual system?**

The problem isn't just "store and query sensor readings." The system includes:
- Existing PostgreSQL with metadata (managed by a separate product team)
- Jupyter notebooks with SQLAlchemy for data science
- An alerting loop running every 60 seconds
- Dashboards querying recent data thousands of times per day
- Nightly ML training jobs joining readings with maintenance records

Adding a second database technology means: ETL pipelines between systems, two connection pools, two operational runbooks, two on-call escalation paths, and data consistency risk at the join boundary. The "hidden cost of InfluxDB" isn't just the query language — it's the operational surface area of a heterogeneous system.

**The Time Lens — What does this look like in 18 months?**

- 20% annual sensor growth → ~600K sensors in 12 months, ~720K in 24 months
- Data volume grows proportionally: 4TB hot today → ~6TB in 18 months
- Plain PostgreSQL with monthly partitions: 24 partitions for hot data is manageable now, but VACUUM pressure on uncompressed large tables grows painful, and manual partition management (creating future partitions, detaching/archiving old ones) becomes an ongoing ops burden with no safety net
- TimescaleDB compression (claimed ~10x): 4TB becomes ~400GB compressed — meaningful for I/O-bound query performance and storage cost

**The Adversarial Lens — How would each option fail?**

*Plain PostgreSQL:*
- VACUUM fails to keep up on a heavily-written large table → table bloat → slow sequential scans
- A data scientist runs an unindexed exploratory query → full table scan locks up the primary → dashboard latency spikes
- Someone forgets to create next month's partition → inserts fail at midnight

*TimescaleDB:*
- Extension version lag behind PostgreSQL → upgrade path complexity
- Compression makes individual row updates expensive (a non-issue here — sensor data is append-only)
- Continuous aggregates can fall behind under heavy ingest — requires tuning `refresh_interval`

*InfluxDB:*
- Already eliminated, but for completeness: every join query requires an application-layer fetch-and-merge, meaning query #4 would require pulling millions of rows into pandas and joining in Python — latency, memory, and complexity cost that compounds with every new ad-hoc query

---

### Step 3: Compare Framings

| Framing | Points toward |
|---|---|
| "Pick the most specialized write-optimized tool" | InfluxDB — but disqualified by SQL constraint |
| "Is plain PostgreSQL actually sufficient?" | Probably yes today; operational risk grows with scale |
| "Minimize system complexity while meeting all constraints" | TimescaleDB — same operational model as PostgreSQL |
| "What survives 18 months of 20% growth?" | TimescaleDB — compression and chunk architecture are the safety net |

Three of four framings converge on **TimescaleDB**. The convergence is strong.

---

## Recommendation: TimescaleDB

### The Core Argument

TimescaleDB is the right choice — not because PostgreSQL "can't handle" the write throughput (it can), but because it extends PostgreSQL with exactly the missing capabilities needed as the dataset grows, while preserving everything the data science team depends on.

You are not choosing between PostgreSQL and TimescaleDB. You are choosing between **unextended PostgreSQL** and **PostgreSQL with time-series superpowers**. The operational model is identical. The query language is identical. The connection string changes by one word.

---

### Query Pattern Analysis

**Pattern 1 — Dashboards (< 500ms, thousands/day)**

```sql
SELECT timestamp, value
FROM sensor_readings
WHERE sensor_id = 's-4a2f9c'
  AND timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp;
```

TimescaleDB's chunk-based partitioning means this query touches at most 1–2 chunks (time-boxed segments), not a full table scan. With a composite index on `(sensor_id, timestamp DESC)`, this is a fast index scan on a small chunk. Plain PostgreSQL with monthly partitions achieves similar pruning but requires more careful index strategy and yields no compression benefit.

**Pattern 2 — Alerting every 60 seconds**

```sql
SELECT r.sensor_id, r.value, s.alert_threshold
FROM sensor_readings r
JOIN sensors s ON r.sensor_id = s.id
WHERE r.timestamp > NOW() - INTERVAL '2 minutes'
  AND r.value > s.alert_threshold;
```

This is a join against the existing `sensors` table in PostgreSQL. TimescaleDB runs natively in the same PostgreSQL instance, so this is a local join — no network hop, no ETL. With InfluxDB, you'd need to: fetch the latest readings via Flux, fetch thresholds from PostgreSQL, join in application code, and run this every 60 seconds. That's fragile.

Use a **continuous aggregate** to maintain a `latest_readings` materialized view — this makes the alerting query a near-instant lookup rather than a scan of the last 2 minutes of raw data.

**Pattern 3 — Trend analysis (90-day aggregates, 10s latency OK)**

```sql
SELECT d.model, DATE_TRUNC('day', r.timestamp) AS day, AVG(r.value)
FROM sensor_readings r
JOIN sensors s ON r.sensor_id = s.id
JOIN devices d ON s.device_id = d.id
WHERE s.metric_type = 'temperature'
  AND d.factory_id = 'F-102'
  AND r.timestamp > NOW() - INTERVAL '90 days'
GROUP BY d.model, day
ORDER BY day;
```

TimescaleDB continuous aggregates pre-compute daily averages per sensor. The 90-day query then scans a tiny materialized table rather than raw readings. Without this, 90 days × 500K sensors × readings is a full analytical scan — 10s latency requires either continuous aggregates or a columnar store.

**Pattern 4 — Ad-hoc data science queries**

The firmware-vs-vibration-anomaly correlation query is exactly what makes InfluxDB unworkable. This query joins `sensor_readings → sensors → devices → factories → customers` — four joins across tables managed by a separate team in a separate PostgreSQL database. TimescaleDB makes this a standard SQL query run over a foreign data wrapper or a shared PostgreSQL connection. InfluxDB makes this a multi-system extract/join operation in Python that falls apart when the data science team asks a novel question at 11pm.

**Pattern 5 — Nightly ML training**

Bulk export for training: a single `COPY` or `SELECT INTO` that joins sensor readings with maintenance records and device metadata. Same PostgreSQL semantics, same tooling, works natively.

---

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  PostgreSQL / TimescaleDB                │
│                                                         │
│  Hypertable: sensor_readings                            │
│  ├── chunk_interval: 1 week (tunable)                   │
│  ├── compression: enabled after 7 days (10x ratio)      │
│  └── retention: 2yr hot, then pg_partman → S3 archive   │
│                                                         │
│  Continuous aggregates:                                  │
│  ├── sensor_hourly_stats (for dashboards)               │
│  └── sensor_daily_stats  (for trend queries)            │
│                                                         │
│  Existing tables (unchanged):                           │
│  ├── customers, factories, devices, sensors             │
│  └── (managed by product team — no migration required)  │
└─────────────────────────────────────────────────────────┘
```

**Hypertable definition:**
```sql
SELECT create_hypertable('sensor_readings', 'timestamp',
  chunk_time_interval => INTERVAL '1 week',
  partitioning_column => 'sensor_id',
  number_partitions => 4  -- space partitioning for parallel writes
);

-- Compression policy: compress chunks older than 7 days
SELECT add_compression_policy('sensor_readings', INTERVAL '7 days');

-- Retention policy: drop chunks older than 2 years (after S3 archive)
SELECT add_retention_policy('sensor_readings', INTERVAL '2 years');
```

**Continuous aggregate for dashboards:**
```sql
CREATE MATERIALIZED VIEW sensor_hourly_stats
WITH (timescaledb.continuous) AS
SELECT sensor_id,
       time_bucket('1 hour', timestamp) AS bucket,
       AVG(value) AS avg_val,
       MAX(value) AS max_val,
       MIN(value) AS min_val
FROM sensor_readings
GROUP BY sensor_id, bucket;

SELECT add_continuous_aggregate_policy('sensor_hourly_stats',
  start_offset => INTERVAL '3 hours',
  end_offset   => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 hour'
);
```

---

### Addressing the Stated Concerns

**"Can PostgreSQL really handle 10M inserts/day at scale?"**

Yes. 115 writes/sec average / 400 writes/sec peak is well within PostgreSQL's range — a single modern instance handles 5,000–20,000 writes/sec. The concern is valid at 100M writes/day; it is not the binding constraint here. TimescaleDB adds write throughput through parallel chunk insertion, not by replacing PostgreSQL's write path.

At 20% annual growth, you reach ~400 writes/sec sustained in about 4–5 years. At that point, TimescaleDB's multi-node option (or read replicas for query offload) provides a clear upgrade path without changing your query language or application code.

**"The data science team will riot if they can't do SQL joins"**

With TimescaleDB, they never have to. Their SQLAlchemy connection string points at the same PostgreSQL endpoint. Every query they write today continues to work. The `sensor_readings` hypertable looks like a regular table to any SQL client.

**"Isn't plain PostgreSQL too slow for 10M rows/day?"**

Not for writes. Potentially yes for reads on raw data without continuous aggregates or compression. The operational risk with plain PostgreSQL is: manual partition management accumulates toil; without compression, 4TB grows to 20TB over 5 years with proportional I/O cost; no built-in continuous aggregates means dashboard queries hit raw data; no built-in retention policy means ad-hoc `DROP TABLE` scripts for old partitions.

TimescaleDB solves all of these. Plain PostgreSQL requires you to build and maintain the same solutions manually.

---

### What to Skip

**Do not build a hybrid architecture** (TimescaleDB for writes + InfluxDB for reads, or Kafka in front of TimescaleDB). The write throughput does not justify it. Hybrid architectures introduce consistency windows, operational complexity, and failure modes that exceed any benefit at this scale.

**Do not pre-optimize for Cassandra, ClickHouse, or columnar stores.** These are real options at 10x–100x the current scale. At 115 writes/sec and 4TB, they add cost and operational overhead for marginal gain. Revisit at 50M+ writes/day.

---

### Summary

| Criterion | TimescaleDB | InfluxDB | Plain PostgreSQL |
|---|---|---|---|
| SQL joins with metadata | Native | Impossible | Native |
| Write throughput (400/sec peak) | Handles comfortably | Exceeds requirement | Handles comfortably |
| Dashboard latency (< 500ms) | Yes, via continuous aggregates | Yes | Marginal without aggregates |
| Alerting every 60s | Yes, with latest-value aggregate | Requires app-layer join | Yes |
| Trend analysis (90 days) | Fast, via daily aggregates | No SQL | Slow without pre-aggregation |
| Data science ad-hoc SQL | Full standard SQL | Blocked | Full standard SQL |
| ML training batch export | Standard COPY/SELECT | ETL required | Standard COPY/SELECT |
| Compression (4TB → ~400GB) | Yes, automatic | Yes | No |
| Operational complexity | Low (it's PostgreSQL) | High (second system) | Low |
| Growth headroom | High | Medium | Medium |

**Choose TimescaleDB.** Deploy it on the same PostgreSQL infrastructure. Enable compression after 7 days, continuous aggregates for hourly and daily rollups, and a retention policy that archives to S3 at 2 years. The data science team gets full SQL. The alerting system gets sub-second joins. The dashboard team gets pre-aggregated fast paths. You operate one system, not two.

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

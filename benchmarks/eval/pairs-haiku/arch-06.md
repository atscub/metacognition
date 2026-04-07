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
## Reframing This Decision

Let me apply the reframing protocol:

**Current Framing**: "Choose the best time-series database technology."
→ This leads to pattern-matching (specialist tool for specialist problem), which pulls toward InfluxDB.

**Reframing Lenses Applied:**

1. **The Constraint Lens** (which constraints are real?):
   - "Data science team cannot do SQL joins" — **Hard constraint, explicit, non-negotiable.**
   - "PostgreSQL can't handle 10M inserts/day" — **Unvalidated.** 115/sec sustained + 400/sec peak is very achievable with bulk inserts and connection pooling. This might be scaling theater.
   - "We must pick one database" — **Unexamined.** But splitting time-series from metadata creates synchronization problems.

2. **The Zoom Out Lens** (system-level view):
   - Metadata (customers, factories, devices, sensors) **already lives in PostgreSQL** and is actively managed by the product team.
   - Fragmenting telemetry to a different system creates a multi-system join problem for downstream consumers.
   - The data science team explicitly cannot rewrite pipelines to bridge databases.
   - **Real problem: keeping time-series and metadata queryable together, in one system.**

3. **The Inversion Lens** (what would guarantee failure?):
   - Choosing InfluxDB when SQL joins are required = Failure. (The team will either denormalize metadata as tags—operational burden—or write fragile ETL bridges.)
   - Choosing a database that can't write 10M/day reliably = Failure.
   - Keeping telemetry and metadata in separate systems = Synchronization debt, complexity.

4. **The Simplicity Lens** (what's the minimal solution?):
   - Minimal: PostgreSQL with proper partitioning. Metadata and telemetry in one place. All queries are native SQL.
   - The question: Is 10M inserts/day actually slow enough to matter, or is this a false constraint?

---

## Recommendation: **TimescaleDB**

### Primary Choice
**TimescaleDB** (PostgreSQL extension with hypertables)

### Why This Wins

| Factor | TimescaleDB | InfluxDB | Plain PG |
|--------|-------------|----------|----------|
| **SQL Joins with Metadata** | ✅ Full SQL support | ❌ No native joins (tags only, no foreign keys) | ✅ Full SQL support |
| **Data Science Requirements** | ✅ Jupyter + SQLAlchemy work unchanged | ❌ Team would riot; requires rewrites | ✅ Jupyter + SQLAlchemy work unchanged |
| **Write Throughput (10M/day)** | ✅ Built for it; hypertables auto-compress | ✅ Designed for this scale | ⚠️ Possible, needs tuning |
| **Operational Complexity** | 🟡 PostgreSQL + extension | 🔴 New system to operate | ✅ Just PostgreSQL |
| **Hot Data Compression** | ✅ ~10x compression (critical for 4TB→400GB) | ⚠️ Better than raw, but less effective | ❌ No compression |
| **Integration with Product Team's PG** | ✅ Same database, no sync needed | ❌ Two systems to sync | ✅ Same database |

### Architecture Sketch

```sql
-- Metadata stays in product PostgreSQL (unchanged)
-- Telemetry in TimescaleDB hypertable (same server, separate schema)

CREATE TABLE sensor_readings (
    time TIMESTAMPTZ NOT NULL,
    sensor_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value FLOAT8 NOT NULL,
    quality TEXT
) PARTITION BY RANGE (time);

-- Convert to hypertable
SELECT create_hypertable('sensor_readings', 'time', 
    if_not_exists => TRUE,
    time_interval => '7 days');

-- Query pattern (data science can still use this):
SELECT 
    d.model,
    DATE_TRUNC('day', sr.time) AS day,
    AVG(sr.value) AS avg_temp
FROM sensor_readings sr
JOIN devices d ON sr.device_id = d.id
WHERE sr.metric = 'temperature'
  AND sr.time > NOW() - INTERVAL '90 days'
GROUP BY d.model, day;

-- Compression (automatic with TimescaleDB):
-- ~10x reduction for 4TB → ~400GB hot data
ALTER TABLE sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'time DESC'
);
```

### Why Not the Alternatives

**InfluxDB**: Breaks the hard constraint.
- InfluxQL and Flux don't support JOINs to external tables.
- The data science team would need to either:
  - Denormalize all metadata (device model, firmware, calibration) as InfluxDB tags (**operational burden**: sync metadata changes, handle late-arriving metadata).
  - Export readings, join in Python, re-import (**latency**, **complexity**).
  - Write custom code to query both systems (**fragile**, **will break**).
- **Decision**: Only choose InfluxDB if you can *guarantee* data science will not need to join with PostgreSQL metadata. You cannot make that guarantee here.

**Plain PostgreSQL with Partitioning**: Simpler, but unproven for your scale.
- 10M inserts/day = 115/sec sustained, 400/sec peak.
- PostgreSQL can handle this *if*:
  - You use bulk inserts (`COPY`, batch inserts, not single-row).
  - You tune `max_wal_size`, `maintenance_work_mem`, `shared_buffers`.
  - You monitor CPU/IO during peak ingestion.
- **Problem**: This requires constant tuning and monitoring. You're operating at the edge of PostgreSQL's sweet spot.
- **Better**: TimescaleDB handles compression and partitioning *automatically*. You're not guessing; you're using a tool built for this pattern.
- **Fallback**: If your team wants to prove plain PG is sufficient first, start there with monthly partitions, add indexes on (device_id, timestamp, metric), and see if it holds up for 60 days. If latency stays under SLO, you can skip TimescaleDB. But I'd recommend TimescaleDB from day one to avoid the tuning debt.

### Implementation Notes

1. **Operational**: TimescaleDB is a PostgreSQL extension; your ops team already knows PostgreSQL. No new infrastructure.
2. **Migration path**: Start with plain PostgreSQL for the first 3 months to validate the scale. If you're at 50%+ CPU during peak writes, migrate to TimescaleDB (schema change, then `SELECT create_hypertable()`—low-friction).
3. **Compression**: Enable compression on older chunks (data > 1 week old) to keep hot data small.
4. **Cold data**: Archive chunks > 2 years to S3 (TimescaleDB supports this with `policy_compression`).
5. **Alerting query**: The "find sensors exceeding threshold" query runs every 60 seconds—this is a full table scan on latest readings. Add an index or use a materialized view of recent readings.

---

**Bottom line**: TimescaleDB because it's PostgreSQL-plus—all your SQL works, it's built for time-series at your scale, and it integrates seamlessly with the metadata that's already in PostgreSQL.

## Response B
I recommend **Option A: TimescaleDB**. Here's the analysis:

## Why TimescaleDB Wins

**1. It's the only option that doesn't break the data science team's workflow**

The ad-hoc exploration requirement is the killer constraint here:
> "Correlation between firmware version and vibration anomaly rates, broken down by customer industry and factory timezone"

This query looks something like:
```sql
SELECT c.industry, f.timezone, d.model,
       COUNT(CASE WHEN r.value > s.alert_threshold THEN 1 END)::float / COUNT(*) AS anomaly_rate
FROM sensor_readings r
JOIN sensors s ON r.sensor_id = s.id
JOIN devices d ON s.device_id = d.id
JOIN factories f ON d.factory_id = f.id
JOIN customers c ON f.customer_id = c.id
WHERE r.timestamp > NOW() - INTERVAL '90 days'
  AND d.firmware_version = '2.1.4'
GROUP BY c.industry, f.timezone, d.model
```

- **InfluxDB (Option B)** cannot express this at all without denormalizing metadata as tags (creating consistency nightmares and data bloat)
- **Plain PostgreSQL (Option C)** can express it, but will choke on full-table scans of multi-billion-row tables
- **TimescaleDB** handles this elegantly with time-series optimizations

**2. Write scale is completely fine**

Your concerns about "can PostgreSQL handle 10M inserts/day?" are legitimate for vanilla PostgreSQL, but not for TimescaleDB:

- 400/sec peak writes → TimescaleDB routinely handles 100k+/sec on standard hardware
- Hypertables use time-based partitioning + optimized write path
- No random I/O thrashing like you'd get with monthly partitions in vanilla PostgreSQL
- WAL pressure is mitigated by intelligent batching

**3. Compression solves your storage problem**

- 4 TB hot data → ~400 GB with 10x compression (typical for time-series)
- Savings compound across 2 years of hot data and 5 years of cold archive
- Cold storage: archive compressed chunks to S3, query decompressed if needed

**4. Solves all query patterns efficiently**

| Pattern | Latency | How |
|---------|---------|-----|
| **Dashboards** (24hr of device d-7891) | <500ms ✓ | Index on (sensor_id, timestamp DESC); time range pruning eliminates most chunks |
| **Alerting** (latest reading by sensor) | <100ms ✓ | Materialized view of latest values per sensor; or indexed subquery with DISTINCT ON |
| **Trend analysis** (90-day daily averages) | <2s ✓ | Continuous aggregates (pre-computed hourly/daily rollups); join with device metadata |
| **Ad-hoc SQL** (firmware + industry correlations) | <10s ✓ | Full SQL with JOINs; planner uses time-range exclusion to prune irrelevant chunks |
| **ML batch jobs** (nightly training) | - ✓ | Direct query export to CSV/Parquet; SQLAlchemy works unchanged |

**5. Operational simplicity**

- It's a PostgreSQL extension. Your team already knows PostgreSQL.
- Same backup/replication story (WAL, streaming replication, etc.)
- Monitoring and alerting fit existing PostgreSQL tooling
- No "two database systems" to manage

## Recommended Architecture

```
┌─────────────────────────────────────┐
│  TimescaleDB (PostgreSQL + extension)│
├─────────────────────────────────────┤
│ HOT LAYER (2 years)                 │
│  • Hypertable: sensor_readings      │
│    - 1-day chunks, compress after   │
│      30 days (reduce I/O)           │
│  • Existing metadata tables:         │
│    - customers, factories, devices, │
│      sensors (denormalized for      │
│      hot access)                    │
│  • Continuous aggregates:           │
│    - hourly_avg_by_sensor           │
│    - daily_avg_by_device            │
│    - Backfill on demand for JOINs   │
├─────────────────────────────────────┤
│ COLD LAYER (2-5 years)              │
│  • Compressed chunks → S3 (Parquet) │
│  • Query via TimescaleDB + S3 or    │
│    Redshift/DuckDB for deep archive │
└─────────────────────────────────────┘
```

### Table Structure
```sql
-- New hypertable for sensor telemetry
CREATE TABLE sensor_readings (
    time TIMESTAMP NOT NULL,
    sensor_id TEXT NOT NULL,
    device_id TEXT NOT NULL,  -- denormalized for JOIN performance
    value FLOAT NOT NULL,
    metric TEXT NOT NULL,
    quality TEXT
) PARTITION BY RANGE (time);

SELECT create_hypertable('sensor_readings', 'time', 
    if_not_exists => TRUE,
    time_partitioning_func => 'create_time_bucket');

-- Compress chunks older than 30 days
ALTER TABLE sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'sensor_id, time DESC'
);

SELECT add_compression_policy('sensor_readings', INTERVAL '30 days');

-- Index for alerting queries (latest reading per sensor)
CREATE INDEX idx_readings_sensor_latest 
    ON sensor_readings (sensor_id, time DESC) 
    WHERE quality = 'good';

-- Continuous aggregate for dashboards (hourly rollup)
CREATE MATERIALIZED VIEW hourly_sensor_stats WITH (
    timescaledb.continuous
) AS
SELECT time_bucket('1 hour', time) AS hour,
       sensor_id, device_id,
       AVG(value) AS avg_value,
       MAX(value) AS max_value,
       MIN(value) AS min_value,
       COUNT(*) AS sample_count
FROM sensor_readings
GROUP BY hour, sensor_id, device_id;

SELECT add_continuous_aggregate_policy('hourly_sensor_stats', 
    start_offset => INTERVAL '3 days',
    schedule_interval => INTERVAL '1 hour');
```

## Addressing Specific Concerns

**"Isn't this another tool to operate?"**
- No. It's a PostgreSQL extension. Same backup, replication, and monitoring as today.
- Maintenance: `ALTER SYSTEM` parameter changes; compression policies run automatically.

**"What about write performance under peak load (400/sec)?"**
- Test: provision a mid-range RDS instance (8-16 vCPU, 64 GB RAM) and load 500K sensors for one hour. You'll see sub-50ms insert latency at 400/sec.
- For 115/sec average, a t3.xlarge covers you with room to spare.

**"What if we need to query 5 years of cold data?"**
- Archive to S3 after 2 years as compressed Parquet. Use TimescaleDB's native S3 support (or Redshift Spectrum) to query cold data without rehydrating.
- Nightly ML batch jobs: query TimescaleDB directly; if cold data is needed, unroll from S3 on demand.

## Recommendation Summary

| Option | SQL Joins | Write Scale | Data Science Friction | Operational Burden |
|--------|-----------|-------------|----------------------|---------------------|
| **TimescaleDB** ✓ | ✓ | ✓ (400/sec) | ✓ (0 friction) | ✓ (low) |
| InfluxDB | ✗ | ✓ | ✗ (complete rework) | ✓ |
| Plain PostgreSQL | ✓ | ? (risky) | ✓ | ✓ |

**Go with TimescaleDB.** It's the only option that doesn't force trade-offs between scale, analytics, and team productivity.

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

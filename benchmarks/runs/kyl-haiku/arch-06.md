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
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
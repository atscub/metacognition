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
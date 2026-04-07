I recommend **TimescaleDB** without hesitation. Here's the analysis:

---

## Decision: TimescaleDB ✓

### Why TimescaleDB Wins

**1. SQL is your non-negotiable constraint.**  
Your data science team explicitly requires SQLAlchemy + SQL joins across customer → factory → device → readings. InfluxDB's lack of native JOINs would force denormalization of metadata (duplicating customer/factory/device info into every sensor tag), creating a maintenance nightmare and violating the implicit requirement that metadata is normalized. This alone disqualifies InfluxDB.

**2. The "concern" about PostgreSQL write throughput is outdated.**  
10M rows/day (115 writes/sec average, 400/sec peak) is *trivial* for modern PostgreSQL. TimescaleDB routinely handles 10x–100x this volume. The concern underestimates both PostgreSQL's and TimescaleDB's capabilities. With proper batching and tuning, you'll see sustained >1000/sec writes.

**3. TimescaleDB gives you compression without pain.**  
- ~10x compression for time-series data (via columnar storage & gorilla compression in later versions)
- Automatic time-based partitioning (hypertables) eliminates manual partition management
- Your 4TB hot data becomes ~400GB—a real win for operational costs and query speed

**4. Your query patterns map cleanly to TimescaleDB strengths:**

| Pattern | TimescaleDB Solution |
|---------|----------------------|
| **Dashboards** (last 24h, <500ms) | Hypertable indexes on `(device_id, timestamp)` + partitioning; queries hit only recent chunks |
| **Alerting** (60-sec, latest threshold) | Materialized view on latest readings per sensor, refreshed continuously; JOIN to `sensors.alert_threshold` |
| **Trend analysis** (90-day rolling, 10-sec latency OK) | Continuous aggregate views (TimescaleDB feature) pre-compute daily rollups; JOIN factories/devices on the fly |
| **Ad-hoc exploration** | Full SQL JOINs across all tables; no denormalization needed |
| **Batch ML** | Standard PostgreSQL dump; SQLAlchemy reads directly |

---

## Architecture (Recommended Implementation)

```sql
-- Keep metadata tables as-is in regular PostgreSQL
-- (customers, factories, devices, sensors unchanged)

-- Create hypertable for time-series readings
CREATE TABLE readings (
    sensor_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    metric TEXT NOT NULL,
    value FLOAT NOT NULL,
    unit TEXT,
    quality TEXT
);

-- Convert to hypertable, partitioned by time (auto-managed)
SELECT create_hypertable('readings', 'timestamp', if_not_exists => TRUE);

-- Composite index for dashboard queries
CREATE INDEX idx_readings_device_timestamp 
ON readings (sensor_id, timestamp DESC);

-- Compression policy: compress after 14 days, save space
ALTER TABLE readings SET (
    timescaledb.compress = true,
    timescaledb.compress_chunk_time_interval = '7 days'
);

SELECT add_compression_policy('readings', INTERVAL '14 days');

-- Continuous aggregate for alerting (materialized view, refreshed often)
CREATE MATERIALIZED VIEW latest_readings_with_thresholds AS
SELECT 
    r.sensor_id,
    r.timestamp,
    r.value,
    s.alert_threshold,
    r.value > s.alert_threshold AS is_alert
FROM (
    SELECT DISTINCT ON (sensor_id) sensor_id, timestamp, value
    FROM readings
    ORDER BY sensor_id, timestamp DESC
) r
JOIN sensors s ON r.sensor_id = s.id;

REFRESH MATERIALIZED VIEW latest_readings_with_thresholds;
-- Automate this refresh every 60 seconds via application or pg_cron

-- Continuous aggregate for trend analysis (daily rollups)
CREATE MATERIALIZED VIEW daily_temperature_rollup AS
SELECT 
    DATE_TRUNC('day', timestamp) AS day,
    sensor_id,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value
FROM readings
WHERE metric = 'temperature'
GROUP BY DATE_TRUNC('day', timestamp), sensor_id;

SELECT add_continuous_aggregate_policy('daily_temperature_rollup',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
```

### Example Queries

**Dashboard (last 24h for device d-7891):**
```sql
SELECT timestamp, value, quality 
FROM readings 
WHERE sensor_id IN (SELECT id FROM sensors WHERE device_id = 'd-7891')
  AND timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;
-- Hypertable + index = sub-100ms
```

**Alerting (with threshold join):**
```sql
SELECT * FROM latest_readings_with_thresholds 
WHERE is_alert = true;
-- Materialized view + continuous refresh = instant
```

**Trend analysis (90-day correlation, data science query):**
```sql
SELECT 
    d.model,
    f.timezone,
    c.industry,
    DATE_TRUNC('day', r.timestamp)::DATE AS day,
    AVG(r.value) AS avg_vibration
FROM readings r
JOIN sensors s ON r.sensor_id = s.id
JOIN devices d ON s.device_id = d.id
JOIN factories f ON d.factory_id = f.id
JOIN customers c ON f.customer_id = c.id
WHERE r.metric = 'vibration_rms'
  AND f.id = 'F-102'
  AND r.timestamp > NOW() - INTERVAL '90 days'
GROUP BY d.model, f.timezone, c.industry, day
ORDER BY day;
-- Full SQL, full flexibility. With aggregates pre-computed, latency ~2–5 sec.
```

---

## Why Not the Others?

**InfluxDB:** Violates the hard constraint (no SQL JOINs). You'd end up:
- Duplicating customer/factory/device metadata into InfluxDB tags (breaks normalization)
- ETL'ing data between systems
- Data science team maintaining separate query layer
- **Not worth the headache.**

**Plain PostgreSQL + declarative partitioning:**
- Monthly partitions are coarse (90 days = 3 partitions); TimescaleDB's auto-chunking (1-day or 1-week) is better for query pruning
- No compression built-in; you'd need external tools or triggers
- No continuous aggregates; you build rollups manually
- Manual partition management is operational toil
- Slower write throughput without time-series optimization
- **Works, but you're paying for complexity without the benefits.**

---

## Operational Considerations

1. **Capacity**: 4TB hot + 10M rows/day = grow ~1–1.5TB/year. TimescaleDB compression keeps this manageable.
2. **Backups**: TimescaleDB works with standard PostgreSQL backup tools (pg_dump, WAL archiving).
3. **Monitoring**: Watch chunk compression jobs and continuous aggregate refresh times.
4. **Cold storage**: After 2 years, export to S3 (standard PostgreSQL dump) and drop from the hypertable.

**Bottom line:** TimescaleDB is the pragmatic choice. It keeps your SQL-heavy workflow intact, handles the write scale effortlessly, and compresses your storage footprint by 10x. You're not over-engineering (InfluxDB is overkill for a SQL-dependent team), and you're not under-engineering (plain PostgreSQL manual partitioning is tedious). It's the Goldilocks choice.
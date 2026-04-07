## Recommendation: TimescaleDB (Option A)

**Eliminate InfluxDB first.** The data science team's requirement is a hard constraint, not a preference: arbitrary SQL joins across sensor readings and the metadata tables (customers, factories, devices, sensors), using SQLAlchemy. InfluxDB's lack of standard SQL and no native JOIN support makes query patterns 2, 3, 4, and 5 either impossible or require a brittle denormalization scheme. Any "join at the application layer" workaround means you've rebuilt a query planner badly. Cross it off.

**Plain PostgreSQL with partitioning is viable but leaves capability on the table.** 115 writes/sec average is within PostgreSQL's comfort zone — the concern is not write throughput, it's storage efficiency and query performance as the dataset grows 20% annually. Without compression, 4 TB stays 4 TB. Without continuous aggregates, trend queries scan raw data. Without purpose-built time-series chunk management, partition pruning has to be hand-maintained. It works today; it becomes a maintenance burden in 18 months.

---

### TimescaleDB Architecture

**Deployment model:** A dedicated TimescaleDB instance, separate from the product team's PostgreSQL. The DS team and alerting systems connect to TimescaleDB. Metadata tables (customers, factories, devices, sensors) remain in the product PostgreSQL and are exposed to TimescaleDB via `postgres_fdw`. This gives the DS team a single SQL endpoint with full join capability while keeping the product database unaffected by analytical load.

```sql
-- Hypertable with weekly chunks; partition key is time, segment by device
CREATE TABLE sensor_readings (
    time        TIMESTAMPTZ     NOT NULL,
    sensor_id   TEXT            NOT NULL,
    device_id   TEXT            NOT NULL,
    metric      TEXT            NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    quality     TEXT
);

SELECT create_hypertable('sensor_readings', 'time',
    chunk_time_interval => INTERVAL '1 week');

CREATE INDEX ON sensor_readings (device_id, time DESC);
CREATE INDEX ON sensor_readings (sensor_id, time DESC);

-- Compress chunks older than 2 weeks (~10x reduction)
ALTER TABLE sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id, sensor_id',
    timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('sensor_readings', INTERVAL '2 weeks');
```

At 10x compression, 4 TB becomes ~400 GB of hot compressed data. At 20% annual sensor growth, you have several years of headroom before storage becomes a crisis.

---

### Query Pattern Coverage

**Pattern 1 — Dashboards (< 500ms, thousands/day)**

A 24-hour window on a specific device touches exactly one or two weekly chunks. With the `(device_id, time DESC)` index, this is a narrow scan into already-segmented compressed data. Sub-100ms is realistic, well inside the 500ms target.

```sql
SELECT time, metric, value
FROM sensor_readings
WHERE device_id = 'd-7891'
  AND time > NOW() - INTERVAL '24 hours'
ORDER BY time DESC;
```

**Pattern 2 — Alerting (every 60 seconds)**

Use a continuous aggregate to maintain a rolling "latest value per sensor," then join against the `sensors` table (via FDW) for `alert_threshold`. This avoids a full table scan every 60 seconds.

```sql
CREATE MATERIALIZED VIEW latest_readings
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', time) AS bucket,
       sensor_id,
       last(value, time)  AS latest_value,
       last(metric, time) AS metric
FROM sensor_readings
GROUP BY 1, 2;

-- Alert query joins across FDW to product PostgreSQL
SELECT lr.sensor_id, lr.latest_value, s.alert_threshold
FROM latest_readings lr
JOIN sensors s ON lr.sensor_id = s.id
WHERE lr.bucket = time_bucket('1 minute', NOW() - INTERVAL '1 minute')
  AND lr.latest_value > s.alert_threshold;
```

**Pattern 3 — Trend analysis (90 days, 10s latency acceptable)**

Build a continuous aggregate at daily granularity. The "group by device model" join hits the `devices` table via FDW — a ~50K-row lookup that PostgreSQL handles trivially.

```sql
CREATE MATERIALIZED VIEW daily_sensor_stats
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', time) AS day,
       sensor_id, device_id, metric,
       avg(value)  AS avg_value,
       max(value)  AS max_value
FROM sensor_readings
GROUP BY 1, 2, 3, 4;

-- Trend query with device model join
SELECT ds.day, d.model, avg(ds.avg_value)
FROM daily_sensor_stats ds
JOIN devices d ON ds.device_id = d.id
JOIN factories f ON d.factory_id = f.id
WHERE f.id = 'F-102'
  AND ds.day >= NOW() - INTERVAL '90 days'
  AND ds.metric = 'temperature'
GROUP BY 1, 2
ORDER BY 1;
```

**Pattern 4 — Ad-hoc exploration (SQLAlchemy, arbitrary joins)**

This is where the architecture pays for itself. The DS team's connection string points to TimescaleDB. FDW tables `customers`, `factories`, `devices`, `sensors` appear as local tables. Their firmware-vs-vibration-anomaly query runs unmodified:

```sql
SELECT c.industry,
       f.timezone,
       d.firmware_version,
       count(*) FILTER (WHERE sr.value > s.alert_threshold) AS anomaly_count,
       count(*) AS total_readings
FROM sensor_readings sr
JOIN sensors s       ON sr.sensor_id = s.id
JOIN devices d       ON sr.device_id = d.id
JOIN factories f     ON d.factory_id = f.id
JOIN customers c     ON f.customer_id = c.id
WHERE sr.time > NOW() - INTERVAL '30 days'
  AND sr.metric = 'vibration_rms'
GROUP BY 1, 2, 3;
```

No query language change. No SQLAlchemy reconfiguration. No DS team revolt.

**Pattern 5 — ML training (nightly batch)**

Direct SQLAlchemy read via the same endpoint. TimescaleDB's `COPY` export is fast, and the data already lives in a form that joins cleanly with maintenance records in the product database. Optionally use `timescaledb-parallel-copy` for the export step if batch window becomes tight.

---

### Retention and Cold Storage

| Tier | Age | Mechanism |
|------|-----|-----------|
| Hot | 0–2 years | TimescaleDB compressed hypertable |
| Cold | 2–5 years | TimescaleDB data tiering to S3 (OSS: tablespace on S3-mounted volume; Cloud: native tiering) |
| Delete | > 5 years | `drop_chunks()` retention policy |

```sql
SELECT add_retention_policy('sensor_readings', INTERVAL '5 years');
```

---

### Addressing the Write Throughput Concern

The "can PostgreSQL handle 10M inserts/day?" concern is misplaced for TimescaleDB. The chunked hypertable architecture means each insert goes into the current open chunk — a small, in-memory table. TimescaleDB benchmarks at 1–5M rows/second on modest hardware. Your 400/sec peak is two orders of magnitude below where you'd start sweating. The growth concern (20%/year sensors, proportional write growth) is similarly comfortable; you'd need ~10x current write rates before TimescaleDB becomes a bottleneck, and by then you'd have budget for horizontal scaling.

---

### What You're Not Doing (and Why)

- **No dual-write to InfluxDB**: Adds operational complexity, a second system to monitor/upgrade/fail, and a second query language to maintain. TimescaleDB already covers InfluxDB's write throughput strengths.
- **No Kafka in front**: At 400 writes/sec peak, you don't need a message queue to absorb bursts. Add it later if sensors hit tens of thousands per second.
- **No denormalization of metadata into sensor_readings**: The FDW approach keeps metadata authoritative in the product PostgreSQL — no sync lag, no stale firmware versions in your readings table.

---

### Decision Summary

| Requirement | TimescaleDB | InfluxDB | Plain PG |
|---|---|---|---|
| 400 writes/sec peak | ✅ comfortable | ✅ excellent | ✅ fine |
| SQL joins (hard constraint) | ✅ native | ❌ impossible | ✅ native |
| SQLAlchemy compatibility | ✅ | ❌ | ✅ |
| 10x compression | ✅ | ✅ | ❌ |
| Continuous aggregates | ✅ | partial | ❌ |
| Cold storage tiering | ✅ | ✅ | manual |
| Operational footprint | medium | high | low |

TimescaleDB is the only option that satisfies all five query patterns without compromise. The operational cost over plain PostgreSQL is modest — one extension, one additional concept (hypertables), and a FDW configuration. The return is compression, continuous aggregates, and chunk-pruned time-range queries that will remain fast as the dataset grows.
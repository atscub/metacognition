## Reframing the Problem

### Step 1: Current Framing (Before Reframe)

The team is framing this as: *"We have high write volume, so we need a specialized time-series database."* That framing leads straight to InfluxDB. Let me stress-test that.

---

### Step 2: Alternative Lenses

**Inversion Lens — What guarantees failure?**

- A query language the data science team can't use → immediate failure. They have SQLAlchemy notebooks, existing joins, arbitrary SQL. InfluxDB's Flux/InfluxQL isn't SQL. Adding a federation layer to bridge them adds a whole system just to work around a tool's limitation.
- Splitting telemetry from metadata without a join path → forces ETL pipelines, stale data in joins, two systems to operate and two places to debug.
- Treating write throughput as the binding constraint when it isn't → over-engineering the ingestion path while leaving the alerting query pattern unexamined.

**Simplicity Lens — Is this simpler than it looks?**

Let's gut-check the "scary" numbers:

- 115 writes/sec average, 400/sec peak. PostgreSQL comfortably handles 5,000–20,000 TPS in production. The concern about 10M inserts/day is a *single-table, no-partitioning fear*, not a fundamental PostgreSQL limit.
- 4TB over 2 years with partitioning = ~24 monthly partitions at ~170GB each. Partition pruning means most queries touch 1–3 partitions.
- The constraint isn't writes — PostgreSQL can absorb them. The constraint is the **alerting query**: "latest reading for each of 500,000 sensors, compared against threshold, every 60 seconds." That's a different problem entirely.

**Zoom Out Lens — Where is the real bottleneck?**

The system has five distinct query patterns. Mapping each to what it actually requires:

| Query | Real bottleneck |
|---|---|
| Dashboard (24h per device) | Index on `(sensor_id, timestamp)` — trivial |
| **Alerting (latest value × 500k sensors, every 60s)** | **Maintaining a "current state" per sensor — not a time-range scan** |
| Trend analysis (90-day aggregates) | Columnar compression + partition pruning |
| Ad-hoc SQL joins | Must stay in SQL ecosystem |
| ML batch training | Bulk scan — storage efficiency matters |

The alerting pattern is the adversarial case. It's not a time-series query — it's a key-value lookup (latest value per sensor ID). Neither TimescaleDB nor plain PostgreSQL solves this natively without a materialized current-state table.

**Constraint Lens — Which constraints are real vs. assumed?**

- "SQL joins are required" → Hard, stated explicitly, non-negotiable.
- "PostgreSQL can't handle this scale" → Assumed, not demonstrated. 400 writes/sec is not high.
- "We need a specialized time-series system" → This is the assumption being questioned. The data is time-series in shape, but the query patterns are relational.
- "Telemetry must live in the same instance as the product tables" → Not stated. Separation with FDW is viable.

**Time Lens — What does this look like in 18 months?**

- 20% annual growth → ~600k sensors, ~500/sec peak writes. Still manageable.
- Plain PostgreSQL: 4TB grows to ~7TB hot data with no compression. Table bloat becomes real.
- TimescaleDB with 10x compression: same data fits in ~700GB. The storage trajectory matters.
- Cold archival to S3: TimescaleDB has native tiering; plain PostgreSQL requires custom scripts.

---

### Step 3: Framings Compared

| Framing | Implied solution | Problem |
|---|---|---|
| Write performance problem | InfluxDB | Eliminates SQL joins |
| Query pattern problem | TimescaleDB or plain PG | Both viable |
| Operational complexity problem | Plain PG (zero new infra) | Storage growth is real |
| Data growth + tiering problem | TimescaleDB | Right answer for 5-year lifecycle |

Three of four framings converge on **TimescaleDB**. InfluxDB fails the SQL constraint. Plain PostgreSQL fails the storage efficiency and tiering story as you approach year 3–5.

---

## Recommendation: TimescaleDB on a Dedicated Instance + Materialized Current-State Table

### Architecture

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│   Product PostgreSQL (existing)     │     │   Telemetry PostgreSQL + TimescaleDB │
│                                     │     │                                     │
│  customers, factories,              │◄────│  sensor_readings (hypertable)       │
│  devices, sensors                   │ FDW │  sensor_current_state (plain table) │
│                                     │     │                                     │
└─────────────────────────────────────┘     └─────────────────────────────────────┘
                                                         ▲
                                                   ingestion service
                                                   (115–400 writes/sec)
```

**Why a dedicated instance, not co-located?** The write workload (400/sec peak, continuous) and the OLTP web app workload have different resource profiles. Isolating them prevents vacuum, autovacuum, and WAL pressure from the telemetry side from impacting web app latency. PostgreSQL Foreign Data Wrappers (FDW) give the data science team transparent cross-system SQL joins from their Jupyter notebooks — they write one query, the planner handles it.

---

### Addressing Each Query Pattern

**1. Dashboards — "Last 24h for device d-7891"** `< 500ms` ✓

```sql
SELECT timestamp, value
FROM sensor_readings
WHERE sensor_id IN (SELECT id FROM sensors WHERE device_id = 'd-7891')
  AND timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp;
```

TimescaleDB chunk exclusion prunes this to a single recent chunk. Index on `(sensor_id, timestamp DESC)`. Easily sub-100ms.

**2. Alerting — "Latest reading vs. threshold, 500k sensors, every 60s"** — this is the hard one

Do **not** scan `sensor_readings` for this. Maintain a dedicated current-state table, updated on every insert via a trigger or the ingestion service:

```sql
CREATE TABLE sensor_current_state (
    sensor_id   TEXT PRIMARY KEY,
    value       FLOAT,
    quality     TEXT,
    recorded_at TIMESTAMPTZ
);
```

The alert query becomes a 500k-row key-value scan with a join on `sensors.alert_threshold`:

```sql
SELECT cs.sensor_id, cs.value, s.alert_threshold
FROM sensor_current_state cs
JOIN sensors s ON s.id = cs.sensor_id
WHERE cs.value > s.alert_threshold
  AND cs.quality = 'good'
  AND cs.recorded_at > NOW() - INTERVAL '5 minutes';  -- ignore stale sensors
```

This runs in well under a second regardless of historical data size. Without this table, neither TimescaleDB nor plain PostgreSQL can meet the 60-second alert cycle reliably at 500k sensors.

**3. Trend Analysis — "90-day daily averages by factory + device model"**

```sql
SELECT
    time_bucket('1 day', timestamp) AS day,
    d.model,
    AVG(value) AS avg_temp
FROM sensor_readings sr
JOIN sensors s ON s.id = sr.sensor_id          -- FDW join
JOIN devices d ON d.id = s.device_id            -- FDW join
JOIN factories f ON f.id = d.factory_id         -- FDW join
WHERE f.id = 'F-102'
  AND sr.metric = 'temperature'
  AND sr.timestamp > NOW() - INTERVAL '90 days'
GROUP BY 1, 2;
```

TimescaleDB's `time_bucket` is optimized for this. Chunk exclusion limits the scan to the relevant 90-day window. With compression enabled, those chunks are columnar-compressed — aggregations are fast. 10-second latency target is easily met.

**4. Ad-hoc SQL Joins — Data science notebooks**

This is non-negotiable and is why InfluxDB is off the table. With FDW configured, the data science team's SQLAlchemy sessions connect to the telemetry PostgreSQL instance and can join freely:

```sql
-- "Correlation between firmware version and vibration anomaly rates
--  broken down by customer industry and factory timezone"
SELECT
    d.firmware_version,
    c.industry,
    f.timezone,
    COUNT(*) FILTER (WHERE sr.value > s.alert_threshold) AS anomaly_count,
    COUNT(*) AS total_readings,
    ROUND(
        COUNT(*) FILTER (WHERE sr.value > s.alert_threshold)::numeric
        / NULLIF(COUNT(*), 0) * 100, 2
    ) AS anomaly_rate_pct
FROM sensor_readings sr
JOIN sensors s    ON s.id = sr.sensor_id
JOIN devices d    ON d.id = s.device_id
JOIN factories f  ON f.id = d.factory_id
JOIN customers c  ON c.id = f.customer_id
WHERE sr.metric = 'vibration_rms'
  AND sr.timestamp > NOW() - INTERVAL '90 days'
GROUP BY 1, 2, 3
ORDER BY anomaly_rate_pct DESC;
```

Standard SQL, SQLAlchemy-compatible, no query language switch required.

**5. ML Batch Training — Nightly bulk export**

```sql
COPY (
    SELECT sr.*, d.model, d.firmware_version, d.last_maintenance,
           s.calibration_date, s.alert_threshold,
           f.timezone, c.industry
    FROM sensor_readings sr
    JOIN sensors s ON s.id = sr.sensor_id
    JOIN devices d ON d.id = s.device_id
    JOIN factories f ON f.id = d.factory_id
    JOIN customers c ON c.id = f.customer_id
    WHERE sr.timestamp > NOW() - INTERVAL '365 days'
) TO '/tmp/training_data.parquet' WITH (FORMAT parquet);
```

Or via `pg_dump` to S3 via a pipeline. TimescaleDB's continuous aggregates can pre-compute feature windows nightly to reduce the join cost.

---

### Why Not Plain PostgreSQL with Partitioning?

It works today. At 4TB with monthly partitions it's fine. But:

1. **No compression.** PostgreSQL declarative partitioning gives you partition pruning, not compression. In 3 years at 20% annual growth, you're at ~9TB hot data. TimescaleDB compresses to ~900GB. The storage cost delta is significant, and more importantly, compressed columnar chunks make trend analysis dramatically faster.

2. **No native tiering.** Moving cold data to S3 after 2 years requires you to build and maintain the archival pipeline yourself. TimescaleDB's tiered storage policy is a config line.

3. **The gap narrows as you grow.** Plain PostgreSQL is fine at current scale; it becomes a liability at 3-4× scale. TimescaleDB is a PostgreSQL extension — you're not adopting a new system, you're extending the one you already know.

### Why Not InfluxDB?

One sentence: the data science team's SQL join requirement is stated as a hard constraint, and InfluxDB has no native JOIN support. You would need to build and maintain an ETL pipeline to materialize metadata into InfluxDB tags, keep it synchronized with the product PostgreSQL, and it still wouldn't support arbitrary SQL. The operational and query complexity overhead exceeds any write-throughput benefit — especially since 400 writes/sec is well within PostgreSQL's capability.

---

### Decision Matrix

| Requirement | Plain PG | TimescaleDB | InfluxDB |
|---|---|---|---|
| 400/sec write throughput | ✓ | ✓ | ✓ |
| SQL join support | ✓ | ✓ | ✗ |
| Dashboard latency < 500ms | ✓ | ✓ | ✓ |
| Alerting at 500k sensors/60s | ⚠ needs work | ⚠ needs work | ✗ |
| 90-day trend aggregation | ✓ | ✓✓ (compressed) | ✗ |
| Ad-hoc SQL joins from Jupyter | ✓ | ✓ | ✗ |
| Storage efficiency at 5yr scale | ✗ | ✓ (10x compression) | ✓ |
| Native cold tiering to S3 | ✗ | ✓ | ✓ |
| Operational complexity | minimal | low (PG extension) | high (new system) |

**TimescaleDB wins on 6 of 9 criteria.** The alerting pattern requires the same `sensor_current_state` solution regardless of which PostgreSQL-family option you choose — it's a query pattern architectural problem, not a database engine problem.

---

### Immediate Implementation Steps

1. **Deploy TimescaleDB** as a PostgreSQL extension on a dedicated instance (same PG version as product instance for FDW compatibility).
2. **Create the hypertable** with 1-week chunks (balances chunk count vs. size at this scale) and enable compression after 7 days.
3. **Create `sensor_current_state`** and wire the ingestion service to upsert it on every write.
4. **Configure FDW** from the telemetry instance to the product instance so data science joins work transparently.
5. **Enable TimescaleDB tiered storage** or write an S3 archival job for data > 2 years.
6. **Revisit at 1M sensors** — if write throughput genuinely becomes a bottleneck (it won't at 20% annual growth for several years), TimescaleDB supports multi-node at that point.
## Coherence Audit: Three Database Schema Artifacts

Running through the 10 categories, focusing on **factual accuracy** and **naming coherence** since these are technical schemas.

---

### Step 1: Parts Inventory

- Artifact 1 (SQL): ground-truth DDL — `categories` + `products` tables
- Artifact 2 (Knex): programmatic migration — should replicate A1
- Artifact 3 (Prisma): ORM schema — should map to the same database as A1 + A2

---

### Step 2: Cross-Artifact Comparison

#### Category 1: Factual Accuracy — Column-by-column diff

**`products.description`**

| Artifact | Nullability |
|---|---|
| SQL | `TEXT NOT NULL` — required |
| Knex | `.text('description')` — no `.notNullable()`, so **nullable** |
| Prisma | `String?` — **nullable** |

**Discrepancy (High):** SQL enforces NOT NULL; Knex and Prisma allow null. All three will produce different schemas.

---

**`products.sku`**

| Artifact | Present? |
|---|---|
| SQL | `VARCHAR(50) NOT NULL UNIQUE` ✓ |
| Knex | `string('sku', 50).notNullable().unique()` ✓ |
| Prisma | **Missing entirely** |

**Discrepancy (High):** Prisma drops `sku` completely. Any code using Prisma client can't query or set SKU. If Prisma runs `prisma db push`, it will attempt to delete the column.

---

**`products.image_url`**

| Artifact | Present? |
|---|---|
| SQL | **Missing** |
| Knex | `string('image_url', 500)` ✓ |
| Prisma | `String? @db.VarChar(500)` ✓ |

**Discrepancy (High):** SQL is the authoritative DDL but omits `image_url`. Running `001_create_tables.sql` produces a different schema than the Knex migration or what Prisma introspects. This column exists in exactly two of three artifacts.

---

**`products.category_id` (FK to categories)**

| Artifact | Present? |
|---|---|
| SQL | **No FK column, no relation** |
| Knex | **No FK column, no relation** |
| Prisma | `categoryId Int @map("category_id")` — **required, non-null FK** |

**Discrepancy (High):** Prisma asserts a mandatory relationship between `Product` and `Category`. Neither SQL nor Knex creates this column. The `Category.products` relation on the Prisma side is also an orphan. If Prisma manages the schema, it would try to add a NOT NULL column with no default to an existing table — a breaking migration.

---

**`products.unit_price` — type precision**

| Artifact | Type |
|---|---|
| SQL | `DECIMAL(10, 2)` |
| Knex | `decimal('unit_price', 10, 2)` |
| Prisma | `Float` |

**Discrepancy (Medium-High):** `DECIMAL(10,2)` is exact-precision and the standard for monetary values. `Float` is IEEE 754 double-precision floating point — it introduces rounding errors. A price of `$9.99` may be stored as `9.989999999...`. This is a correctness issue, not just a cosmetic mismatch.

---

**`products.weight_kg` — type precision**

| Artifact | Type |
|---|---|
| SQL | `NUMERIC(8, 3)` |
| Knex | `decimal('weight_kg', 8, 3)` |
| Prisma | `Float?` |

**Discrepancy (Medium):** Same pattern as `unit_price`. Prisma uses `Float` where the other two specify an exact-precision numeric type.

---

**`products.updated_at` — update behavior**

| Artifact | Behavior |
|---|---|
| SQL | `DEFAULT NOW()` — set once at insert, never auto-updated |
| Knex | `.defaultTo(knex.fn.now())` — same: set at insert only |
| Prisma | `@updatedAt` — **automatically updated on every write** |

**Discrepancy (Medium):** Prisma's `@updatedAt` is an ORM-managed behavior that updates the field on every `update()` call. The SQL and Knex schemas have no trigger equivalent. If both paths write to the database (raw SQL + Prisma client), `updated_at` will behave differently depending on which path is used.

---

#### Category 4: Naming Coherence

Prisma's field-to-column mapping (`@map`) is consistent throughout — `unitPrice`/`unit_price`, `isActive`/`is_active`, etc. No issues here.

#### Categories 2, 3, 5–10

Not applicable to technical schemas — these categories address documentation voice, framing, scope, and narrative consistency.

---

### Step 3: Findings Summary

| Discrepancy | Between | Severity |
|---|---|---|
| `description` is NOT NULL in SQL, nullable in Knex + Prisma | A1 vs A2 + A3 | High |
| `sku` is absent from Prisma | A1 + A2 vs A3 | High |
| `image_url` is absent from SQL | A1 vs A2 + A3 | High |
| `category_id` FK exists only in Prisma | A3 vs A1 + A2 | High |
| `unit_price` uses `Float` in Prisma instead of `DECIMAL(10,2)` | A3 vs A1 + A2 | Medium-High |
| `weight_kg` uses `Float` in Prisma instead of `NUMERIC(8,3)` | A3 vs A1 + A2 | Medium |
| `updated_at` auto-updates in Prisma but not in SQL/Knex | A3 vs A1 + A2 | Medium |

---

### Recommended Fixes

1. **Pick a single source of truth.** Right now no two artifacts agree fully. If SQL is canonical, generate Prisma schema from introspection (`prisma db pull`) rather than hand-authoring it.

2. **`description`**: Add `.notNullable()` in Knex and remove `?` in Prisma, or change SQL to allow NULL — then make all three consistent.

3. **`sku`**: Add `sku String @unique @db.VarChar(50)` to the Prisma `Product` model.

4. **`image_url`**: Add the column to SQL (`image_url VARCHAR(500)`) to match Knex and Prisma.

5. **`category_id`**: Either add the FK column to SQL and Knex migrations, or remove the relation from Prisma. If keeping it, the Knex migration must create the column and a foreign key constraint.

6. **Numeric precision**: Change Prisma `unit_price` and `weight_kg` from `Float` to `Decimal` with `@db.Decimal(10, 2)` and `@db.Decimal(8, 3)` respectively.

7. **`updated_at`**: If you want auto-update behavior, add a trigger in SQL and a Knex hook. If you don't, change Prisma to `DateTime @default(now()) @map("updated_at")` instead of `@updatedAt`.
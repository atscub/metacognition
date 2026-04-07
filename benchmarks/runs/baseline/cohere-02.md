Here are the discrepancies across the three artifacts:

---

## 1. `description` — nullability mismatch

| Artifact | Nullability |
|---|---|
| SQL | `NOT NULL` |
| Knex | nullable (no `.notNullable()`) |
| Prisma | `String?` (nullable) |

SQL disagrees with the other two.

---

## 2. `image_url` — missing from SQL

| Artifact | Present |
|---|---|
| SQL | No |
| Knex | Yes (`VARCHAR(500)`) |
| Prisma | Yes (`VarChar(500)`) |

SQL is missing this column entirely.

---

## 3. `sku` — missing from Prisma

| Artifact | Present |
|---|---|
| SQL | Yes (`VARCHAR(50) NOT NULL UNIQUE`) |
| Knex | Yes |
| Prisma | **No** |

Prisma drops `sku` entirely — a critical field given it's a unique business identifier.

---

## 4. `category_id` — spurious in Prisma only

| Artifact | Present |
|---|---|
| SQL | No |
| Knex | No |
| Prisma | Yes (`categoryId Int`, required, with `Category` relation) |

Prisma adds a required `category_id` FK on products that doesn't exist in the other two. This would also make `categoryId` non-nullable, meaning you can't insert a product without a category — a constraint that SQL and Knex don't enforce.

---

## 5. `unit_price` and `weight_kg` — type mismatch in Prisma

| Artifact | `unit_price` | `weight_kg` |
|---|---|---|
| SQL | `DECIMAL(10, 2)` | `NUMERIC(8, 3)` |
| Knex | `decimal(10, 2)` | `decimal(8, 3)` |
| Prisma | `Float` | `Float?` |

Prisma's `Float` maps to PostgreSQL `double precision` (floating-point), not fixed-precision `DECIMAL`. For monetary values (`unit_price`) this is a significant semantic error — floating-point arithmetic will introduce rounding errors.

---

## 6. `onDelete` for `parent_id` self-relation — missing in Prisma

| Artifact | Behavior |
|---|---|
| SQL | `ON DELETE SET NULL` |
| Knex | `.onDelete('SET NULL')` |
| Prisma | Not specified (defaults to `Restrict`) |

Prisma will default to `Restrict`, blocking deletion of parent categories. SQL and Knex would set `parent_id` to null instead.

---

## 7. `created_at` — timezone handling

| Artifact | Type |
|---|---|
| SQL | `TIMESTAMP WITH TIME ZONE` |
| Knex | `timestamp` (without time zone — Knex default) |
| Prisma | `DateTime` → `timestamp(3)` (without time zone) |

Only SQL uses timezone-aware timestamps. Knex and Prisma use `timestamp without time zone`.

---

## 8. `updated_at` — update behavior

| Artifact | Behavior |
|---|---|
| SQL | `DEFAULT NOW()` — set on insert only |
| Knex | `.defaultTo(knex.fn.now())` — set on insert only |
| Prisma | `@updatedAt` — auto-updated by Prisma ORM on every write |

This is a behavioral difference: the Prisma model will auto-update `updated_at` transparently, while the SQL/Knex definitions rely on application code or triggers to do so.

---

## Summary table

| Issue | SQL | Knex | Prisma |
|---|---|---|---|
| `description` nullable | NOT NULL | nullable | nullable |
| `image_url` exists | No | Yes | Yes |
| `sku` exists | Yes | Yes | **No** |
| `category_id` exists | No | No | **Yes** |
| Price/weight types | DECIMAL | decimal | **Float** |
| `parent_id` onDelete | SET NULL | SET NULL | **Restrict** |
| Timestamps timezone | WITH TZ | without TZ | without TZ |
| `updated_at` auto-update | No | No | **Yes** |
## Coherence Audit: Three Schema Artifacts

Working through the relevant categories of the 10-category checklist. For schema artifacts, categories 1, 2, 4, and 8 carry the most weight.

---

### Category 1: Factual Accuracy — Do the parts describe the same reality?

Six discrepancies found:

---

**[HIGH] `category_id` — present in Prisma only**

| Artifact | `category_id` on `products` |
|---|---|
| SQL | absent |
| Knex | absent |
| Prisma | `categoryId Int @map("category_id")` — required (non-nullable) |

Prisma declares a required FK from `Product` to `Category`. Neither the SQL schema nor the Knex migration creates this column. If Prisma were pointed at a database built from either of the other two artifacts, every product insert would fail with a NOT NULL violation. The `Category.products Product[]` relation in Prisma is a symptom of the same gap.

---

**[HIGH] `sku` — present in SQL and Knex, absent in Prisma**

| Artifact | `sku` field |
|---|---|
| SQL | `VARCHAR(50) NOT NULL UNIQUE` + explicit index |
| Knex | `string('sku', 50).notNullable().unique()` + raw index |
| Prisma | completely absent |

The Prisma model cannot read, write, filter, or enforce uniqueness on `sku`. Any application code going through Prisma loses access to this field entirely.

---

**[HIGH] `description` nullability mismatch**

| Artifact | `description` |
|---|---|
| SQL | `TEXT NOT NULL` |
| Knex | `.text()` — no `.notNullable()`, so nullable |
| Prisma | `String?` — optional |

SQL enforces a NOT NULL constraint. The migration that creates the table does not, so the actual database created by Knex will accept NULL descriptions. Prisma correctly reflects what Knex creates, but neither matches the stated SQL intent.

---

**[MEDIUM] `image_url` — absent in SQL**

| Artifact | `image_url` |
|---|---|
| SQL | absent |
| Knex | `string('image_url', 500)` |
| Prisma | `String? @db.VarChar(500)` |

Knex and Prisma agree with each other, but the SQL schema is incomplete — it does not include this column. The SQL file is not the authoritative source it claims to be.

---

**[MEDIUM] `unit_price` type — DECIMAL vs Float**

| Artifact | type |
|---|---|
| SQL | `DECIMAL(10, 2)` |
| Knex | `decimal(10, 2)` |
| Prisma | `Float` |

`DECIMAL(10,2)` is exact fixed-point arithmetic. `Float` is IEEE 754 binary floating-point, which cannot represent many decimal fractions exactly. For a price field this is a real semantic mismatch — Prisma will round-trip values that SQL would store exactly.

---

**[MEDIUM] `updated_at` behavior mismatch**

| Artifact | behavior |
|---|---|
| SQL | `DEFAULT NOW()` — set on insert only |
| Knex | `.defaultTo(knex.fn.now())` — set on insert only |
| Prisma | `@updatedAt` — Prisma auto-updates on every write |

The SQL and Knex versions only populate `updated_at` at row creation. Prisma's `@updatedAt` directive causes it to automatically update the field on every `update` operation. The runtime behavior diverges depending on which layer touches the database.

---

### Category 2: Representational Completeness

- Prisma's `Product` is missing `sku` — a column that exists in the other two artifacts and has a unique constraint and index.
- SQL's `products` table is missing `image_url` and `category_id` — columns that exist in Knex and/or Prisma.
- No artifact has a complete, self-consistent picture of the intended schema.

---

### Category 4: Naming Coherence

No naming issues. All three use consistent mappings: `snake_case` column names in SQL/Knex, `camelCase` field names in Prisma with correct `@map()` directives throughout. `weight_kg` → `weightKg`, `unit_price` → `unitPrice`, etc. are all aligned.

---

### Category 8: Category Accuracy

The type classification for `unit_price` is incorrect in Prisma. `Float` and `DECIMAL` are not interchangeable — they belong to different numeric categories (approximate vs. exact). This is a semantic misclassification, not just a precision difference.

---

## Summary Table

| # | Field | SQL | Knex | Prisma | Severity |
|---|---|---|---|---|---|
| 1 | `category_id` on products | absent | absent | required FK | **High** |
| 2 | `sku` on products | NOT NULL UNIQUE | NOT NULL UNIQUE | absent | **High** |
| 3 | `description` nullability | NOT NULL | nullable | nullable | **High** |
| 4 | `image_url` on products | absent | present | present | Medium |
| 5 | `unit_price` type | DECIMAL(10,2) | DECIMAL(10,2) | Float | Medium |
| 6 | `updated_at` behavior | default only | default only | auto-updates | Medium |

---

## Recommended Fix Order

1. **Decide on `category_id`**: either add it to SQL and Knex, or remove it from Prisma and make the relation optional.
2. **Add `sku` to Prisma** with `@unique` and the correct `@map("sku")`.
3. **Align `description`**: make it `NOT NULL` in Knex (`.notNullable()`) and remove the `?` in Prisma, or drop the constraint in SQL.
4. **Add `image_url` to SQL**.
5. **Change Prisma `unitPrice` to `Decimal`** (requires `@db.Decimal(10, 2)`).
6. **Resolve `updated_at`**: either add a trigger to SQL to auto-update, or remove `@updatedAt` from Prisma and let application code manage it.
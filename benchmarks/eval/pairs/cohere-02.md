# Task: cohere-02 — Database schema vs migration vs ORM model

## Prompt
Review the following three artifacts for consistency. Identify any discrepancies between them.

## Artifact 1: PostgreSQL Schema (sql/001_create_tables.sql)

```sql
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    sku VARCHAR(50) NOT NULL UNIQUE,
    unit_price DECIMAL(10, 2) NOT NULL,
    quantity_in_stock INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    weight_kg NUMERIC(8, 3),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_products_active ON products(is_active);
CREATE INDEX idx_categories_slug ON categories(slug);
```

## Artifact 2: Knex.js Migration (migrations/20240115_create_products_categories.js)

```javascript
exports.up = function (knex) {
  return knex.schema
    .createTable('categories', (table) => {
      table.increments('id').primary();
      table.string('name', 100).notNullable();
      table.string('slug', 100).notNullable().unique();
      table.integer('parent_id').unsigned().references('id').inTable('categories').onDelete('SET NULL');
      table.timestamp('created_at').defaultTo(knex.fn.now());
    })
    .createTable('products', (table) => {
      table.increments('id').primary();
      table.string('name', 255).notNullable();
      table.text('description');
      table.string('sku', 50).notNullable().unique();
      table.decimal('unit_price', 10, 2).notNullable();
      table.integer('quantity_in_stock').notNullable().defaultTo(0);
      table.boolean('is_active').notNullable().defaultTo(true);
      table.decimal('weight_kg', 8, 3);
      table.string('image_url', 500);
      table.timestamp('created_at').defaultTo(knex.fn.now());
      table.timestamp('updated_at').defaultTo(knex.fn.now());
    })
    .then(() => {
      return knex.schema.raw('CREATE INDEX idx_products_sku ON products(sku)');
    })
    .then(() => {
      return knex.schema.raw('CREATE INDEX idx_products_active ON products(is_active)');
    })
    .then(() => {
      return knex.schema.raw('CREATE INDEX idx_categories_slug ON categories(slug)');
    });
};

exports.down = function (knex) {
  return knex.schema.dropTableIfExists('products').dropTableIfExists('categories');
};
```

## Artifact 3: Prisma Schema (prisma/schema.prisma)

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model Category {
  id        Int        @id @default(autoincrement())
  name      String     @db.VarChar(100)
  slug      String     @unique @db.VarChar(100)
  parentId  Int?       @map("parent_id")
  parent    Category?  @relation("CategoryTree", fields: [parentId], references: [id])
  children  Category[] @relation("CategoryTree")
  products  Product[]
  createdAt DateTime   @default(now()) @map("created_at")

  @@map("categories")
}

model Product {
  id             Int       @id @default(autoincrement())
  name           String    @db.VarChar(255)
  description    String?
  unitPrice      Float     @map("unit_price")
  quantityInStock Int      @default(0) @map("quantity_in_stock")
  isActive       Boolean   @default(true) @map("is_active")
  weightKg       Float?    @map("weight_kg")
  imageUrl       String?   @db.VarChar(500) @map("image_url")
  categoryId     Int       @map("category_id")
  category       Category  @relation(fields: [categoryId], references: [id])
  createdAt      DateTime  @default(now()) @map("created_at")
  updatedAt      DateTime  @updatedAt @map("updated_at")

  @@map("products")
}
```


## Response A
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

## Response B
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

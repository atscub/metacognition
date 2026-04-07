# Schema Consistency Review

I found **6 major discrepancies** across these artifacts:

## 🔴 Critical Issues

### 1. **Missing Product-Category Relationship**
- **SQL & Knex**: No `category_id` foreign key in products table
- **Prisma**: Products has `categoryId` (required) + `category` relation to Category

This is a **structural mismatch**. Prisma enforces a relationship that doesn't exist in the actual schema.

### 2. **Missing SKU Field in Prisma**
- **SQL & Knex**: `sku VARCHAR(50) NOT NULL UNIQUE`
- **Prisma**: No SKU field defined

Products without SKU identifiers in Prisma will break any code expecting to use it.

### 3. **Extra image_url Field in Knex & Prisma**
- **SQL**: No `image_url` column
- **Knex**: `image_url VARCHAR(500)` (extra)
- **Prisma**: `imageUrl` (extra)

The actual database schema doesn't have this column, but two definitions expect it.

## ⚠️ Type & Constraint Mismatches

### 4. **description Nullability**
- **SQL**: `TEXT NOT NULL` (required)
- **Knex**: Implicitly nullable (no `.notNullable()`)
- **Prisma**: `String?` (nullable)

### 5. **Price/Weight Type Precision**
- **SQL**: `DECIMAL(10, 2)` and `NUMERIC(8, 3)` (exact)
- **Knex**: `decimal()` (exact)
- **Prisma**: `Float` (imprecise for currency/measurements)

### 6. **unsigned vs. signed integers**
- **Knex**: `parent_id` is `.unsigned()` 
- **SQL/Prisma**: No unsigned constraint specified (though INT is fine)

## Recommendations

**Priority 1**: Add `category_id` and foreign key to the SQL schema, or remove it from Prisma
**Priority 2**: Add `sku` to Prisma, or remove it from SQL/Knex
**Priority 3**: Decide on `image_url` — add to SQL or remove from Knex/Prisma
**Priority 4**: Change `description` to nullable in SQL, or non-nullable in Knex/Prisma (be consistent)
**Priority 5**: Use `Decimal` in Prisma instead of `Float` for financial data

Which of these should I fix first?
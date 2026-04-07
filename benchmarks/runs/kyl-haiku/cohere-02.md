# Coherence Audit: Three Schema Definitions

Working through the 10-category checklist systematically:

---

## **1. Factual Accuracy** — Do the parts describe the same reality?

### ❌ CRITICAL DISCREPANCIES

| Field | SQL | Knex | Prisma | Status |
|-------|-----|------|--------|--------|
| **image_url** | ❌ Missing | ✅ `string(500)` | ✅ `String?` | Knex/Prisma add a field SQL doesn't define |
| **category_id** (FK to categories) | ❌ Missing | ❌ Missing | ✅ Present + required | Prisma adds a relationship SQL/Knex lack entirely |
| **description** | `TEXT NOT NULL` | `text()` (nullable by default) | `String?` (optional) | Type & nullability mismatch across all three |
| **unit_price** | `DECIMAL(10,2)` | `decimal(10, 2)` | `Float` | Prisma loses fixed-decimal precision |
| **weight_kg** | `NUMERIC(8,3)` | `decimal(8, 3)` | `Float` | Prisma loses fixed-decimal precision |
| **Indexes** | 3 indexes defined | 3 indexes defined | ❌ Zero indexes | Prisma omits all performance indexes |

---

## **2. Representational Completeness** — Do all components get fair coverage?

The three schemas claim to represent the same database, but:
- **SQL + Knex** represent a 2-table schema (categories ↔ categories self-reference)
- **Prisma** represents a 2-table schema **with a required relationship** (products → categories)

The Prisma version shows more complete domain logic (products must belong to a category), but SQL/Knex have no mechanism for this constraint.

---

## **3. Voice Consistency** — Same audience, same technical level?

Each is written in its native idiom (SQL DDL, Knex fluent API, Prisma SDL). ✅ Appropriate for their consumers. **No issue here.**

---

## **4. Naming Coherence** — Same concepts, same names?

| Concept | SQL | Knex | Prisma |
|---------|-----|------|--------|
| Parent category | `parent_id` | `parent_id` | `parentId` + `parent` relation |
| Weight field | `weight_kg` | `weight_kg` | `weightKg` |
| Stock quantity | `quantity_in_stock` | `quantity_in_stock` | `quantityInStock` |

✅ **Naming is consistent within each artifact's convention** (snake_case for SQL/Knex, camelCase for Prisma with @map annotations). But the **Prisma schema adds semantic names** (`parent`, `children`, `category`, `products` relations) that don't exist in SQL/Knex.

---

## **5. Framing Precision** — Does the scope match what's actually included?

All three are framed as "products and categories schema," but:
- **SQL/Knex frame**: Self-referential category hierarchy, products table with no category link
- **Prisma frame**: Products explicitly linked to categories (required FK relationship)

The **Prisma version reframes the domain**: products *must* belong to a category. The SQL/Knex versions don't enforce or even enable this relationship.

---

## **6. Origin Fidelity** — Is the motivation accurate?

This is unclear without context, but the **Prisma divergence** (adding `category_id` FK) suggests either:
- The original SQL schema is incomplete/outdated
- The Prisma schema over-models the relationship
- These are *different implementations* of a similar idea, not the same schema in three languages

---

## **7. Tone Calibration** — Does confidence match the work's maturity?

All three present themselves as production-ready ("CREATE TABLE", "PRIMARY KEY", indexes). But the **inconsistencies undermine that promise**. A Prisma user would have a required constraint missing in the SQL schema.

---

## **8. Category Accuracy** — Are things classified correctly?

- **SQL/Knex**: Treat `products` and `categories` as standalone tables
- **Prisma**: Treats them as **related domain models** with enforced relationships

**Issue**: Prisma adds structural semantics (required FK) that SQL/Knex don't express. These aren't equivalent schemas—they're **different schemas wearing the same name**.

---

## **9. Cross-Reference Redundancy** — Does each location add value?

If these three are meant to be kept in sync (e.g., "SQL is source of truth, Knex is the migration, Prisma is the ORM mapping"), then:
- **SQL ↔ Knex**: ~95% overlap, minor redundancy
- **Knex ↔ Prisma**: ~40% divergence (image_url, category_id, index definitions missing in Prisma)

You're storing **three partially-inconsistent definitions** of the schema. A single source of truth (e.g., SQL + generated migrations + Prisma from SQL) would be more maintainable.

---

## **10. Scope Discipline** — Is everything here about *this* schema?

✅ Yes. Each artifact stays focused on schema definition.

---

## **Summary of Issues by Severity**

| Severity | Issue | Fix |
|----------|-------|-----|
| 🔴 **CRITICAL** | **Prisma adds `category_id` FK** that SQL/Knex don't define | Decide: Is products→categories relationship required? Update all three consistently |
| 🔴 **CRITICAL** | **Prisma loses index definitions** entirely | Add `@@index` directives to Prisma schema or document why they're not needed |
| 🟠 **HIGH** | **description field nullability mismatch** (NOT NULL vs nullable vs optional) | Update SQL schema to match intent: `description TEXT` or `description TEXT NOT NULL` |
| 🟠 **HIGH** | **image_url exists in Knex/Prisma but not SQL** | Either add to SQL or remove from migration/Prisma |
| 🟡 **MEDIUM** | **Floating-point types in Prisma** (unitPrice, weightKg as Float vs DECIMAL/NUMERIC) | Use `Decimal` type in Prisma + prisma/decimal.ts extension, or confirm Float precision is acceptable |
| 🟡 **MEDIUM** | **parent_id unsigned integer in Knex** | Remove `.unsigned()` on parent_id self-reference—integers can be negative or null |

---

**Recommendation**: Choose a **single source of truth** (likely the SQL schema), then generate the others from it, or keep all three and establish a synchronization protocol with explicit tests.
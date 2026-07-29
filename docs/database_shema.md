# HBntory — Database Schema Documentation

**Related files**: `backoffice/models.py`, `backoffice/init_db.py`, `backoffice/stock_service.py`

---

## 1. Guiding principle: data separation

The Backoffice database stores **local system data only**: users, branches and stock quantities.

Every piece of product information (name, description, price, image, category, supplier, metadata) comes **exclusively from the external Product API**. The local database only keeps the **product identifier**, which acts as a plain reference to that API.

**Rationale**: the Product API is the *single source of truth* for product data. Duplicating that information locally would create a desynchronisation risk (if a price or a name changes in the API, the local copy would become stale with no mechanism to detect it). By storing only the identifier, inconsistent product data between the two systems becomes impossible.

---

## 2. Schema overview

The schema contains **three tables**, deliberately limited to what is strictly required. No table was added for the sake of "realism": each one answers an explicit requirement of the specification.

```
branches (1) ──────< (N) users
    │
    └──────────────< (N) stock ──── references ────> External Product API
                                     (id_product)
```

- A branch can have several users; a common user belongs to exactly one branch.
- A branch can have several stock rows; each stock row belongs to a single branch.
- Each stock row references an external product identifier, without ever storing its details.

---

## 3. `branches` table

Represents the company's physical branches.

| Column | SQL type | Constraints | Purpose |
|---|---|---|---|
| `id` | Integer | Primary key | Internal branch identifier |
| `name` | String(100) | `NOT NULL`, `UNIQUE` | Branch name (e.g. "North Branch") |
| `created_at` | DateTime | `NOT NULL` | Record creation timestamp |
| `updated_at` | DateTime | `NOT NULL` | Last modification timestamp |

**Design decisions:**

- **Dedicated table instead of free-text names.** Writing the branch name directly into `users` and `stock` would have exposed the system to typos (`"North"`, `"north"`, `"North Branch"` treated as three different branches) and would have made renaming expensive (updating dozens of rows across several tables). With a dedicated table, the name exists in exactly one place and the other tables only reference the `id`.
- **`UNIQUE` constraint on `name`.** Prevents the creation of two identically named branches, which would be ambiguous for users and for the AI agent alike.
- **No active/deleted status column.** The specification only requires soft deletion for users. Adding an `is_active` column on branches would have been an unrequested feature. It can be added later if a real need arises.

---

## 4. `users` table

Represents Backoffice accounts: the single administrator and the common users.

| Column | SQL type | Constraints | Purpose |
|---|---|---|---|
| `id` | Integer | Primary key | Internal user identifier |
| `username` | String(50) | `NOT NULL`, `UNIQUE` | Login identifier |
| `password_hash` | String(255) | `NOT NULL` | bcrypt digest of the password (never the plain-text password) |
| `role` | String(100) | `NOT NULL` | `"admin"` or `"common_user"` |
| `branch_id` | Integer | `FOREIGN KEY → branches.id`, **nullable** | Assigned branch |
| `is_active` | Boolean | `NOT NULL`, default `True` | Soft delete flag |
| `created_at` | DateTime | `NOT NULL` | Account creation timestamp |
| `updated_at` | DateTime | `NOT NULL` | Last modification timestamp |

**Design decisions:**

- **`username` is `UNIQUE`.** Two accounts sharing the same login identifier would make authentication ambiguous: the system would not know which account to verify. The constraint is declared directly on the column (`unique=True`) rather than through a composite `UniqueConstraint`, since only one column is involved.
- **`branch_id` is nullable.** The administrator manages no stock and is therefore attached to no branch: their `branch_id` value is `NULL`. Making the column mandatory would have forced us to artificially attach the admin to an arbitrary branch, which would have been inconsistent with their role.
  *Known limitation:* the database alone does not prevent creating a common user without a branch. The rule "if `role = common_user`, then `branch_id` is mandatory" belongs to application logic and is enforced on the Backoffice side when an account is created.
- **`is_active` instead of physical deletion.** The specification requires a *soft delete*: a deleted account must keep its record. A plain SQL `DELETE` would have destroyed the row and, as a side effect, endangered the referential integrity of historical data. Setting `is_active` to `False` disables the account while preserving all existing stock records, which are never linked to a user but to a branch.
- **`role` is not unique.** The role is a category shared by several accounts (multiple common users coexist). Any uniqueness constraint on this column would have forbidden creating more than one user per role.

---

## 5. `stock` table

Represents available quantities, per (product, branch) pair.

| Column | SQL type | Constraints | Purpose |
|---|---|---|---|
| `id` | Integer | Primary key | Internal stock row identifier |
| `id_product` | String(50) | `NOT NULL` | Product identifier in the external API (e.g. `HB-LAP-1001`) |
| `id_branch` | Integer | `FOREIGN KEY → branches.id`, `NOT NULL` | Branch concerned |
| `quantity` | Integer | `NOT NULL`, `CHECK (quantity >= 0)` | Available quantity |

**Table-level constraints:**

```python
__table_args__ = (
    UniqueConstraint('id_product', 'id_branch', name='unique_product_branch'),
    CheckConstraint('quantity >= 0', name='check_quantity_non_negative'),
)
```

**Design decisions:**

- **`id_product` is `String(50)`, not `Integer`.** Product identifiers returned by the external API follow an alphanumeric format (`HB-LAP-1001`, `HB-KEY-2002`). An integer column could not have stored them.
- **`id_product` is not a foreign key.** The product does not exist in the local database: it lives in an external service queried over HTTP. A `FOREIGN KEY` constraint between a relational database and a remote API is technically impossible. The validity of the identifier must therefore be checked at application level, through a call to the Product API (see section 6).
- **Composite uniqueness constraint on `(id_product, id_branch)`.** Neither `id_product` nor `id_branch` should be unique on its own: the same product can be present in several branches, and a branch holds several products. It is the **combination** of the two that must be unique, so that exactly **one counter row** exists per (product, branch) pair. Without this constraint, two competing rows could exist for the same product in the same branch, and a lookup query would not know whether to sum the rows or keep only one of them.
  **Consequence for application code:** adding stock does not systematically create a new row. The code must first look for an existing row for the pair concerned; if it exists, it updates its `quantity` (`UPDATE`), otherwise it creates the row (`INSERT`).
- **`CHECK (quantity >= 0)` constraint.** Guarantees at database-engine level that no negative quantity can ever be stored, regardless of the write path used.

---

## 6. Validation rules and where they live

Validation is split across **two complementary levels**. This is a deliberate choice: each level covers what the other cannot do.

### Database level — the safety net

| Rule | Mechanism |
|---|---|
| Quantity can never be negative | `CheckConstraint('quantity >= 0')` |
| Stock always references an existing branch | `ForeignKey('branches.id')` |
| No duplicate (product, branch) pair | `UniqueConstraint('id_product', 'id_branch')` |
| No duplicate login identifier | `unique=True` on `users.username` |

**Purpose of this level:** guaranteeing data integrity **no matter what happens**, including in the event of an application bug, a manual write to the database, or code written later that would bypass the service functions. An SQL constraint cannot be "forgotten" by a developer.

### Python application level — business rules and clear messages

Implemented in `backoffice/stock_service.py`:

```python
def remove_stock(session, stock_item, quantity_to_remove):
    if not isinstance(quantity_to_remove, int) or quantity_to_remove <= 0:
        raise ValueError("Quantity to remove must be a positive integer.")
    if stock_item.quantity < quantity_to_remove:
        raise ValueError(f"Cannot remove {quantity_to_remove} from stock item "
                         f"with only {stock_item.quantity} available.")
    stock_item.quantity -= quantity_to_remove
    session.commit()
```

| Rule | Mechanism |
|---|---|
| Requested quantity is an integer | `isinstance(quantity, int)` |
| Requested quantity is strictly positive | `quantity <= 0` rejected |
| Removal does not exceed available stock | comparison before modification |
| Product identifier exists in the external API | call to the Product API *(to be implemented — Task 3.3)* |

**Purpose of this level:**

1. **Producing understandable messages.** A violated SQL constraint surfaces as a technical `IntegrityError` (`CHECK constraint failed`), which is unusable for a non-technical user. Python-level validation makes it possible to display "You cannot remove 50 units, only 30 are available".
2. **Covering rules beyond the reach of SQL.** A database cannot query an external HTTP API to verify that a product identifier really exists. This check can only be performed at application level.
3. **Checking input types.** A column typed as `Integer` offers no protection against a `2.5` or a string submitted through a form: it is up to the code to reject those values upstream.

### Implementation detail: order of checks

The two conditions on the first line are evaluated in a specific order:

```python
if not isinstance(quantity_to_remove, int) or quantity_to_remove <= 0:
```

The type check is placed **before** the numeric comparison. Python evaluates an `or` from left to right and stops as soon as one condition is true. Were the order reversed, a value such as `"ten"` would raise a raw `TypeError` on the `"ten" <= 0` comparison before ever reaching the type check — and the user would receive a technical error message instead of the intended business message.

### Asymmetry between reads and writes

Failures of the external Product API are handled differently depending on
whether the operation reads or writes.

**Reads degrade gracefully.** If the catalogue is unreachable, the stock page
still renders: quantities come from our own database and remain accurate, only
product names fall back to "Unknown product". Blocking the page would deny
users access to data we hold ourselves.

**Writes are refused.** Adding stock requires the product identifier to be
confirmed against the catalogue. If that confirmation cannot be obtained —
whether because the SKU does not exist or because the API is down — the
insertion is rejected.

The reasoning behind the asymmetry: a missing product name is a temporary
display gap with no lasting consequence, whereas an unverified identifier would
be written to the database permanently. That row would then be read by the MCP
server and surfaced to the AI agent, propagating an invalid reference across
two services. An operation that cannot be validated is not performed.

Two distinct exceptions make the distinction visible to the user:
`ProductNotFoundError` produces a message inviting them to check the identifier
they typed, while `ProductAPIError` states that the catalogue is temporarily
unavailable and the operation should be retried later. Reporting an unreachable
API as a non-existent product would send the user looking for a typo in a
perfectly valid SKU.

**Removals are not subject to this check.** A stock row can only exist if its
identifier was validated at insertion time. Blocking removals during an API
outage would prevent legitimate work with no integrity benefit.

---

## 7. Database initialisation

Script: `backoffice/init_db.py`

It creates the tables if needed (`Base.metadata.create_all(engine)`) and then inserts a minimal dataset:

- **1 administrator account** (`admin`), whose password is hashed with bcrypt before insertion and read from the `ADMIN_PASSWORD` environment variable (`.env` file, excluded from the Git repository). No plain-text password is written in the source code or stored in the database.
- **2 branches**: `North Branch` and `South Branch`.
- **3 stock rows**, two of which deliberately carry the **same product identifier in two different branches** (`HB-LAP-1001` in North with 100 units, and in South with 30 units). This test case validates that the composite uniqueness constraint does allow this scenario, and that a stock lookup without a specified branch returns a list of results rather than a single value.

**Execution order imposed by foreign keys:** branches must be created and committed before stock rows, because their `id` — generated by the database — is only available in the Python objects after the commit. It is then used to populate `stock.id_branch`.

**Compatibility note:** the development environment uses SQLite (`hbntory.db`), whereas the Docker deployment targets PostgreSQL 16. No change to the SQLAlchemy models is required for this switch: only the connection string passed to `create_engine()` differs.

---

## 8. Expected behaviour when consulting stock

An important distinction has been adopted for lookups, and will be reused by the MCP server tools:

- **Valid product and valid branch, but no row in the database for that combination** → this is **not** an error: the answer is a quantity of **0**. The information is available, its value is simply zero.
- **Product identifier that does not exist in the external API, or non-existent branch** → this is **invalid data**. The system must state that the information is unavailable, without inventing a value.

This distinction is consistent with the specification's requirement that the AI agent must never invent information and must explicitly state when data is unavailable.
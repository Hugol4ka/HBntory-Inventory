# Product MCP Server — Documentation

This document describes the Product MCP Server of the `HBntory-Inventory` project: the tools it exposes, the data sources it bridges, its error-handling strategy, and evidence of manual test execution.

---

## 1. Purpose

The Product MCP Server is the single data boundary of the AI system. It exposes six tools over the Model Context Protocol, bridging two distinct sources:

- the **external Products API**, read-only, for catalog information;
- the **local PostgreSQL database**, for branches and stock quantities.

The AI Query Service never reaches either source directly. Every fact it uses comes through one of these tools.

```
   AI Query Service
        │  MCP over streamable-http
        ▼
  Product MCP Server ──────► External Products API   (catalog)
                     └─────► PostgreSQL              (branches, stock)
```

### Files

| File | Responsibility |
|---|---|
| `server.py` | Entry point: imports tool modules, starts the MCP server |
| `mcp_instance.py` | Holds the shared `FastMCP` instance |
| `tools/catalog.py` | Tools backed by the external Products API |
| `tools/stock.py` | Tools backed by PostgreSQL |
| `database.py` | SQLAlchemy engine, configured from `DATABASE_URL` |
| `models.py` | SQLAlchemy models (`Branch`, `User`, `Stock`) |

The `mcp_instance.py` module exists to avoid a circular import: the tool modules need the `mcp` object to register their decorators, while `server.py` needs the tool modules to be loaded before starting. Isolating the instance in its own module lets both depend on it without depending on each other.

---

## 2. Transport

The server runs over **streamable-http**, the transport recommended by the current MCP specification, listening on `HBN_MCP_PORT` (5000 inside the container, mapped to 5003 on the host) at the path `/mcp`.

An earlier version used **stdio**, with the AI Query Service spawning the server as a local subprocess. That design cannot survive containerisation: a container cannot spawn a process living in another container. Switching to a network transport was required for the `docker compose` deployment, and matches what the compose file anticipated from the start with its `HBN_AI_MCP_URL` variable.

---

## 3. Exposed Tools

| Tool | Source | Input | Output |
|---|---|---|---|
| `list_products` | Products API | — | Full catalog |
| `get_product` | Products API | `product_id` (string: numeric ID or SKU) | Product details |
| `list_branches` | PostgreSQL | — | All branches (`id`, `name`) |
| `get_stock_by_product` | PostgreSQL | `sku` (string) | Quantity per branch |
| `get_stock_by_branch` | PostgreSQL + Products API | `branch_id` (integer) | Products in that branch, with names |
| `check_shopping_list` | PostgreSQL | `items`: list of `{sku, quantity}` | Feasibility verdict per branch |

### Product identification

Products are identified differently on each side of the boundary. The external API accepts either a numeric ID (`1`) or a SKU (`HB-LAP-1001`). The local `stock` table keys on SKU only.

This asymmetry means a stock question starting from a numeric ID requires two calls: `get_product` to resolve the SKU, then the relevant stock tool. The tool descriptions state this explicitly so the agent can chain them correctly.

### Tool descriptions matter

Each tool's docstring is what FastMCP transmits to the model as its official description — it is the only information available for choosing a tool and building its arguments.

Early descriptions were too terse and too similar to one another, producing a stream of `Invalid arguments` warnings in the server logs: `get_stock_by_branch` received a `product_id` it does not accept, `get_product` received the integer `1` where a string was expected. Each failed call forced an extra round trip through the model, inflating response times.

Rewriting the docstrings to state, for each tool, **what it takes**, **what it returns**, **which question it answers**, and **a concrete example value** eliminated those warnings entirely.

### A deliberate exception: `get_stock_by_branch`

Every tool draws from a single source, with one exception. `get_stock_by_branch` queries PostgreSQL for the SKUs held in a branch, then calls the Products API once to attach a product name to each.

The original design kept it database-only, expecting the agent to cross-reference the SKUs against `list_products` itself. That expectation proved unreliable: the agent frequently skipped the second call and presented raw SKUs to the user. Performing the join server-side made the behaviour deterministic, at the cost of one extra HTTP request inside the tool.

If the catalog is unreachable, quantities are still returned with the name marked unavailable — a partial answer rather than a failure.

---

## 4. Error Handling

The server never lets an exception propagate to the agent. Every tool returns structured JSON, whether it succeeds or fails.

### External Products API

**HTTP 404.** `get_product` checks `response.status_code == 404` *before* calling `raise_for_status()`. Order matters: `raise_for_status()` raises on any status ≥ 400, so checking afterwards would collapse a meaningful "product not found" into a generic connection error.

**Network failures.** All outgoing requests are wrapped in `try / except httpx.HTTPError` — the parent class covering timeouts, DNS failures, refused connections and 5xx responses alike. The exception becomes a readable payload rather than a Python traceback.

### PostgreSQL

**Database errors.** All database access is wrapped in `try / except SQLAlchemyError`, the parent class for every SQLAlchemy failure. Same principle, same output shape.

**Session scope.** Every query runs inside `with Session(engine) as session:`, guaranteeing the connection is released whether the block completes or raises.

### Business outcomes are not errors

A product not stocked in a branch, or a branch holding too few units, are valid answers — not exceptions. They appear as `"ok": false` with a descriptive `issues` message, or as an empty `stock` list.

This distinction matters for grounding: the agent must be able to tell "the system failed to answer" (an `error` key, caused by an exception) from "the system answered clearly that this cannot be satisfied" (a well-formed negative result).

### Three distinct negative outcomes

`_has_enough_stock` separates cases that would otherwise produce identical messages:

| Situation | Message |
|---|---|
| SKU exists nowhere in the inventory | `Unknown SKU 'X': no stock record exists for this product in any branch. Check the SKU spelling.` |
| SKU exists, not stocked in this branch | `Product X is not available at branch N.` |
| SKU stocked here, insufficient quantity | `Product X has only N in stock at branch M, but Q were requested.` |

The first case was added after the model mistyped a SKU when building tool arguments (`HB-KBD-41002` instead of `HB-KBD-4102`). The tool correctly reported that this product was unavailable everywhere, and the agent faithfully relayed that verdict — producing a factually wrong answer from correctly grounded data. Distinguishing an unknown reference from an unavailable product turns a wrong answer into an honest one.

`get_stock_by_branch` applies the same principle to branches: it verifies the branch exists before querying, returning an explicit error rather than an empty list for a non-existent ID.

---

## 5. Manual Test Evidence

Tests were executed against the running Docker deployment using the official **MCP Inspector**, connected over streamable HTTP to `http://localhost:5003/mcp`.

```bash
npx @modelcontextprotocol/inspector
```

The server must not be launched a second time from Inspector: the container already holds port 5003, and a stdio invocation would not match the HTTP transport.

Reference data in the inventory database:

| SKU | Branch | Quantity |
|---|---|---|
| HB-LAP-1001 | North Branch (1) | 100 |
| HB-SSD-7101 | North Branch (1) | 20 |
| HB-LAP-1001 | South Branch (2) | 30 |
| HB-KBD-4102 | South Branch (2) | 50 |

### Test 1: `list_products`

- **Objective**: Verify the catalog is fetched from the external API.
- **Input**: none
- **Result**: HTTP 200, 39 products returned, paginated at 20 per page.

```json
{
  "count": 39,
  "limit": 20,
  "offset": 0,
  "results": [
    {
      "id": 1,
      "sku": "HB-LAP-1001",
      "name": "Holberton Student Laptop 14",
      "category": "Laptops",
      "brand": "Holberton",
      "unit_price": 799.0,
      "currency": "USD",
      "discontinued": false
    }
  ]
}
```

*(one entry shown, 20 returned)*

### Test 2: `get_product` — existing product

- **Objective**: Verify details are retrieved for a specific product.
- **Input**: `product_id = "1"`
- **Result**: Full record including nested supplier metadata.

```json
{
  "id": 1,
  "sku": "HB-LAP-1001",
  "name": "Holberton Student Laptop 14",
  "description": "Training catalog item for HBntory integration: holberton student laptop 14.",
  "category": "Laptops",
  "brand": "Holberton",
  "unit_price": 799.0,
  "currency": "USD",
  "discontinued": false,
  "weight_kg": 1.35,
  "tags": ["student", "portable", "linux-ready"],
  "supplier": {
    "id": "SUP-HBT-001",
    "name": "Holberton Tools Co.",
    "contact_email": "catalog@holberton-tools.example",
    "country": "US",
    "lead_time_days": 5,
    "reliability_score": 0.97
  }
}
```

### Test 3: `get_product` — non-existent product

- **Objective**: Verify explicit 404 handling.
- **Input**: `product_id = "999999"`
- **Result**: Clean error payload, no exception raised.

```json
{ "error": "Product with ID '999999' not found" }
```

### Test 4: External API unavailable

- **Objective**: Verify network failures are caught without crashing the server.
- **Procedure**: Stop the `external-products-api` container, then call `list_products`.
- **Result**:

```json
{
  "error": "Impossible to communicate with the external products API",
  "details": "All connection attempts failed"
}
```

### Test 5: `list_branches`

- **Objective**: Verify branches are read from PostgreSQL.
- **Input**: none
- **Result**:

```json
[
  { "id": 1, "name": "North Branch" },
  { "id": 2, "name": "South Branch" }
]
```

### Test 6: `get_stock_by_product`

- **Objective**: Verify a database join returns per-branch quantities with branch names.
- **Input**: `sku = "HB-LAP-1001"`
- **Result**:

```json
{
  "sku": "HB-LAP-1001",
  "stock": [
    { "branch_id": 1, "branch_name": "North Branch", "quantity": 100 },
    { "branch_id": 2, "branch_name": "South Branch", "quantity": 30 }
  ]
}
```

### Test 7: `get_stock_by_branch`

- **Objective**: Verify branch stock is returned with catalog names attached.
- **Input**: `branch_id = 1`
- **Result**: Both the branch name and the product names resolved server-side.

```json
{
  "branch_id": 1,
  "branch_name": "North Branch",
  "quantity_by_product": [
    { "sku": "HB-LAP-1001", "quantity": 100, "name": "Holberton Student Laptop 14" },
    { "sku": "HB-SSD-7101", "quantity": 20, "name": "External SSD 1TB" }
  ]
}
```

### Test 8: `get_stock_by_branch` — non-existent branch

- **Objective**: Verify an invalid branch ID is rejected rather than returning an empty list.
- **Input**: `branch_id = 99`
- **Result**:

```json
{ "error": "Branch 99 does not exist." }
```

### Test 9: `check_shopping_list` — satisfiable

- **Objective**: Verify the feasibility calculation across a multi-product list.
- **Input**:

```json
[
  { "sku": "HB-LAP-1001", "quantity": 5 },
  { "sku": "HB-KBD-4102", "quantity": 2 }
]
```

- **Result**: South Branch holds both products in sufficient quantity; North Branch does not stock the keyboard.

```json
{
  "feasible_branches": ["South Branch"],
  "details": {
    "North Branch": {
      "ok": false,
      "issues": ["Product HB-KBD-4102 is not available at branch 1."]
    },
    "South Branch": { "ok": true, "issues": [] }
  }
}
```

### Test 10: `check_shopping_list` — unknown SKU

- **Objective**: Verify a non-existent product reference is distinguished from an unavailable one.
- **Input**:

```json
[{ "sku": "HB-KBD-99999", "quantity": 1 }]
```

- **Result**:

```json
{
  "feasible_branches": [],
  "details": {
    "North Branch": {
      "ok": false,
      "issues": ["Unknown SKU 'HB-KBD-99999': no stock record exists for this product in any branch. Check the SKU spelling."]
    },
    "South Branch": {
      "ok": false,
      "issues": ["Unknown SKU 'HB-KBD-99999': no stock record exists for this product in any branch. Check the SKU spelling."]
    }
  }
}
```

---

## 6. Configuration

| Variable | Default | Purpose |
|---|---|---|
| `HBN_MCP_API_URL` | `http://localhost:5001` | External Products API base URL |
| `HBN_MCP_PORT` | `5003` | Port the MCP server listens on (`5000` in Docker) |
| `DATABASE_URL` | `sqlite:///<module dir>/hbntory.db` | Database connection string (PostgreSQL in Docker) |

### The database path

`DATABASE_URL` falls back to a SQLite file whose path is computed from the module's own location:

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "hbntory.db")
```

A relative path would resolve against the working directory of whatever process started the server — which changed once the AI Query Service began launching it as a subprocess from another folder, silently pointing SQLAlchemy at a non-existent file. Anchoring on `__file__` makes the default independent of the launch directory.

In Docker, `DATABASE_URL` points at PostgreSQL and the fallback is never used.

### Running

```bash
# In Docker, alongside the rest of the stack
docker compose up -d mcpserver

# Standalone, for local testing
cd product_mcp_server && python server.py
```

Requires a reachable Products API and database.

---

## 7. Known Limitations

**`models.py` is duplicated.** The SQLAlchemy models are copied between `backoffice/` and `product_mcp_server/`, because each service builds its Docker image from its own directory and cannot reach a shared folder. The two copies must be kept in sync manually.

This has already caused one incident: `Stock.id_product` was changed from `Integer` to `String(50)` in the back-office copy when the project moved from numeric IDs to SKUs, but not in the MCP server copy. Every stock query then failed with a type mismatch against a `character varying` column, and the AI service reported that stock information was unavailable — a correct grounded answer to a broken query.

A `shared/` directory imported by both services would remove the duplication, but requires changing the build context of both images in `docker-compose.yml`.

**Referential integrity is not enforced across systems.** `Stock.id_product` carries no foreign key, since the product catalog lives in the external API rather than in the local database — SQLAlchemy cannot constrain a column against a table that does not exist locally. Nothing prevents a stock row referencing a SKU absent from the catalog, or a catalog product being removed while stock rows survive. The correspondence is maintained by convention only.

This is an architectural consequence of splitting product data across two systems, not an oversight.

**Unknown SKUs are reported inconsistently.** `check_shopping_list` returns an explicit *Unknown SKU* message, while `get_stock_by_product` returns an empty `stock` list for the same situation — technically accurate, but silent about the distinction between "this product exists and is out of stock everywhere" and "this SKU does not exist". The AI service currently compensates through a prompt rule; aligning the two tools would be more robust.

**Supplier metadata is returned unfiltered.** `get_product` passes through everything the external API provides, including contact emails, lead times and supplier reliability scores. These reach the public client when the agent lists product details. Trimming the response would require deciding which fields are legitimately public.

**Restarting the server invalidates open sessions.** MCP sessions are negotiated at connection time. Rebuilding or restarting this server leaves connected clients holding a dead session id, and every subsequent tool call fails with `Session terminated` until they reconnect. The AI Query Service handles this by catching the error and reconnecting once.
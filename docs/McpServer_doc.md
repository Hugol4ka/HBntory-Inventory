# Manual Test Documentation — Product MCP Server

This document provides evidence of manual test execution for the `HBntory-Inventory` Product MCP Server, along with a detailed explanation of the error handling strategy.

---

## 1. Environment & Test Protocol

Tests were executed using the official **MCP Inspector** tool (`@modelcontextprotocol/inspector`).

### Launch Command

```bash
npx @modelcontextprotocol/inspector python product_mcp_server/server.py
```

### Data Sources

The MCP server bridges two distinct data sources, each accessed by a dedicated set of tools:

| Source | Tools |
|---|---|
| External Product API (`httpx`) | `list_products`, `get_product` |
| Local Inventory Database (SQLAlchemy / SQLite) | `list_branches`, `get_stock_by_product`, `get_stock_by_branch`, `check_shopping_list` |

---

## 2. Test Scenarios & Execution Evidence

### Test 1: Global Product List (`list_products`)

- **Objective**: Verify that the MCP server successfully fetches the product catalog from the external API.
- **Input**: None.
- **Expected Result**: HTTP 200 — Structured JSON list of products.
- **Actual Result**:

```json
{
  "count": 39,
  "limit": 20,
  "offset": 0,
  "results": [
    {
      "id": 4,
      "sku": "HB-MON-2102",
      "name": "24 inch Compact Monitor",
      "category": "Displays",
      "unit_price": 169.99,
      "currency": "USD",
      "discontinued": false
    },
    {
      "id": 1,
      "sku": "HB-LAP-1001",
      "name": "Holberton Student Laptop 14",
      "category": "Laptops",
      "unit_price": 799,
      "currency": "USD",
      "discontinued": false
    }
  ]
}
```

---

### Test 2: Details of an Existing Product (`get_product`)

- **Objective**: Validate fetching details for a specific product by ID or SKU.
- **Input**: `product_id = "1"`
- **Expected Result**: HTTP 200 — Detailed product information enriched with supplier metadata.
- **Actual Result**:

```json
{
  "id": 1,
  "sku": "HB-LAP-1001",
  "name": "Holberton Student Laptop 14",
  "description": "Training catalog item for HBntory integration: holberton student laptop 14.",
  "category": "Laptops",
  "unit_price": 799,
  "currency": "USD",
  "supplier": {
    "id": "SUP-HBT-001",
    "name": "Holberton Tools Co.",
    "contact_email": "catalog@holberton-tools.example"
  }
}
```

---

### Test 3: Product Not Found / 404 Error (`get_product`)

- **Objective**: Verify explicit handling of non-existent product identifiers.
- **Input**: `product_id = "999999"`
- **Expected Result**: Gracefully caught 404 error returning an informative JSON response.
- **Actual Result**:

```json
{
  "error": "Product with ID '999999' not found"
}
```

---

### Test 4: External Service Outage / Network Error (`httpx.HTTPError`)

- **Procedure**: Temporarily stop the `external-products-api` container.
- **Tool Executed**: `list_products()`
- **Expected Result**: Catch network connection errors without server crashes.
- **Actual Result**:

```json
{
  "error": "Impossible to communicate with the external products API",
  "details": "All connection attempts failed"
}
```

---

### Test 5: List All Branches (`list_branches`)

- **Objective**: Verify that the MCP server successfully retrieves the list of branches from the local inventory database.
- **Input**: None.
- **Expected Result**: A JSON array of branches with `id` and `name`.
- **Actual Result**:

```json
[
  { "id": 1, "name": "North Branch" },
  { "id": 2, "name": "South Branch" }
]
```

---

### Test 6: Stock of a Product Across Branches (`get_stock_by_product`)

- **Objective**: Verify that the MCP server correctly aggregates, via a database join, the stock quantities of a single product across all branches.
- **Input**: `product_id = 1`
- **Expected Result**: A JSON object listing the quantity of the product in every branch where it is stocked.
- **Actual Result**:

```json
{
  "product_id": 1,
  "stock": [
    { "branch_id": 1, "branch_name": "North Branch", "quantity": 100 },
    { "branch_id": 2, "branch_name": "South Branch", "quantity": 30 }
  ]
}
```

---

### Test 7: Stock of a Branch (`get_stock_by_branch`)

- **Objective**: Verify that the MCP server correctly lists all products (and quantities) stocked in a given branch.
- **Input**: `branch_id = 1`
- **Expected Result**: A JSON object listing every product present in that branch, with its quantity.
- **Actual Result**:

```json
{
  "branch_id": 1,
  "stock": [
    { "product_id": 1, "quantity": 100 }
  ]
}
```

---

### Test 8: Shopping List Feasibility (`check_shopping_list`)

- **Objective**: Verify that the MCP server correctly determines which branches can fully satisfy a list of desired products and quantities, and that it distinguishes between "insufficient stock" and "product not stocked at all" in a single branch.

**Case A — Feasible in both branches**

- **Input**: `items = [{"product_id": 1, "quantity": 5}]`
- **Actual Result**:

```json
{
  "feasible_branches": ["North Branch", "South Branch"],
  "details": {
    "North Branch": { "ok": true, "issues": [] },
    "South Branch": { "ok": true, "issues": [] }
  }
}
```

**Case B — Not feasible anywhere (quantity exceeds all stock)**

- **Input**: `items = [{"product_id": 1, "quantity": 9999}]`
- **Actual Result**:

```json
{
  "feasible_branches": [],
  "details": {
    "North Branch": {
      "ok": false,
      "issues": ["Product 1 has only 100 in stock at branch 1, but 9999 were requested."]
    },
    "South Branch": {
      "ok": false,
      "issues": ["Product 1 has only 30 in stock at branch 2, but 9999 were requested."]
    }
  }
}
```

**Case C — Product entirely absent from one branch**

- **Input**: `items = [{"product_id": 2, "quantity": 1}]`
- **Actual Result**:

```json
{
  "feasible_branches": ["South Branch"],
  "details": {
    "North Branch": {
      "ok": false,
      "issues": ["Product 2 is not available at branch 1."]
    },
    "South Branch": { "ok": true, "issues": [] }
  }
}
```

---

## 3. Explanation of Error Handling

The MCP server implements a defensive strategy to ensure stability and seamless AI agent interaction. Error handling differs slightly depending on the data source being queried.

### 3.1 External Product API (`list_products`, `get_product`)

1. **HTTP 404 Errors (Resource Not Found)**: When an invalid product ID is requested, the external API responds with HTTP status 404. The MCP server explicitly checks `response.status_code == 404` prior to calling `raise_for_status()`. It returns a clean JSON error structure (`{"error": "..."}`) so the AI agent understands the resource does not exist and can inform the user gracefully instead of failing abruptly.

2. **Network Errors and API Unavailability (`httpx.HTTPError`)**: All outgoing HTTP requests are wrapped inside `try / except httpx.HTTPError` blocks. In the event of network timeouts, server outages, or 5xx HTTP errors, the exception is intercepted and converted into a readable error payload. This prevents Python stack traces from leaking to the client and keeps the MCP server running smoothly.

### 3.2 Local Inventory Database (`list_branches`, `get_stock_by_product`, `get_stock_by_branch`, `check_shopping_list`)

3. **Database Connection / Query Errors (`sqlalchemy.exc.SQLAlchemyError`)**: All database access is wrapped inside `try / except SQLAlchemyError` blocks — the parent exception class for all SQLAlchemy errors (connection issues, locked database, malformed queries, etc.). On failure, a structured JSON error is returned instead of letting the exception propagate, following the same defensive pattern used for the external API.

4. **Absence of Data vs. Insufficient Data**: Business-level "failures" (a product not stocked in a branch, or a branch not holding enough quantity to satisfy a request) are **not** treated as exceptions. They are valid, expected outcomes represented explicitly in the JSON response (e.g. `"ok": false` with a descriptive `issues` message in `check_shopping_list`, or an empty `stock` list). This distinction matters for grounding: the AI agent must be able to tell the difference between "the system failed to answer" (an `error` key, caused by an exception) and "the system answered clearly that the request cannot be satisfied" (a normal, well-formed response).

5. **Session Scope**: All database operations are performed within a `with Session(engine) as session:` context manager, ensuring the connection is properly released after each tool call, whether it succeeds or raises an exception.

### 3.3 Known Limitation

The local database does not enforce referential integrity between `Stock.id_product` and the product catalog exposed by the external API (no foreign key exists between them, since the catalog itself is not stored locally). The correspondence between a product's ID in the external API and in the local `Stock` table is maintained by convention only. This is a documented architectural limitation rather.
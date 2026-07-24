# Manual Test Documentation — Product MCP Server

This document provides evidence of manual test execution for the `HBntory-Inventory` Product MCP Server, along with a detailed explanation of the error handling strategy.

---

## 1. Environment & Test Protocol

Tests were executed using the official **MCP Inspector** tool (`@modelcontextprotocol/inspector`).

### Launch Command

```bash
npx @modelcontextprotocol/inspector python product_mcp_server/server.py
```

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

## 3. Explanation of Error Handling

The MCP server implements a defensive strategy to ensure stability and seamless AI agent interaction:

1. **HTTP 404 Errors (Resource Not Found)**: When an invalid product ID is requested, the external API responds with HTTP status 404. The MCP server explicitly checks `response.status_code == 404` prior to calling `raise_for_status()`. It returns a clean JSON error structure (`{"error": "..."}`) so the AI agent understands the resource does not exist and can inform the user gracefully instead of failing abruptly.

2. **Network Errors and API Unavailability (`httpx.HTTPError`)**: All outgoing HTTP requests are wrapped inside `try / except httpx.HTTPError` blocks. In the event of network timeouts, server outages, or 5xx HTTP errors, the exception is intercepted and converted into a readable error payload. This prevents Python stack traces from leaking to the client and keeps the MCP server running smoothly.

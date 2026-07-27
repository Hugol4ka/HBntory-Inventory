# AI Query Service — Documentation

This document describes the AI Query Service of the `HBntory-Inventory` project: the question types it supports, its client-facing communication protocol, its internal architecture, and evidence of manual test execution.

---

## 1. Overview

The AI Query Service is an independent backend service that receives natural-language questions from the Client Web Interface, retrieves real data through the Product MCP Server, and returns grounded answers.

It never accesses the products API or the inventory database directly: every piece of data it uses comes from a tool exposed by the Product MCP Server.

```
Client Web Interface
        │  POST /query { "question": "..." }
        ▼
   AI Query Service ──────► Ollama (local LLM)
        │
        ▼
  Product MCP Server ──────► External Products API
                     └─────► Local Inventory Database
```

### Components

| File | Responsibility |
|---|---|
| `main.py` | FastAPI application, `POST /query` endpoint, service lifecycle |
| `agent.py` | Two-stage agent: tool-calling stage, then answer-formulation stage |
| `mcp_client.py` | MCP client: connects to the Product MCP Server, discovers and calls tools |
| `config.py` | Environment-driven configuration (model, host, ports, limits) |

---

## 2. Supported Question Types

The service answers four categories of questions. Any question outside this scope receives an explicit, polite refusal rather than an attempted answer.

| # | Question type | Example | Tools used |
|---|---|---|---|
| 1 | Product details | *"Give me the details of the product with ID 1"* | `get_product`, `list_products` |
| 2 | Where a product is available | *"Where can I find product 1?"* | `get_stock_by_product` |
| 3 | What is available in a branch | *"Which products are available at North Branch?"* | `list_branches`, `get_stock_by_branch`, `list_products` |
| 4 | Shopping list feasibility | *"Can I buy 5 units of product 1 and 2 units of product 2 in a single branch?"* | `check_shopping_list` |

### Out-of-scope handling

Questions unrelated to products, stock or branches are declined explicitly. The refusal is a natural consequence of the architecture: when the tool-calling stage retrieves no data, the answer stage receives an empty result set and applies its scope rules.

**Example** — Input: *"What is the weather in Paris?"*

```json
{
  "answer": "This type of request is not supported by this assistant. Additionally, no data was retrieved to provide information about the weather in Paris.",
  "tool_calls": []
}
```

---

## 3. Client Communication Protocol: REST

**The AI Query Service uses REST (HTTP), not WebSockets.**

### Rationale

- **No conversation history is required.** Each request is fully independent and stateless, so the persistent connection that WebSockets provide brings no benefit.
- **Simplicity of integration.** A single `POST` request is trivial to call from the Client Web Interface, from `curl`, or from automated tests.
- **Operational simplicity.** REST works out of the box behind standard reverse proxies and Docker port mappings, with no additional protocol handling.

WebSockets would become the better choice if the service later needed to stream partial answers token by token, or to maintain a multi-turn conversation — neither of which is a requirement here.

### `POST /query`

Request:

```json
{ "question": "Where can I find product 1?" }
```

Response:

```json
{
  "answer": "The product with ID 1 is available at the following branches: North Branch (100 units in stock), South Branch (30 units in stock).",
  "tool_calls": []
}
```

The `tool_calls` field is empty by default. Tool traces are always written to the server logs; they are only included in the HTTP response when the `EXPOSE_TOOL_CALLS` environment variable is set to `true`. This satisfies the observability requirement without exposing internal data (supplier identifiers, contact emails, reliability scores) to the public client.

---

## 4. Architecture: Two-Stage Agent

The agent processes every question in two distinct stages, each with its own system prompt and its own call to the LLM.

### Stage 1 — Data retrieval (tool-calling)

Uses a deliberately **short** system prompt and passes the full tool list to Ollama. Its only job is to select and call the right tools, and to accumulate their results. The natural-language text it produces at this stage is discarded.

### Stage 2 — Answer formulation

Makes a second call to Ollama **without** any tools attached. It receives the original question plus the raw results collected in stage 1, and formulates the final answer. Because no tool-calling mechanism has to be preserved here, this stage can use a long, detailed system prompt containing the full scope rules and grounding rules.

### Why two stages

This split was not a stylistic choice — it was required to make the system work reliably with a local model.

During testing, we established that the tool-calling mechanism degrades as the system prompt grows. Each section of the prompt worked correctly in isolation, but combining two or more of them caused the model to stop emitting structured tool calls. Instead it would either imitate the tool-call format as plain text, or narrate what it intended to do without acting on it. In the worst observed case, the model produced a complete, confident and entirely fabricated product description.

Splitting the work resolves the conflict: the fragile mechanism (structured tool calling) gets a minimal prompt, and the robust one (text generation) gets the detailed rules. No requirement had to be dropped.

An additional finding: numbered lists with arrows (`1. ... → use get_product`) were especially disruptive to tool calling, apparently being interpreted as an output template to reproduce rather than as internal routing instructions. Continuous prose proved significantly more reliable in the tool-calling prompt.

---

## 5. Grounding Strategy

Grounded answers are enforced at three levels:

1. **Data access is tool-only.** The service holds no product or stock knowledge of its own; every fact in an answer must come from a tool result passed into the agent context.
2. **Explicit prompt rules.** The answer-stage prompt forbids inventing product names, prices, stock quantities or branches, and requires stating clearly when information is unavailable.
3. **Deterministic computation where it matters.** Shopping list feasibility is computed in Python by `check_shopping_list`, not reasoned about by the model. The tool returns a ready-made verdict (`feasible_branches` plus per-branch `issues`) that the model only has to rephrase.

Point 3 proved necessary in practice. When a feasibility question was answered from raw stock data instead of the dedicated tool, the model produced a partially incorrect answer: it stated that no other branch held the product, while the data it had been given explicitly listed a second branch with 30 units in stock. Routing these questions to `check_shopping_list` removed that class of error.

---

## 6. Manual Test Evidence

All tests were run against the live service (`uvicorn main:app --port 8000`) with the `qwen3:latest` model served by a local Ollama instance. Tool traces are taken from the server logs.

### Test 1: Out-of-scope question

- **Objective**: Verify that questions outside the supported scope are declined clearly, without any attempt to answer.
- **Input**: *"What is the weather in Paris?"*
- **Tools called**: none
- **Response**:

```json
{
  "answer": "This type of request is not supported by this assistant. Additionally, no data was retrieved to provide information about the weather in Paris.",
  "tool_calls": []
}
```

- **Result**: Explicit refusal, no tool call, no fabricated answer.

### Test 2: Product details

- **Objective**: Verify that product details are retrieved from the catalog and reported without fabrication.
- **Input**: *"Give me the details of the product with ID 1"*
- **Tool called**: `get_product({"product_id": "1"})`
- **Response** (abridged):

> Here are the details for the product with ID 1: ID 1, SKU HB-LAP-1001, Name Holberton Student Laptop 14, Description "Training catalog item for HBntory integration: holberton student laptop 14.", Category Laptops, Brand Holberton, Supplier Holberton Tools Co. (SUP-HBT-001), Unit Price 799.00 USD, Discontinued No, Weight 1.35 kg, Tags student / portable / linux-ready.

- **Result**: Every field in the answer matches the tool output exactly. No fabricated fields.

### Test 3: Where a product is available

- **Objective**: Verify that stock across branches is retrieved from the inventory database.
- **Input**: *"Where can I find product 1?"*
- **Tool called**: `get_stock_by_product({"product_id": 1})`
- **Tool result**:

```json
{"product_id":1,"stock":[{"branch_id":1,"branch_name":"North Branch","quantity":100},{"branch_id":2,"branch_name":"South Branch","quantity":30}]}
```

- **Response**:

> The product with ID 1 is available at the following branches: North Branch — 100 units in stock; South Branch — 30 units in stock.

- **Result**: Both branches and both quantities reported correctly.

### Test 4: Products available in a branch

- **Objective**: Verify that a branch referenced by name is resolved to its ID, and that product identifiers are enriched with catalog names.
- **Input**: *"Which products are available at North Branch?"*
- **Tools called**: `list_branches`, `get_stock_by_branch`, `list_products`
- **Response**:

> The products available at North Branch are: Holberton Student Laptop 14 (SKU: HB-LAP-1001) — Category Laptops, Price $799.00 USD, Stock Quantity 100 units. No other products are listed as available at North Branch based on the provided data.

- **Result**: The agent resolved the branch name to its ID, retrieved the branch stock, and cross-referenced the returned product IDs against the catalog to display names instead of raw identifiers.

This confirms the design decision made on the MCP server side: `get_stock_by_branch` deliberately returns product IDs only, and the agent performs the name lookup itself by combining it with `list_products`.

### Test 5: Shopping list feasibility — satisfiable

- **Objective**: Verify that multi-product feasibility is delegated to the dedicated tool and reported faithfully.
- **Input**: *"Can I buy 5 units of product 1 and 2 units of product 2 in a single branch?"*
- **Tool called**: `check_shopping_list({"items": [{"product_id": 1, "quantity": 5}, {"product_id": 2, "quantity": 2}]})`
- **Tool result**:

```json
{"feasible_branches":["South Branch"],"details":{"North Branch":{"ok":false,"issues":["Product 2 is not available at branch 1."]},"South Branch":{"ok":true,"issues":[]}}}
```

- **Response**:

> Yes, you can purchase 5 units of Product 1 and 2 units of Product 2 in a single branch. South Branch is the only feasible option, as it has both products available in the required quantities. North Branch cannot fulfill the request because Product 2 is not available there.

- **Result**: The verdict and the explanation both match the tool output exactly.

### Test 6: Shopping list feasibility — not satisfiable

- **Objective**: Verify that a negative verdict is reported accurately, without rounding in the user's favour.
- **Input**: *"Can I buy 9999 units of product 1 in a single branch?"*
- **Tool called**: `check_shopping_list({"items": [{"product_id": 1, "quantity": 9999}]})`
- **Tool result**:

```json
{"feasible_branches":[],"details":{"North Branch":{"ok":false,"issues":["Product 1 has only 100 in stock at branch 1, but 9999 were requested."]},"South Branch":{"ok":false,"issues":["Product 1 has only 30 in stock at branch 2, but 9999 were requested."]}}}
```

- **Response**:

> The request to purchase 9999 units of product 1 cannot be fulfilled in a single branch. Neither the North Branch (only 100 units available) nor the South Branch (only 30 units available) has sufficient stock to meet the requested quantity.

- **Result**: Negative verdict reported correctly, with both branch stock levels stated accurately.

---

## 7. Configuration

All configuration is environment-driven, with development-friendly defaults.

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_MODEL` | `qwen3:latest` | Local model used for both agent stages |
| `OLLAMA_TIMEOUT_SECONDS` | `60` | Per-request timeout for Ollama calls |
| `MCP_SERVER_COMMAND` | `python` | Command used to launch the MCP server subprocess |
| `MCP_SERVER_ARGS` | `../product_mcp_server/server.py` | Arguments for that command |
| `MAX_TOOL_CALL_ROUNDS` | `5` | Safety limit on the tool-calling loop |
| `HBN_AI_PORT` | `8000` | Port the service listens on |
| `EXPOSE_TOOL_CALLS` | `false` | Whether to include tool traces in HTTP responses |

### Running locally

```bash
cd ai_service
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Requires a running Ollama instance with the configured model pulled, and a reachable external products API.

---

## 8. Known Limitations

**Model choice matters significantly.** Early testing with `mistral` produced fabricated product data — a non-existent "Apple iPhone 12" presented confidently as product ID 1 — along with inconsistent tool calling. `qwen3:latest` proved substantially more reliable and is the configured default. This is a property of the local model, not of the service architecture.

**Prompt length constrains the tool-calling stage.** As described in section 4, the stage-1 prompt must stay short. Any new routing rule added there should be re-tested against all four question types to confirm that structured tool calling is still emitted.

**Tool routing on single-product feasibility questions required an explicit rule.** Without an explicit instruction in the stage-1 prompt, single-product feasibility questions were answered from raw stock data rather than through `check_shopping_list`. A short routing rule was added to the prompt and verified against all six test cases.

**MCP transport is stdio-based.** The MCP client launches the Product MCP Server as a local subprocess. This works when both run on the same host, but will need to be revisited when the two services are deployed as separate Docker containers, since a container cannot spawn a subprocess living in another container.

**Latency.** Each question triggers at least two LLM calls (one or more tool-calling rounds, plus the answer-formulation call). With an 8B model running locally on CPU, response times of several seconds are expected.

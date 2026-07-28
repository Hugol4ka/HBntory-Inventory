# AI Query Service — Documentation

This document describes the AI Query Service of the `HBntory-Inventory` project: the question types it supports, its client-facing communication protocol, its internal architecture, its stock-access strategy, and evidence of manual test execution.

---

## 1. Overview

The AI Query Service is an independent backend service that receives natural-language questions from the Client Web Interface, retrieves real data through the Product MCP Server, and returns grounded answers.

It never accesses the products API or the inventory database directly: every piece of data it uses comes from a tool exposed by the Product MCP Server.

```
Client Web Interface  (port 5005)
        │  POST /query { "question": "..." }
        ▼
   AI Query Service  (port 5004) ──────► Ollama (local LLM, host machine)
        │
        ▼  MCP over streamable-http
  Product MCP Server  (port 5003) ──────► External Products API (port 5001)
                                  └─────► PostgreSQL (port 5432)
```

### Components

| File | Responsibility |
|---|---|
| `main.py` | FastAPI application, `POST /query` endpoint, service lifecycle |
| `agent.py` | Two-stage agent: tool-calling stage, then answer-formulation stage |
| `mcp_client.py` | MCP client: connects to the Product MCP Server, discovers and calls tools |
| `config.py` | Environment-driven configuration (model, hosts, ports, limits) |

---

## 2. Supported Question Types

The service answers four categories of questions. Any question outside this scope receives an explicit, polite refusal rather than an attempted answer.

| # | Question type | Example | Tools used |
|---|---|---|---|
| 1 | Product details | *"Give me the details of the product with ID 1"* | `get_product` |
| 2 | Where a product is available | *"Where can I find product 1?"* | `get_product`, then `get_stock_by_product` |
| 3 | What is available in a branch | *"Which products are available at North Branch?"* | `get_stock_by_branch` (optionally `list_branches` first) |
| 4 | Shopping list feasibility | *"Can I buy 5 units of HB-LAP-1001 and 2 units of HB-KBD-4102 in a single branch?"* | `check_shopping_list` |

Questions may be asked in French or in English. The tool-calling prompt instructs the model to answer in the language of the question.

### Out-of-scope handling

Two categories of requests are declined explicitly.

**Unrelated topics.** Anything that is not about products, stock or branches. When the tool-calling stage retrieves no data, the answer stage receives an empty result set and applies its scope rules.

Input: *"What is the weather in Paris?"*

> I am unable to provide information about the weather in Paris, as this type of request is not supported by this assistant.

**Whole-inventory requests.** Stock questions must target one specific product or one specific branch. A request for the complete inventory across all branches is refused, with an explanation of what the assistant *can* do.

Input: *"quel est la liste du stock ?"*

> La question demandant la liste complète du stock n'est pas supportée par ce système. Je peux vous fournir le stock pour un produit spécifique ou pour une branche spécifique. Veuillez préciser le produit ou la branche que vous souhaitez consulter.

This second rule was added after the agent was observed answering such a question with the full product catalog — which lists what *exists*, not what is *in stock*. A dedicated grounding rule now forbids presenting the catalog as stock information.

---

## 3. Client Communication Protocol: REST

**The AI Query Service uses REST (HTTP), not WebSockets.**

### Rationale

- **No conversation history is required.** Each request is fully independent and stateless, so the persistent connection that WebSockets provide brings no benefit.
- **Simplicity of integration.** A single `POST` request is trivial to call from the Client Web Interface, from `curl`, or from automated tests.
- **Operational simplicity.** REST works out of the box behind standard Docker port mappings, with no additional protocol handling.

WebSockets would become the better choice if the service later needed to stream partial answers token by token, or to maintain a multi-turn conversation — neither of which is a requirement here.

### `POST /query`

Request:

```json
{ "question": "Where can I find product 1?" }
```

Response:

```json
{
  "answer": "Product Holberton Student Laptop 14 (SKU: HB-LAP-1001) is available in the following branches: North Branch — 100 units, South Branch — 30 units.",
  "tool_calls": []
}
```

The `tool_calls` field is empty by default. Tool traces are always written to the server logs; they are only included in the HTTP response when the `EXPOSE_TOOL_CALLS` environment variable is set to `true`. This satisfies the observability requirement of task 2 without exposing internal data (supplier identifiers, contact emails, reliability scores) to the public client.

---

## 4. Architecture: Two-Stage Agent

The agent processes every question in two distinct stages, each with its own system prompt and its own call to the LLM. The two calls are fully independent: the model retains nothing between them, so shared context — including the assistant's identity — must be restated in both prompts.

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

## 5. Stock Access Strategy

Stock information is accessed **by extending the Product MCP Server with dedicated stock-query tools**, rather than through a third-party database MCP or a separate internal API.

### Rationale

- **Single boundary.** The AI Query Service already speaks MCP to reach product data; routing stock through the same server keeps exactly one integration point instead of two.
- **No raw SQL exposure.** A generic database MCP tool would let the agent issue arbitrary queries. Our tools expose four narrow, purpose-built read operations instead — the agent cannot reach the `users` table or write anything.
- **Deterministic computation.** `check_shopping_list` performs the feasibility calculation in Python and returns a ready-made verdict, rather than handing raw rows to the model and hoping it reasons correctly over them.

### Tools by data source

| Tool | Source | Purpose |
|---|---|---|
| `list_products` | External Products API | Full catalog |
| `get_product` | External Products API | Details for one product, by numeric ID or SKU |
| `list_branches` | PostgreSQL | All branches (id + name) |
| `get_stock_by_product` | PostgreSQL | Stock of one SKU across all branches |
| `get_stock_by_branch` | PostgreSQL + Products API | All products stocked in one branch, enriched with catalog names |
| `check_shopping_list` | PostgreSQL | Which branches can satisfy a full shopping list |

`get_stock_by_branch` is the one tool that combines both sources. The design initially kept it database-only, expecting the agent to cross-reference SKUs against `list_products` itself. That expectation proved unreliable: the agent frequently skipped the second call and displayed raw SKUs. Performing the join server-side made the behaviour deterministic, at the cost of one extra HTTP request inside the tool. If the catalog is unreachable, quantities are still returned with the product name marked as unavailable.

---

## 6. Grounding Strategy

Grounded answers are enforced at three levels:

1. **Data access is tool-only.** The service holds no product or stock knowledge of its own; every fact in an answer must come from a tool result passed into the agent context.
2. **Explicit prompt rules.** The answer-stage prompt forbids inventing product names, prices, stock quantities or branches, and requires stating clearly when information is unavailable.
3. **Deterministic computation where it matters.** Shopping list feasibility is computed in Python by `check_shopping_list`, not reasoned about by the model.

Point 3 proved necessary in practice. When a feasibility question was answered from raw stock data instead of the dedicated tool, the model produced a partially incorrect answer: it stated that no other branch held the product, while the data it had been given explicitly listed a second branch with 30 units in stock.

### Unknown identifiers

The stock tools distinguish three situations that would otherwise produce the same message:

- the SKU exists but is not stocked in this branch,
- the SKU is stocked here but in insufficient quantity,
- **the SKU does not exist anywhere in the inventory.**

The third case was added after the model mistyped a SKU when building tool arguments (`HB-KBD-41002` instead of `HB-KBD-4102`). The tool correctly reported that this product was unavailable everywhere, and the agent faithfully relayed that verdict — producing a factually wrong answer from correctly grounded data. The tool now returns an explicit *unknown SKU* message, and a grounding rule instructs the agent to report a non-existent product reference rather than an out-of-stock condition.

### Grounding under failure

During an interval when the `stock` table did not yet exist in PostgreSQL, the agent received a raw SQL error from the tool and answered: *"the requested information about its availability could not be retrieved"* — rather than inventing branches or quantities.

---

## 7. Manual Test Evidence

All tests were run against the live Docker deployment (`docker compose up`), with the `qwen3:latest` model served by a local Ollama instance. Tool traces are taken from the service logs.

Reference data in the inventory database:

| SKU | Branch | Quantity |
|---|---|---|
| HB-LAP-1001 | North Branch | 100 |
| HB-SSD-7101 | North Branch | 20 |
| HB-LAP-1001 | South Branch | 30 |
| HB-KBD-4102 | South Branch | 50 |

### Test 1: Out-of-scope question

- **Objective**: Verify that unrelated questions are declined clearly, without any attempt to answer.
- **Input**: *"What is the weather in Paris?"*
- **Tools called**: none
- **Response**:

> I am unable to provide information about the weather in Paris, as this type of request is not supported by this assistant.

- **Result**: Explicit refusal, no tool call, no fabricated answer.

### Test 2: Whole-inventory request

- **Objective**: Verify that stock questions without a specific target are declined, and that the catalog is not presented as stock.
- **Input**: *"quel est la liste du stock ?"*
- **Tools called**: `list_branches`
- **Response**:

> La question demandant la liste complète du stock n'est pas supportée par ce système. Je peux vous fournir le stock pour un produit spécifique ou pour une branche spécifique.

- **Result**: Refused with a useful alternative, in the language of the question.

### Test 3: Product details

- **Objective**: Verify that product details are retrieved from the catalog and reported without fabrication.
- **Input**: *"Give me the details of the product with ID 1"*
- **Tool called**: `get_product({"product_id": "1"})`
- **Response** (abridged):

> Name: Holberton Student Laptop 14 — SKU: HB-LAP-1001 — Category: Laptops — Brand: Holberton — Supplier: Holberton Tools Co. — Unit Price: $799.00 USD — Weight: 1.35 kg — Tags: student, portable, linux-ready.

- **Result**: Every field matches the tool output exactly. No fabricated fields.

### Test 4: Where a product is available

- **Objective**: Verify the numeric ID → SKU conversion followed by a stock lookup.
- **Input**: *"Where can I find product 1?"*
- **Tools called**: `get_product({"product_id": "1"})`, then `get_stock_by_product({"sku": "HB-LAP-1001"})`
- **Tool result**:

```json
{"sku":"HB-LAP-1001","stock":[{"branch_id":1,"branch_name":"North Branch","quantity":100},{"branch_id":2,"branch_name":"South Branch","quantity":30}]}
```

- **Response**:

> Product Holberton Student Laptop 14 (SKU: HB-LAP-1001) is available in the following branches: North Branch — 100 units, South Branch — 30 units.

- **Result**: Two-step chain executed correctly; both branches and quantities accurate.

### Test 5: Same question in French

- **Objective**: Verify that the ID → SKU chain also holds for a French phrasing that does not use the word "where".
- **Input**: *"quelle est la quantité du produit 1 en stock ?"*
- **Tools called**: `get_product`, then `get_stock_by_product`
- **Result**: Both tools called, correct quantities reported in French.

An earlier version of the tool-calling prompt failed this test: the agent called `get_product`, stopped there, and then correctly reported that stock information was absent from the data it held. The answer stayed grounded but the question went unanswered. The prompt now states explicitly that `get_product` alone never answers a stock question.

### Test 6: Products available in a branch

- **Objective**: Verify that stock is returned with catalog product names rather than raw SKUs.
- **Input**: *"Which products are available at North Branch?"*
- **Tool called**: `get_stock_by_branch({"branch_id": 1})`
- **Tool result**:

```json
{"branch_id":1,"branch_name":"North Branch","quantity_by_product":[{"sku":"HB-LAP-1001","quantity":100,"name":"Holberton Student Laptop 14"},{"sku":"HB-SSD-7101","quantity":20,"name":"External SSD 1TB"}]}
```

- **Response**:

> The products available at North Branch are: Holberton Student Laptop 14 (SKU: HB-LAP-1001) — 100 units; External SSD 1TB (SKU: HB-SSD-7101) — 20 units.

- **Result**: Names correctly resolved by the tool itself, in a single call.

### Test 7: Second branch, in French

- **Objective**: Verify that the correct branch is targeted when the answer for another branch would differ.
- **Input**: *"quels produits sont disponibles à South Branch ?"*
- **Tool called**: `get_stock_by_branch({"branch_id": 2})`
- **Response**:

> À South Branch, les produits disponibles sont : Compact Keyboard ES (SKU : HB-KBD-4102) — 50 unités ; Holberton Student Laptop 14 (SKU : HB-LAP-1001) — 30 unités.

- **Result**: Correct branch resolved, correct products and quantities, answer in French.

### Test 8: Shopping list feasibility — satisfiable

- **Objective**: Verify that multi-product feasibility is delegated to the dedicated tool and reported faithfully.
- **Input**: *"Can I buy 5 units of HB-LAP-1001 and 2 units of HB-KBD-4102 in a single branch?"*
- **Tool called**: `check_shopping_list({"items": [{"sku": "HB-LAP-1001", "quantity": 5}, {"sku": "HB-KBD-4102", "quantity": 2}]})`
- **Tool result**:

```json
{"feasible_branches":["South Branch"],"details":{"North Branch":{"ok":false,"issues":["Product HB-KBD-4102 is not available at branch 1."]},"South Branch":{"ok":true,"issues":[]}}}
```

- **Response**:

> Yes, you can buy 5 units of HB-LAP-1001 and 2 units of HB-KBD-4102 in a single branch. The South Branch is the only branch where this combination is available. The North Branch does not have HB-KBD-4102 in stock.

- **Result**: Verdict and explanation both match the tool output exactly.

### Test 9: Shopping list feasibility — not satisfiable

- **Objective**: Verify that a negative verdict is reported accurately, without rounding in the user's favour.
- **Input**: *"Can I buy 9999 units of HB-LAP-1001 in a single branch?"*
- **Tool called**: `get_stock_by_product({"sku": "HB-LAP-1001"})`
- **Response**:

> The product HB-LAP-1001 is available in two branches: North Branch — 100 units, South Branch — 30 units. You cannot buy 9999 units in a single branch, as the maximum available in any one branch is 100 units.

- **Result**: Correct answer, but reached by the model reasoning over raw stock data rather than through `check_shopping_list`. See section 10 for the reliability implication.

### Test 10: Unknown SKU

- **Objective**: Verify that a non-existent product reference is reported as such, not as an out-of-stock condition.
- **Input**: *"Can I buy 2 units of HB-KBD-99999 in a single branch?"*
- **Tool called**: `get_stock_by_product({"sku": "HB-KBD-99999"})` returning an empty stock list
- **Response**:

> The product reference "HB-KBD-99999" does not exist in the inventory. Please check the SKU and try again.

- **Result**: Correct distinction between an unknown reference and an unavailable product.

### Test 11: End-to-end through the Client Web Interface

- **Objective**: Verify the full chain from browser to database.
- **Procedure**: Question submitted from the chat interface on `http://localhost:5005`.
- **Result**: The web client reaches the AI service, which reaches the MCP server, which reaches both PostgreSQL and the external Products API. The answer is rendered in the browser.

---

## 8. Performance

Response times were measured with `time curl` against the running service.

| Question type | Ollama calls | Measured time |
|---|---|---|
| Out of scope (no tool) | 2 | ~4 s |
| Product details | 3 | ~7 s |
| Stock lookup (ID → SKU → stock) | 4 | ~10 s |

Per-call breakdown for a stock question, from the service logs:

```
[tool round 0] prompt_eval=596 eval=21 duration_ms=2774
[tool round 1] prompt_eval=818 eval=29 duration_ms=1664
[tool round 2] prompt_eval=906 eval=49 duration_ms=2314
[answer]       prompt_eval=596 eval=54 duration_ms=3317
```

### The `think` parameter

An early version of the service took **2 minutes 35 seconds** for a stock question, which caused the Client Web Interface to time out and display *"AI Service unavailable"*. The logs showed the AI service still calling Ollama after the client had already given up.

The cause was qwen3's reasoning mode: the model generates an internal reasoning block before each response, invisible in the output but fully billed in compute time, and this cost multiplied across every call in the chain.

Passing `"think": false` in both Ollama requests reduced the same question to **10 seconds** — a factor of 15. Both calls must carry the parameter; omitting it on the answer-formulation call alone kept response times above two minutes.

Client implementations should still allow a timeout of at least 60 seconds and display a loading indicator.

---

## 9. Configuration

All configuration is environment-driven, with development-friendly defaults.

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API base URL (`http://host.docker.internal:11434` in Docker) |
| `OLLAMA_MODEL` | `qwen3:latest` | Local model used for both agent stages |
| `OLLAMA_TIMEOUT_SECONDS` | `180` | Per-request timeout for Ollama calls |
| `MCP_SERVER_URL` | `http://localhost:5003/mcp` | Product MCP Server endpoint (`HBN_AI_MCP_URL` in Docker) |
| `MAX_TOOL_CALL_ROUNDS` | `5` | Safety limit on the tool-calling loop |
| `HBN_AI_PORT` | `8000` | Port the service listens on (`5000` inside the container) |
| `EXPOSE_TOOL_CALLS` | `false` | Whether to include tool traces in HTTP responses |

### Running with Docker

```bash
docker compose up -d
```

Requires a running Ollama instance on the host with the configured model pulled. On first run, the database must be initialised:

```bash
docker compose run --rm -e ADMIN_PASSWORD=<password> backoffice python init_db.py
```

### Running locally

The MCP server must be started separately, since the client connects over HTTP rather than spawning a subprocess:

```bash
# Terminal 1
cd product_mcp_server && python server.py

# Terminal 2
cd ai_service && pip install -r requirements.txt && uvicorn main:app --reload --port 8000
```

### MCP transport

The client connects to the Product MCP Server over **streamable-http**, the transport recommended by the current MCP specification. An earlier version used stdio, with the AI service spawning the MCP server as a local subprocess — which cannot work once the two services run in separate containers, since a container cannot spawn a process living in another one.

Two resilience mechanisms protect this connection:

- **Startup retry.** `depends_on` guarantees that the MCP server container has started, not that it accepts connections. The client retries the initial connection up to ten times at two-second intervals.
- **Session recovery.** If the MCP server restarts, the negotiated session id becomes invalid and every tool call fails with `Session terminated`. `call_tool` catches this, reconnects, and retries once.

---

## 10. Known Limitations

**Model choice matters significantly.** Early testing with `mistral` produced fabricated product data — a non-existent "Apple iPhone 12" presented confidently as product ID 1 — along with inconsistent tool calling. `qwen3:latest` proved substantially more reliable and is the configured default. This is a property of the local model, not of the service architecture.

**Prompt length constrains the tool-calling stage.** As described in section 4, the stage-1 prompt must stay short, and every routing rule added to it competes with the others. Test 9 illustrates the trade-off: an explicit rule routing feasibility questions to `check_shopping_list` worked when first added, then stopped applying to single-product questions after further rules were appended. The answers remain correct in practice, but they are produced by the model reasoning over raw numbers rather than by deterministic computation — the same path that produced a factually wrong answer earlier in testing. Any new rule should be re-tested against all four question types.

**The model can mistype identifiers.** SKUs are copied by the model into tool arguments and are occasionally corrupted (`HB-KBD-41002` for `HB-KBD-4102`). The tools now detect unknown SKUs and say so explicitly, which turns a wrong answer into an honest one, but cannot recover the intended value.

**Stock is keyed by SKU, product questions by numeric ID.** The `stock` table identifies products by SKU, while users typically refer to products by numeric ID. Every stock question therefore requires two chained calls where one would otherwise suffice.

**`models.py` is duplicated.** The SQLAlchemy models are copied between `backoffice/` and `product_mcp_server/`, because each service builds its Docker image from its own directory and cannot reach a shared folder. The two copies must be kept in sync manually. This has already caused one incident: a change from `Integer` to `String(50)` on `Stock.id_product` was applied in one copy only, and every stock query failed with a type mismatch until the other was updated.

**Referential integrity is not enforced across systems.** `Stock.id_product` has no foreign key, since the product catalog lives in the external API rather than in the local database. The correspondence between a SKU in the local `stock` table and a product in the external catalog is maintained by convention only.

**Supplier details reach the public answer.** `get_product` returns supplier contact emails, lead times and reliability scores, and the agent includes them when listing product details. These are arguably internal data that a public client should not see. Filtering them would require either trimming the tool output or an additional prompt rule.

# HBntory

**Multi-branch inventory management platform with a natural-language AI interface.**

HBntory manages stock across the physical branches of a distribution company. Internal staff operate through an authenticated Backoffice, while the general public can query product and stock availability in plain language — no account required.

The product catalogue is owned by an external API. HBntory never copies it: the local database stores references only.

---

## Table of contents

- [Team](#team)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running the system](#running-the-system)
- [Database initialisation](#database-initialisation)
- [Using the Backoffice](#using-the-backoffice)
- [Using the public interface](#using-the-public-interface)
- [Key technical decisions](#key-technical-decisions)
- [Documentation](#documentation)
- [Known limitations](#known-limitations)
- [Optional features implemented](#optional-features-implemented)

---

## Team

| Member | Scope |
|---|---|
| **Pierre** | Database design, Backoffice (authentication, authorisation, stock, user management, Product API integration, SSR interface), public web client, containerisation |
| **Hugo** | Products MCP server, AI Query Service (agent, tool calling, Ollama integration), initial Docker Compose setup |

Architecture, technical decisions and final integration were carried out jointly.

---

## Architecture

The system is composed of six containerised services on a single Docker network.

```
        ┌─────────────┐   HTTP/REST   ┌──────────────────┐
        │ BACKOFFICE  │ ────────────► │  PRODUCTS API    │
 Staff  │   :5002     │               │  :5001 (given)   │
   ────►│    SSR      │               └──────────────────┘
        └──────┬──────┘                        ▲
               │ SQLAlchemy                    │ HTTP
               ▼  (read + write)               │
        ┌─────────────┐                ┌───────┴──────┐
        │ PostgreSQL  │ ◄──────────────│  MCP SERVER  │
        │   :5432     │   SQLAlchemy   │    :5003     │
        └─────────────┘   (read only)  └──────▲───────┘
                                              │ MCP streamable-http
        ┌─────────────┐   REST         ┌──────┴───────┐    ┌──────────┐
 Public │ WEB CLIENT  │ ────────────►  │  AI SERVICE  │───►│  Ollama  │
   ────►│   :5005     │  POST /ask     │    :5004     │HTTP│  qwen3   │
        └─────────────┘                └──────────────┘    └──────────┘
                                                             host machine
```

| Service | Responsibility | External port |
|---|---|---|
| `backoffice` | Authenticated internal application (Flask, server-side rendering) | 5002 |
| `db` | PostgreSQL — users, branches, stock quantities | 5432 |
| `external-products-api` | Product catalogue, read-only (provided by the school) | 5001 |
| `mcpserver` | MCP bridge exposing product and stock tools to the agent | 5003 |
| `aiservice` | AI Query Service (FastAPI + Ollama) | 5004 |
| `webclient` | Public question interface | 5005 |

**Two independent flows**

- **Staff** — browser → Backoffice → database *(read/write)* + Products API *(names)*
- **Public** — browser → Web Client → AI Service → MCP server → database *(read only)* + Products API

**Boundaries enforced by design**

- The Backoffice and the AI Service never communicate. Their only shared resource is the database.
- The MCP server holds read-only access. Every write goes through the authenticated Backoffice.
- The browser never contacts the AI Service directly; the Web Client relays requests.

All services listen on port `5000` internally and are reachable by service name on the Docker network (`http://mcpserver:5000`, `postgresql://db:5432`).

---

## Requirements

- **Docker** and **Docker Compose** (Docker Desktop on macOS/Windows)
- **Ollama** running on the host machine, with the `qwen3` model pulled
- Roughly 8 GB of free RAM — the language model runs locally

Ollama is not containerised. See [Known limitations](#known-limitations).

---

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/Hugol4ka/HBntory-Inventory.git
cd HBntory-Inventory
```

**2. Create the environment file**

Copy the template and fill in your own values:

```bash
cp .env.example .env
```

`.env` must define:

```
ADMIN_PASSWORD=<a strong password of your choice>
SECRET_KEY_FLASK=<a long random string>
```

`ADMIN_PASSWORD` is the password of the `admin` account created at initialisation. `SECRET_KEY_FLASK` signs the session cookie. Neither value is versioned — `.env` is excluded by `.gitignore`.

**3. Start Ollama and pull the model**

```bash
ollama serve          # leave running in a dedicated terminal
ollama pull qwen3     # first run only, several gigabytes
```

---

## Running the system

From the repository root:

```bash
docker compose up --build
```

Add `-d` to run detached. First build takes a few minutes; subsequent starts are near-instant.

**Check that everything is up**

```bash
docker compose ps
```

Six containers should be listed. If one is missing, inspect its logs:

```bash
docker compose logs <service>
```

**Stop the system**

```bash
docker compose down       # stops containers, keeps data
docker compose down -v    # also deletes the database volume
```
### Running services individually

Any service can be started on its own — Compose will pull in its declared
dependencies automatically:

```bash
docker compose up -d db                       # database only
docker compose up -d external-products-api    # products catalogue only
docker compose up -d backoffice               # backoffice (starts db too)
docker compose up -d mcpserver                # MCP server
docker compose up -d aiservice                # AI service (starts mcpserver too)
docker compose up -d webclient                # public interface
```

Useful for testing one component in isolation, or for restarting a single
service after a change:

```bash
docker compose up -d --build backoffice       # rebuild and restart one service
docker compose restart aiservice              # restart without rebuilding
docker compose logs -f aiservice              # follow one service's logs
```

Note that the AI service requires Ollama to be running on the host, and the
MCP server requires the database.

### Service endpoints

| Service | URL |
|---|---|
| Backoffice | http://localhost:5002 |
| Public interface | http://localhost:5005 |
| Products API health check | http://localhost:5001/health |
| AI Service | http://localhost:5004/query *(POST)* |
| MCP server | http://localhost:5003/mcp |
| PostgreSQL | `localhost:5432` |

---

## Database initialisation

**No manual step is required.** The Backoffice container runs `init_db.py` at startup, which creates the tables if absent and seeds the system with:

- the `admin` account, with the password taken from `.env`
- two branches — *North Branch* and *South Branch*
- four stock rows using real SKUs from the external catalogue

The script is **idempotent**: it checks for existing records before creating anything, so restarting a container never duplicates or fails on existing data.

To run it manually — after a `down -v`, for instance:

```bash
docker compose run --rm backoffice python init_db.py
```

To inspect the database directly:

```bash
docker exec -it hbntory-db psql -U devuser -d inventory -c "SELECT username, role FROM users;"
```

---

## Using the Backoffice

Open **http://localhost:5002** and sign in.

### Administrator

Sign in as `admin` with the password from your `.env`. You will land on the user management page.

The administrator can:

- list all users, with their branch and status
- create common users and assign them to a branch
- change a user's password
- change a user's assigned branch
- soft-delete a user

The administrator has **no access to stock operations** — requesting `/stock` returns `403`.

### Common user

Sign in with an account created by the administrator. You will land on the stock page for your assigned branch, which is displayed on screen.

A common user can:

- list the products currently in stock in their branch, with names retrieved from the external API
- add stock
- remove stock

A common user has **no access to user management** — requesting `/users` returns `403`. They cannot operate on any branch other than their own: the branch is derived from the session on the server side and never accepted from the client.

### Validation

- Quantities must be positive integers
- Stock can never go negative
- Product identifiers are verified against the external catalogue before any insertion

---

## Using the public interface

Open **http://localhost:5005**. No account is needed.

Type a question and submit. Responses typically take a few seconds — the language model runs locally on the host machine.

### Example questions

**Product details**
```
Give me the details of product HB-SSD-7101.
```

**Where a product is available**
```
Which branch has stock of product HB-LAP-1001?
```

**What a branch holds**
```
Which products can I find at North Branch?
```

**Shopping list feasibility**
```
If I want to buy 3 HB-LAP-1001 and 2 HB-SSD-7101, which branch should I visit?
```

**Unknown product** — the agent states the information is unavailable rather than inventing an answer
```
Give me the details of product HB-ZZZ-9999.
```

**Out of scope** — the agent declines
```
What is the weather in Paris?
```

The agent answers strictly from tool results. It has no knowledge of its own about the catalogue or stock levels, and reports missing information explicitly.

---

## Key technical decisions

Each decision is documented in full under [`docs/`](#documentation). Summary:

**No product data stored locally.** The external API is the single source of truth. A local copy would silently drift out of date. The `stock` table holds a product reference and a quantity — nothing else.

**Server-side rendering for the Backoffice.** One component to build and run, rather than a separate frontend to keep in sync with an API. Adequate for management forms.
*Trade-off:* less interactive than a single-page application.

**Session-based authentication.** With server-side rendering the browser returns the session cookie automatically. A token would require JavaScript to store it and attach it to every request, for no benefit.
*Trade-off:* browser-bound; unsuitable as-is for a mobile client.

**REST rather than WebSocket for the public client.** Every question is independent and no history is kept. A persistent connection would add complexity without value.
*Trade-off:* no streamed responses.

**A single MCP server extended to stock queries**, rather than a third-party database MCP tool. One data boundary to maintain, a deliberately narrow surface — our tools expose precise read operations where a generic database MCP would allow arbitrary queries, including against the users table — and the ability to compute in Python rather than have the model reason over raw rows.

**A local model via Ollama** rather than a cloud API. No cost, no API key, no data sent to a third party.
*Trade-off:* lower tool-calling reliability and slower responses than a hosted model. Several architectural choices in the AI service follow directly from this constraint.

**Validation at two levels.** Database constraints (`CHECK quantity >= 0`, foreign keys, composite uniqueness) guarantee integrity regardless of application bugs. Python validation produces messages users can act on, and covers rules SQL cannot reach — such as verifying a product exists in a remote API.

**Authorisation scope always comes from the server.** The branch a stock operation applies to is read from the database using the session's user ID, never from a URL or form field. Product identifiers and quantities do come from the client: falsifying them grants access to nothing forbidden.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/database_schema.md`](docs/database_schema.md) | Schema, design rationale, validation rules |
| [`docs/authentication_authorization.md`](docs/authentication_authorization.md) | Authentication strategy, password hashing, role-based access control |
| [`docs/McpServer_doc.md`](docs/McpServer_doc.md) | MCP tools, contracts, error handling |
| [`docs/AI_Query_Service_doc.md`](docs/AI_Query_Service_doc.md) | Agent architecture, grounding strategy, supported question types |

---

## Known limitations

**Ollama is not containerised.** It runs on the host machine, which means `docker compose up` alone is not self-sufficient. On macOS and Windows the AI service reaches it through `host.docker.internal`; on Linux this hostname is unavailable and the compose file requires adjustment. Containerising Ollama would add several gigabytes to the stack.

**Flask development server.** Both the Backoffice and the Web Client run with `debug=True` on Flask's built-in server. This is unsuitable for production: the debugger exposes an executable Python console in the browser on any unhandled exception. A production deployment would use a WSGI server such as gunicorn with debugging disabled.

**No CSRF protection.** Forms carry no anti-CSRF token. An authenticated administrator visiting a malicious page could have an action triggered on their behalf. The standard remedy is a per-form token, for instance via Flask-WTF.

**No rate limiting on login.** Neither attempt throttling nor account lockout is implemented, leaving brute-force attempts unconstrained.

**No SSL/TLS.** Explicitly out of scope for this project. In real conditions credentials and the session cookie would travel in clear text.

**Containers run as root.** No dedicated application user is defined in the Dockerfiles.

**Data models are duplicated.** `backoffice/models.py` and `product_mcp_server/models.py` describe the same tables in two places. Keeping them aligned is manual, and a divergence has already cost us debugging time. A shared package would be the correct fix.

**Local model performance.** qwen3 on modest hardware, alongside six containers, produces response times of several seconds and occasional tool-calling errors. A smaller model would suit demonstration better.

**Inconsistent column naming.** `stock.id_branch` and `users.branch_id` refer to the same concept with two conventions. Identified but not corrected: renaming would have touched both services simultaneously.

---

## Optional features implemented

- **Docker Compose for all services** — the entire system starts with a single command
- **Automatic database initialisation** — idempotent seeding at container startup, no manual step
- **Graceful degradation** — the Backoffice remains usable when the external Products API is unreachable: quantities are still displayed, only product names fall back to a placeholder

---

## Repository structure

```
HBntory-Inventory/
├── backoffice/              Authenticated internal application
│   ├── app.py               Flask routes
│   ├── models.py            SQLAlchemy models
│   ├── database.py          Engine and connection string
│   ├── decorators.py        Access control decorators
│   ├── stock_service.py     Stock business logic
│   ├── user_service.py      User business logic
│   ├── product_api.py       External Products API client
│   ├── init_db.py           Idempotent database seeding
│   ├── entrypoint.sh        Init then start
│   └── templates/           Jinja2 templates
├── product_mcp_server/      MCP server — product and stock tools
├── ai_service/              AI Query Service — agent and Ollama client
├── client_web/              Public question interface
├── docs/                    Technical documentation
├── docker-compose.yml
├── .env.example
└── README.md
```
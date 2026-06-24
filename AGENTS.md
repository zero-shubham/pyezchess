# AGENTS.md

> **CRITICAL DIRECTIVE:** Always ask the user for explicit confirmation before making changes to source files, modifying database schemas, or executing non-read-only tasks. Never make autonomous destructive decisions.

---

## 1. Project Overview

**pyezchess** — AI Chess Instructor (backend). Persona "Vishy" coaches students through 4 curriculum levels (Fundamentals, Tactics, Opening, Strategy) via WebSocket. Uses Stockfish for move analysis, LangGraph-orchestrated LLM for commentary.

**Stack:** Python 3.14, FastAPI, PostgreSQL 15, SQLAlchemy (async), LangChain/LangGraph, python-chess + Stockfish.

**Architecture:** Hybrid Feature-Slice + Unified Delivery Gates (see [`docs/llm/STRUCTURE.md`](docs/llm/STRUCTURE.md)).
- `src/core/` — feature-sliced domain verticals (game, agent, user, session)
- `src/shared/` — cross-cutting infrastructure (config, database, middleware, message protocol)
- `src/api/` — FastAPI delivery gate (REST + WebSocket)
- `src/cli/` — Typer CLI delivery gate
- `src/tests/` — pytest test suite

---

## 2. Environment & Dependencies

**Package manager:** [uv](https://docs.astral.sh/uv/) (lockfile: `uv.lock`)

```bash
uv sync              # Install all dependencies
```

**Prerequisites:**
- Python 3.14+
- Docker + Docker Compose (for PostgreSQL)
- Stockfish chess engine (path in `STOCKFISH_PATH` env var)

**Environment variables:** Defined in `app.env` (defaults) and `.env` (secrets — gitignored). Key vars: `DATABASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `STOCKFISH_PATH`, `SESSION_SECRET`.

**Run locally:**

```bash
make dev             # Docker Compose: app + PostgreSQL (full stack)
python src/main.py   # Run directly (requires PostgreSQL running separately)
```

---

## 3. Build, Test & Verification Commands

Always run from project root:

```bash
make lint            # Ruff linter check
make format          # Ruff auto-formatter
make typecheck       # Pyright strict mode
make test            # pytest -v (with asyncio auto mode)
```

**Pre-commit checklist:**
1. `make lint` — zero errors
2. `make typecheck` — 100% type safe
3. `make test` — all tests pass

**Docker helpers:**
```bash
make up / make down          # Start/stop services
make migrate-up / migrate-down # Run Alembic migrations
```

**CLI (inside Docker):**
```bash
docker compose run --rm app python -m cli.main admin add <user> <email> <pass>
```

---

## 4. Code Style Guidelines

- **Type hints mandatory** on all new/modified function signatures. Pyright `strict` mode.
- **`from __future__ import annotations`** at top of every `.py` file.
- **Ruff** for linting + formatting. No deviations from default rules.
- **Naming:** PascalCase classes, snake_case functions, `Err` prefix for error classes (`ErrUserNotFound`), `Interface` or `ABC` suffix for abstract types.
- **No generic `except Exception:`** without logging/re-raising.
- **Domain models** use `@dataclass` with `uuid4` defaults.
- **API schemas** use Pydantic models.
- **Enums** use `StrEnum`/`IntEnum`.
- **Repository + Service + Unit of Work** patterns throughout. New features must follow same layered architecture.
- **Precise edits only** — never rewrite entire files for single-line fixes. Preserve git blame.

---

## 5. Security Guidelines

- **Never commit secrets** — API keys, tokens, credentials, `.env` file.
- **Never hardcode credentials** in source. Use environment variables via `configs/config.py`.
- **No raw SQL** — always use SQLAlchemy parameterized queries.
- **Password hashing** uses bcrypt. Do not replace with weaker schemes.
- **Session tokens** use `secrets.token_urlsafe`. Do not downgrade entropy.
- **Session cookies** must remain `HttpOnly`, `SameSite=Lax`.
- **Never bypass auth middleware** or add unauthenticated routes without explicit approval.
- **Avoid LLM API key leaks** — keys flow through `config.py` only, never logged or exposed.

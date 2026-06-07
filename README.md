# ezchess

AI-powered chess learning app. Your personal coach, **Vishy**, walks you through a structured curriculum across 4 levels, scores every move, and gives real-time feedback over WebSocket.

> **Status:** Proof of Concept — basic features only, establishing the idea and validating the concept. Not production-ready.

## How it works

1. You pick a curriculum level (1–4) — Vishy picks the right topic for you.
2. Vishy sets up a practice game, introduces the current topic, and plays alongside you.
3. Every move you make is analyzed by Stockfish and scored by the LLM.
4. Vishy responds with a counter-move and 2–3 sentences of coaching commentary tied to the curriculum.
5. Progress is tracked per topic — scores accumulate, topics unlock as you improve.

## Curriculum

| Level | Name | Topics |
|-------|------|--------|
| 1 | **Fundamentals** | Board, pieces, castling, en passant, promotion, checkmate, stalemate, material values |
| 2 | **Tactics** | Mate patterns, forks, pins, skewers, defense (C.B.M.), board awareness |
| 3 | **Opening** | Center control, development, king safety, Scholar's Mate defense, Italian Game, tempo |
| 4 | **Strategy** | Pawn structure, bishop pair, rook coordination, active king, opposition, planning |

Vishy chooses the next topic based on your progress — you never navigate manually.

## Scoring

| Grade | Delta | Meaning |
|-------|-------|---------|
| STRONG | +3 | Excellent — engine-approved or clearly principled |
| GOOD | +1 | Solid — demonstrates curriculum understanding |
| WEAK | 0 | Needs work — Vishy leads with curiosity, not correction |
| Repeated mistake (same session) | -3 | Second occurrence of the same error type |

Scoring is beginner-lenient: moves that apply recently learned principles get graded up even if suboptimal by engine standards.

## Run the POC locally

Requires Docker. Supports **OpenAI**, **Anthropic (Claude)**, **Gemini**, and **DeepSeek** — at least one LLM API key needed.

```bash
docker network create ezchess

docker run -d --network ezchess --name db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=ezchess \
  postgres:15-alpine

docker run -d --network ezchess --name ezchess -p 3000:3000 \
  -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/ezchess \
  -e OPENAI_API_KEY=sk-... \
  zeroshubham/ezchess:latest
```

App is now at `http://localhost:3000`. A guest account is auto-created (`guest@ezchess.app` / `Password!`).

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `OPENAI_API_KEY` | No* | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4.1` | Override OpenAI model |
| `ANTHROPIC_API_KEY` | No* | — | Anthropic API key |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-20250514` | Override Claude model |
| `DEEPSEEK_API_KEY` | No* | — | DeepSeek API key |
| `DEEPSEEK_MODEL` | No | `deepseek-chat` | Override DeepSeek model |
| `GEMINI_API_KEY` | No* | — | Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Override Gemini model |
| `SESSION_SECRET` | No | `change-me-in-production` | Session encryption key |
| `SECURE_COOKIE` | No | `false` | Set `Secure` flag on cookies |
| `CORS_ORIGINS` | No | `http://localhost:3000` | CORS allowed origins |
| `LOG_LEVEL` | No | `info` | Logging level |

\* At least one LLM API key required.

Frontend app: [svezchess](https://github.com/zero-shubham/svezchess)

## Development

```bash
# Install dependencies
uv sync

# Run dev stack (app + PostgreSQL)
make dev

# Lint, type-check, test
make lint
make typecheck
make test
```

Requires Python 3.14+, Docker, and Stockfish (`STOCKFISH_PATH` env var). See `app.env` for all configuration options.

## Stack

Python 3.14 · FastAPI · LangGraph · Stockfish · PostgreSQL 15 · SQLAlchemy (async) · WebSocket

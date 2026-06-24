# Architectural Blueprint: Hybrid Feature-Slice with Unified Gates

This document codifies the architectural pattern adopted for our Python platform—a highly specialized hybrid structural layout blending **Feature-Driven Vertical Slicing** with **Unified Delivery Gates** and strict **Dependency Inversion Principles (DIP)**.

---

## 🏛️ Architecture Overview

The system is organized into three primary conceptual layout planes:
1. **Unified Delivery Gates (`api/`, `cli/`)**: The system interfaces. They are thin transport-specific wrappers responsible for receiving inputs, enforcing perimeter protocols (HTTP, WebSockets, CLI formatting), and delegating tasks to the core application.
2. **Core Verticals (`core/`)**: Highly cohesive, domain-sliced modules. Each folder contains its own data layout rules, persistent structures, and service operations.
3. **Shared Kernel (`shared/`)**: Pure cross-cutting platform concerns (global configs, connection pools, common middleware) that provide the structural wiring for the app.

```text
.
├── src/
│   ├── shared/                     # Global cross-cutting infrastructure
│   │   ├── config.py               # Pydantic Settings / Environment variables
│   │   ├── database.py             # SQLAlchemy engine, session factory, Base, UoW
│   │   ├── middleware.py           # Cookie/token helpers & session dependency
│   │   ├── message.py              # WebSocket message types, Protocol (MessageSender)
│   │   ├── migrate.py              # Alembic migration runner
│   │   └── unit_of_work.py         # Unit-of-Work async context manager
│   │
│   ├── core/                       # Feature-sliced domain verticals
│   │   ├── game/                   # Rules, board, state, tools
│   │   │   ├── interfaces.py       # GameRepository ABC
│   │   │   ├── schemas.py          # Domain enums + dataclasses (Event, GameSession, …)
│   │   │   ├── board.py            # EzBoard (capture-aware chess board)
│   │   │   ├── models.py           # SQLAlchemy ORM tables (GameSessionModel, …)
│   │   │   ├── repository.py       # PostgresGameRepository implementing GameRepository
│   │   │   ├── services.py         # GameService + SessionManager
│   │   │   └── tools.py            # ToolProvider (Stockfish, session history, fen)
│   │   │
│   │   ├── agent/                  # Multi-agent orchestration layer
│   │   │   ├── interfaces.py       # Instructor ABC
│   │   │   ├── models.py           # LLMClient Protocol, result dataclasses, structured output schemas
│   │   │   ├── prompts.py          # PromptGetter singleton (curriculum prompt loader)
│   │   │   ├── token_tracker.py    # TokenUsageCallback, log_token_usage, token_totals
│   │   │   ├── clients.py          # LLMWrapper + create_llm_client (Claude / DeepSeek / …)
│   │   │   ├── services.py         # LangGraphInstructor
│   │   │   └── workflows/          # LangGraph state graphs
│   │   │       ├── move.py         # Move evaluation + instructor reply
│   │   │       ├── progress.py     # Session resume + new-game greeting
│   │   │       └── query.py        # Free-form student query handling
│   │   │
│   │   ├── user/                   # Identity and Profile context
│   │   │   ├── interfaces.py       # UserRepository ABC + UserServiceInterface ABC
│   │   │   ├── schemas.py          # User dataclass + UserRole enum
│   │   │   ├── models.py           # UserModel ORM table
│   │   │   ├── repository.py       # PostgresUserRepository
│   │   │   └── services.py         # UserService (create, authenticate, role mgmt)
│   │   │
│   │   └── session/                # Auth session management
│   │       ├── interfaces.py       # SessionRepository ABC
│   │       ├── schemas.py          # Session dataclass + new_session factory
│   │       ├── models.py           # UserSessionModel ORM table
│   │       └── repository.py       # PostgresSessionRepository
│   │
│   ├── api/                        # Unified Delivery Gate: Web API
│   │   ├── v1/                     # Versioned controllers / routers
│   │   │   ├── auth.py
│   │   │   ├── game_sessions.py
│   │   │   ├── users.py
│   │   │   └── websocket/          # WebSocket endpoint (module with router + msg_manager)
│   │   │       ├── __init__.py
│   │   │       ├── router.py       # WebSocket endpoint handler
│   │   │       └── msg_manager.py  # WebsocketMsgManager (connection pooler & broadcast)
│   │   ├── docs/                   # Swagger / ReDoc UI
│   │   │   └── docs.py
│   │   └── router.py               # Root FastAPI application assembler + lifespan
│   │
│   ├── cli/                        # Unified Delivery Gate: Terminal Tools
│   │   └── main.py                 # Typer CLI (admin, user, migrate commands)
│   │
│   └── main.py                     # Uvicorn bootstrap entry point
```

# Why This Structure Was Chosen

    High Developer Velocity: Grouping by domain vertical features prevents developers from having to jump across 4 different global layers just to add a single feature flag to a game rule. Everything to do with a feature lives within its core/ folder.

    Unified Transport Controls: Keeping API routers and WebSocket pools localized within a unified src/api/ layer prevents transport logic (e.g., handling HTTP exceptions or managing WebSocket broadcast connection pools) from corrupting core game simulation logic.

    Testability Without Side-Effects: By decoupling core features via Interfaces/Protocols, unit tests can run incredibly fast by passing mock structural variants without invoking a real database or hitting live third-party LLM endpoints.

# Rules of Engagement & Component Interaction

To prevent dependency cycles and maintain a clear flow of operations, every developer must adhere to three strict non-negotiable import boundaries.
1. Inward-Only Directional Flows

The outer interface layers (api/, cli/) may import from the core vertical layers, but the core vertical layers must never import from an interface layer.

    Correct Component Interaction: src/api/v1/game_sessions.py handles an HTTP POST request -> Validates input schemas -> Instantiates and invokes src/core/game/services.py.

2. Strict Cross-Feature Isolation

Core vertical features should remain decoupled from sister features. Direct mutations across database structures owned by other modules are strictly prohibited.

    Correct Component Interaction: If the session feature needs to fetch a user profile, src/core/session/services.py must call a method inside src/core/user/services.py rather than querying the user tables directly inside session/repository.py.

3. Shared Kernel Immutability

The shared/ folder provides low-level framework configurations only and must contain zero domain business context.

    Allowed: src/core/game/repository.py imports the session engine from src/shared/database.py.

    Prohibited: src/shared/database.py imports an explicit model or entity from src/core/game/models.py.

4. Schemas / Models Segregation

Every core vertical must keep domain types and persistence types in separate files:

    schemas.py — enums, dataclasses, domain-only types. No SQLAlchemy imports. No database knowledge.
    models.py — SQLAlchemy ORM table definitions only. No domain dataclasses or business logic.

    Rationale: Prevents domain logic from coupling to persistence details. Enables importing schemas without triggering ORM engine initialization.

5. Public API via __init__.py (Lazy Re-Export)

Each vertical's __init__.py serves as its public API surface. Leaf types (schemas, enums) are eagerly re-exported. Heavy dependencies (services, tools) use PEP 562 __getattr__ for lazy resolution to avoid circular imports.

Example (src/core/game/__init__.py):
```Python

# Eager: domain types have no heavy deps
from core.game.schemas import Event, GameSession, Level, ...
from core.game.board import EzBoard

# Lazy: services/tools trigger imports into other verticals
def __getattr__(name: str):
    if name == "GameService":
        from core.game.services import GameService
        return GameService
    if name == "ToolProvider":
        from core.game.tools import ToolProvider
        return ToolProvider
    raise AttributeError(...)
```

6. ORM Forward References

SQLAlchemy relationship() annotations use string forward references (e.g. Mapped["UserModel"]) with from __future__ import annotations. No TYPE_CHECKING imports needed — they are always resolved lazily by SQLAlchemy at mapper configuration time.

    Prohibited: from typing import TYPE_CHECKING; if TYPE_CHECKING: from core.user.models import UserModel
    Correct: from __future__ import annotations … user: Mapped["UserModel | None"] = relationship(…)  # noqa: F821

# Dependency Inversion via Python Protocols

To maintain high architectural resilience, core business components depend on abstractions, not concretions. We enforce this through structural subtyping via Python's typing.Protocol.

Instead of your core service knowing how PostgreSQL or a specific LLM SDK works, the core service defines an interface (Protocol) representing its exact needs. The concrete data adapters implement this protocol.
Example 1: The Repository Abstraction (src/core/game/interfaces.py)
```Python

from typing import Protocol, Optional
from src.core.game.schemas import GameState

class IGameRepository(Protocol):
    def get_game_by_id(self, game_id: str) -> Optional[GameState]:
        \"\"\"Fetch game state abstraction.\"\"\"
        ...

    def save_game(self, game: GameState) -> None:
        \"\"\"Persist game state abstraction.\"\"\"
        ...
```

Example 2: Injecting the Interface in Core Services (src/core/game/services.py)
```Python

from src.core.game.interfaces import IGameRepository
from src.core.game.schemas import GameState

class GameService:
    # Service accepts ANY object matching the IGameRepository structure
    def __init__(self, repository: IGameRepository):
        self.repository = repository

    def execute_move(self, game_id: str, move: str) -> GameState:
        game = self.repository.get_game_by_id(game_id)
        if not game:
            raise ValueError("Game session not found")
        
        # Apply core chess validations here...
        game.apply_move(move)
        
        self.repository.save_game(game)
        return game
```

Example 3: Implementation via Infrastructure Layer (src/core/game/repository.py)
```Python

from typing import Optional
from sqlalchemy.orm import Session
from src.core.game.schemas import GameState
from src.core.game.models import GameStateModel

class SQLGameRepository:
    \"\"\"Concrete implementation matching IGameRepository Protocol.\"\"\"
    def __init__(self, db_session: Session):
        self.db_session = db_session

    def get_game_by_id(self, game_id: str) -> Optional[GameState]:
        row = self.db_session.query(GameStateModel).filter(GameStateModel.id == game_id).first()
        return self._to_domain(row) if row else None

    def save_game(self, game: GameState) -> None:
        row = GameStateModel(id=game.id, ...)
        self.db_session.add(row)
        self.db_session.commit()
```
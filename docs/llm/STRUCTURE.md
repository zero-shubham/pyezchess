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
│   │   ├── database.py             # SQLAlchemy engine / session orchestrator
│   │   └── middleware.py           # Shared interceptors and logging pipelines
│   │
│   ├── core/                       # Feature-sliced domain verticals
│   │   ├── game/                   # Rules, move parsing, and logic state
│   │   │   ├── interfaces.py       # Structural Protocols (IGameRepository)
│   │   │   ├── models.py           # Core schemas & SQLAlchemy tables
│   │   │   ├── repository.py       # SQL persistence implementing the Protocol
│   │   │   └── services.py         # Business operations & chess validations
│   │   ├── agent/                  # Multi-agent orchestration layer
│   │   │   ├── interfaces.py       # ILLMClient Protocol
│   │   │   ├── prompts/            # System & behavioral prompt assets (.md)
│   │   │   ├── clients.py          # Claude / DeepSeek implementing the Protocol
│   │   │   └── services.py         # Instructor pipelines & token trackers
│   │   ├── user/                   # Identity and Profile context
│   │   └── session/                # Match orchestrations and runtime metadata
│   │
│   ├── api/                        # Unified Delivery Gate: Web API
│   │   ├── v1/                     # Versioned controllers / routers
│   │   │   ├── auth.py
│   │   │   ├── game_sessions.py
│   │   │   └── users.py
│   │   ├── websocket/              # High-frequency transport handlers
│   │   │   └── msg_manager.py      # Connection pooler & broadcast matrix
│   │   └── router.py               # Root FastAPI application assembler
│   │
│   ├── cli/                        # Unified Delivery Gate: Terminal Tools
│   │   ├── commands/               # Administrative tools & seeding scripts
│   │   └── main.py                 # Click / Typer entry point
│   │
│   └── main.py                     # Global application ASGI bootstrap
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

# Dependency Inversion via Python Protocols

To maintain high architectural resilience, core business components depend on abstractions, not concretions. We enforce this through structural subtyping via Python's typing.Protocol.

Instead of your core service knowing how PostgreSQL or a specific LLM SDK works, the core service defines an interface (Protocol) representing its exact needs. The concrete data adapters implement this protocol.
Example 1: The Repository Abstraction (src/core/game/interfaces.py)
```Python

from typing import Protocol, Optional
from src.core.game.models import GameState

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
from src.core.game.models import GameState

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
from src.core.game.models import GameState

class SQLGameRepository:
    \"\"\"Concrete implementation matching IGameRepository Protocol.\"\"\"
    def __init__(self, db_session: Session):
        self.db_session = db_session

    def get_game_by_id(self, game_id: str) -> Optional[GameState]:
        return self.db_session.query(GameState).filter(GameState.id == game_id).first()

    def save_game(self, game: GameState) -> None:
        self.db_session.add(game)
        self.db_session.commit()
```
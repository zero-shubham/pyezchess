"""add query event_type

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-07 00:00:00.000000
"""

from typing import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE game_session_events DROP CONSTRAINT IF EXISTS chk_event_type")
    op.execute(
        "ALTER TABLE game_session_events ADD CONSTRAINT chk_event_type "
        "CHECK (event_type IN ('move', 'hint', 'explain', 'move_result', 'start_game', 'query'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE game_session_events DROP CONSTRAINT IF EXISTS chk_event_type")
    op.execute(
        "ALTER TABLE game_session_events ADD CONSTRAINT chk_event_type "
        "CHECK (event_type IN ('move', 'hint', 'explain', 'move_result', 'start_game'))"
    )

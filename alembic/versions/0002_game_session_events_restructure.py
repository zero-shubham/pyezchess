"""game_session_events restructure

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-04 00:00:00.000000
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("game_session_events", "session_id", new_column_name="game_session_id")

    op.alter_column("game_session_events", "message", new_column_name="payload")

    op.alter_column(
        "game_session_events",
        "metadata",
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="metadata::jsonb",
        existing_type=sa.Text(),
    )

    op.alter_column(
        "game_session_events",
        "role",
        existing_type=sa.String(20),
        server_default="student",
        existing_server_default="system",
    )
    op.alter_column(
        "game_session_events",
        "event_type",
        existing_type=sa.String(30),
        server_default="start_game",
        existing_server_default="notification",
    )

    op.execute(
        "ALTER TABLE game_session_events ADD CONSTRAINT chk_event_type "
        "CHECK (event_type IN ('move', 'hint', 'explain', 'move_result', 'start_game'))"
    )
    op.execute(
        "ALTER TABLE game_session_events ADD CONSTRAINT chk_role "
        "CHECK (role IN ('student', 'instructor'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE game_session_events DROP CONSTRAINT chk_role")
    op.execute("ALTER TABLE game_session_events DROP CONSTRAINT chk_event_type")

    op.alter_column(
        "game_session_events",
        "role",
        existing_type=sa.String(20),
        server_default="system",
        existing_server_default="student",
    )
    op.alter_column(
        "game_session_events",
        "event_type",
        existing_type=sa.String(30),
        server_default="notification",
        existing_server_default="start_game",
    )

    op.alter_column(
        "game_session_events",
        "metadata",
        type_=sa.Text(),
        postgresql_using="metadata::text",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
    )

    op.alter_column("game_session_events", "payload", new_column_name="message")

    op.alter_column("game_session_events", "game_session_id", new_column_name="session_id")
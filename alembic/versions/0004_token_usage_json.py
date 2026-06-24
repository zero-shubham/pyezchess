"""change token_usage from integer to jsonb

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-23 00:00:00.000000
"""

from typing import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE game_sessions ALTER COLUMN token_usage DROP DEFAULT")
    op.execute(
        "ALTER TABLE game_sessions "
        "ALTER COLUMN token_usage TYPE jsonb "
        "USING jsonb_build_object('input_tokens', 0, 'output_tokens', 0)"
    )
    op.execute(
        "ALTER TABLE game_sessions "
        "ALTER COLUMN token_usage SET DEFAULT "
        '\'{"input_tokens": 0, "output_tokens": 0}\'::jsonb'
    )


def downgrade() -> None:
    op.execute("ALTER TABLE game_sessions ALTER COLUMN token_usage DROP DEFAULT")
    op.execute(
        "ALTER TABLE game_sessions "
        "ALTER COLUMN token_usage TYPE integer "
        "USING COALESCE((token_usage->>'input_tokens')::int, 0)"
    )
    op.execute(
        "ALTER TABLE game_sessions "
        "ALTER COLUMN token_usage SET DEFAULT 0"
    )

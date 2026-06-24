from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from shared.config import settings
from shared.database import Base

# Import all ORM models so they register with Base.metadata
import core.game.models  # noqa: F401
import core.user.models  # noqa: F401
import core.session.models  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline():
    url = settings.database_url.replace("+asyncpg", "")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    url = settings.database_url.replace("+asyncpg", "")
    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

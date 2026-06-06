from __future__ import annotations

from configs.config import settings


async def run_migrations(action: str, target: str):
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("+asyncpg", ""))

    if action == "upgrade":
        command.upgrade(alembic_cfg, target)
        print(f"Migrations upgraded to {target}")
    elif action == "downgrade":
        command.downgrade(alembic_cfg, target)
        print(f"Migrations downgraded by {target}")

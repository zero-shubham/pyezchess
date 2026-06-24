from __future__ import annotations

import asyncio
from uuid import UUID

import typer

from core.user.interfaces import (
    ErrAdminAlreadyExists,
    ErrUserAlreadyExists,
    ErrUserNotFound,
)
from core.user.services import UserService
from shared.database import async_session_factory
from core.user.repository import PostgresUserRepository
from shared.unit_of_work import UnitOfWork

cli = typer.Typer()
admin_cli = typer.Typer()
user_cli = typer.Typer()
migrate_cli = typer.Typer()

cli.add_typer(admin_cli, name="admin", help="Admin user management")
cli.add_typer(user_cli, name="user", help="Regular user management")
cli.add_typer(migrate_cli, name="migrate", help="Database migration commands")


@admin_cli.command("add")
def admin_add(username: str, email: str, password: str):
    async def _run():
        async with UnitOfWork(async_session_factory) as uow:
            svc = UserService(PostgresUserRepository(uow.session))
            try:
                user = await svc.create_admin(username, email, password)
                await uow.commit()
                print(f"Admin created: {user.id} ({user.username})")
            except (ErrAdminAlreadyExists, ErrUserAlreadyExists) as e:
                print(f"Error: {e}")
    asyncio.run(_run())


@admin_cli.command("list")
def admin_list():
    async def _run():
        async with UnitOfWork(async_session_factory) as uow:
            svc = UserService(PostgresUserRepository(uow.session))
            admins = await svc.list_admins()
            for a in admins:
                print(f"  {a.id}  {a.username}")
    asyncio.run(_run())


@admin_cli.command("make-admin")
def admin_make_admin(user_id: str):
    async def _run():
        from core.user.schemas import UserRole
        async with UnitOfWork(async_session_factory) as uow:
            svc = UserService(PostgresUserRepository(uow.session))
            try:
                user = await svc.update_role(UUID(user_id), UserRole.ADMIN)
                await uow.commit()
                print(f"User {user.username} is now admin")
            except ErrUserNotFound as e:
                print(f"Error: {e}")
    asyncio.run(_run())


@admin_cli.command("delete")
def admin_delete(user_id: str):
    async def _run():
        async with UnitOfWork(async_session_factory) as uow:
            svc = UserService(PostgresUserRepository(uow.session))
            try:
                await svc.delete_user(UUID(user_id))
                await uow.commit()
                print(f"User {user_id} deleted")
            except ErrUserNotFound as e:
                print(f"Error: {e}")
    asyncio.run(_run())


@user_cli.command("add")
def user_add(username: str, email: str, password: str):
    async def _run():
        async with UnitOfWork(async_session_factory) as uow:
            svc = UserService(PostgresUserRepository(uow.session))
            try:
                user = await svc.create_user(username, email, password)
                await uow.commit()
                print(f"User created: {user.id} ({user.username})")
            except ErrUserAlreadyExists as e:
                print(f"Error: {e}")
    asyncio.run(_run())


@user_cli.command("list")
def user_list():
    async def _run():
        async with UnitOfWork(async_session_factory) as uow:
            svc = UserService(PostgresUserRepository(uow.session))
            users = await svc.list_users()
            for u in users:
                print(f"  {u.id}  {u.username}")
    asyncio.run(_run())


@migrate_cli.command("up")
def migrate_up():
    from shared.migrate import run_migrations
    async def _run():
        await run_migrations("upgrade", "head")
    asyncio.run(_run())


@migrate_cli.command("down")
def migrate_down():
    from shared.migrate import run_migrations
    async def _run():
        await run_migrations("downgrade", "-1")
    asyncio.run(_run())


if __name__ == "__main__":
    cli()

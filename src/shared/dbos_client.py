from __future__ import annotations

from dbos import DBOSClient

from shared.config import settings

client = DBOSClient(system_database_url=settings.dbos_system_database_url)

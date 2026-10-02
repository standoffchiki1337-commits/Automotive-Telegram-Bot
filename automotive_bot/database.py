from __future__ import annotations

from pathlib import Path

from sqlalchemy import event, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from automotive_bot.config import Settings
from automotive_bot.models import Administrator, Base


def create_database(settings: Settings) -> tuple[AsyncEngine, async_sessionmaker]:
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)

    connect_args = {}
    if url.get_backend_name() == "postgresql":
        query = dict(url.query)
        sslmode = query.pop("sslmode", None)
        # asyncpg accepts `ssl`, not libpq's `sslmode` URL parameter.
        # `channel_binding` is also a libpq option and is not an asyncpg argument.
        query.pop("channel_binding", None)
        url = url.set(query=query)
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = sslmode

    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if url.get_backend_name() == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def initialize_database(engine: AsyncEngine, session_factory, admin_ids: tuple[int, ...]) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    if not admin_ids:
        return
    async with session_factory() as session:
        for telegram_id in admin_ids:
            existing = await session.scalar(
                select(Administrator).where(Administrator.telegram_id == telegram_id)
            )
            if existing is None:
                session.add(Administrator(telegram_id=telegram_id, added_by=None))
        await session.commit()

from __future__ import annotations

import argparse
import asyncio
import os

from sqlalchemy import select

from automotive_bot.config import Settings
from automotive_bot.database import create_database, initialize_database
from automotive_bot.models import Administrator


def _database_url() -> str:
    value = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./data/automotive.db"
    ).strip()
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+asyncpg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


async def _add_administrator(telegram_id: int) -> None:
    settings = Settings(
        bot_token="",
        database_url=_database_url(),
        admin_ids=(),
        currency=os.getenv("CURRENCY", "EUR"),
    )
    engine, session_factory = create_database(settings)
    try:
        await initialize_database(engine, session_factory, ())
        async with session_factory() as session:
            existing = await session.scalar(
                select(Administrator).where(
                    Administrator.telegram_id == telegram_id
                )
            )
            if existing is None:
                session.add(
                    Administrator(telegram_id=telegram_id, added_by=None)
                )
                await session.commit()
        print(f"Administrator {telegram_id} is ready.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add the first administrator to the automotive bot."
    )
    parser.add_argument(
        "telegram_id",
        type=int,
        help="Telegram numeric user ID of the person who will administer the bot",
    )
    args = parser.parse_args()
    if args.telegram_id <= 0:
        parser.error("telegram_id must be a positive integer")
    asyncio.run(_add_administrator(args.telegram_id))


if __name__ == "__main__":
    main()

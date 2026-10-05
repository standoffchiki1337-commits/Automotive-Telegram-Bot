from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    admin_ids: tuple[int, ...]
    currency: str


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required. Add it as an environment secret.")

    database_url = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./data/automotive.db"
    ).strip()
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql+asyncpg://", 1
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )

    raw_admin_ids = os.getenv("ADMIN_IDS", "")
    admin_ids: list[int] = []
    for value in raw_admin_ids.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            admin_ids.append(int(value))
        except ValueError as exc:
            raise RuntimeError("ADMIN_IDS must be comma-separated Telegram user IDs.") from exc

    return Settings(
        bot_token=token,
        database_url=database_url,
        admin_ids=tuple(dict.fromkeys(admin_ids)),
        currency="PLN",
    )

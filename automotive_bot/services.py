from __future__ import annotations

import logging
from decimal import Decimal
from html import escape
from urllib.parse import quote

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import User as TelegramUser
from sqlalchemy import select

from automotive_bot.i18n import t
from automotive_bot.models import Administrator, User

logger = logging.getLogger(__name__)


async def get_user_language(session_factory, telegram_id: int) -> str:
    async with session_factory() as session:
        user = await session.get(User, telegram_id)
        return user.language if user else "ru"


async def save_telegram_user(session_factory, telegram_user: TelegramUser) -> User:
    async with session_factory() as session:
        user = await session.get(User, telegram_user.id)
        display_name = " ".join(
            part for part in (telegram_user.first_name, telegram_user.last_name) if part
        )
        if user is None:
            user = User(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                display_name=display_name or telegram_user.full_name or str(telegram_user.id),
                language="ru",
            )
            session.add(user)
        else:
            user.username = telegram_user.username
            user.display_name = display_name or telegram_user.full_name or str(telegram_user.id)
        await session.commit()
        return user


async def is_administrator(session_factory, telegram_id: int) -> bool:
    async with session_factory() as session:
        return await session.get(Administrator, telegram_id) is not None


async def administrator_ids(session_factory) -> list[int]:
    async with session_factory() as session:
        return list(
            (await session.scalars(select(Administrator.telegram_id))).all()
        )


async def notify_administrators(bot: Bot, session_factory, text: str) -> int:
    admin_ids = await administrator_ids(session_factory)
    delivered = 0
    for telegram_id in admin_ids:
        try:
            await bot.send_message(telegram_id, text)
            delivered += 1
        except TelegramForbiddenError:
            logger.warning(
                "Administrator %s has not opened the bot; notification was not delivered.",
                telegram_id,
            )
        except TelegramAPIError as exc:
            logger.warning(
                "Could not deliver administrator notification to %s (%s).",
                telegram_id,
                type(exc).__name__,
            )
    return delivered


def money_text(value: Decimal | float | int, currency: str) -> str:
    amount = Decimal(str(value))
    formatted = (
        f"{amount:,.2f}".replace(",", " ")
        .replace(".", ",")
        .rstrip("0")
        .rstrip(",")
    )
    display_currency = "zł" if currency.strip().upper() == "PLN" else currency
    return f"{formatted} {escape(display_currency)}"


def display_name(user: User | None, telegram_id: int) -> str:
    if user is None:
        return str(telegram_id)
    if user.username:
        return f"{user.display_name} (@{user.username})"
    return user.display_name or str(telegram_id)


def telegram_user_url(telegram_id: int, username: str | None) -> str:
    if username:
        return f"https://t.me/{quote(username, safe='')}"
    return f"tg://user?id={telegram_id}"


async def primary_administrator_url(session_factory) -> str | None:
    async with session_factory() as session:
        telegram_id = await session.scalar(
            select(Administrator.telegram_id)
            .order_by(Administrator.created_at, Administrator.telegram_id)
            .limit(1)
        )
        if telegram_id is None:
            return None
        administrator = await session.get(User, telegram_id)
        return telegram_user_url(
            telegram_id, administrator.username if administrator else None
        )


def telegram_user_link(
    telegram_id: int, username: str | None, language: str
) -> str:
    if username:
        label = f"@{username}"
    else:
        label = t(language, "open_telegram_profile")
    return (
        f'<a href="{escape(telegram_user_url(telegram_id, username), quote=True)}">'
        f"{escape(label)}</a>"
    )

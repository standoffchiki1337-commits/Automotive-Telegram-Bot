from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import BotCommand

from automotive_bot.config import load_settings
from automotive_bot.database import create_database, initialize_database
from automotive_bot.handlers import admin, customer
from automotive_bot.translation import install_required_translation_models


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    engine, session_factory = create_database(settings)
    await initialize_database(engine, session_factory, settings.admin_ids)
    try:
        await asyncio.to_thread(install_required_translation_models)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Offline description translation is unavailable (%s).",
            type(exc).__name__,
        )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        events_isolation=SimpleEventIsolation(),
    )
    dispatcher["session_factory"] = session_factory
    dispatcher["settings"] = settings
    dispatcher.include_router(customer.router)
    dispatcher.include_router(admin.router)

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Open the car catalog"),
                BotCommand(command="help", description="Show the main menu"),
                BotCommand(command="cancel", description="Cancel the current action"),
                BotCommand(command="admin", description="Open the administrator menu"),
            ]
        )
        logging.getLogger(__name__).info("Automotive Telegram bot is polling.")
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            handle_as_tasks=True,
        )
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

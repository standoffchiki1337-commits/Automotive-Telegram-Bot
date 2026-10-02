from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from automotive_bot.models import Administrator


class AdminOnly(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, session_factory) -> bool:
        user = event.from_user
        if user is None:
            return False
        async with session_factory() as session:
            return await session.get(Administrator, user.id) is not None

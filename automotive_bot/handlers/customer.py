from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InputMediaPhoto,
    Message,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from automotive_bot.config import Settings
from automotive_bot.appointment_calendar import (
    DEALERSHIP_TIMEZONE,
    appointment_time_is_future,
    appointment_confirmation_keyboard,
    appointment_date_keyboard,
    appointment_hour_keyboard,
    appointment_month_keyboard,
    appointment_minute_keyboard,
    dealership_today,
    latest_appointment_date,
)
from automotive_bot.i18n import (
    FUEL_KEYS,
    LANGUAGES,
    TEXTS,
    TRANSMISSION_KEYS,
    fuel_label,
    selected_fuel_types,
    status_badge,
    t,
)
from automotive_bot.keyboards import (
    back_keyboard,
    admin_menu_keyboard,
    car_actions,
    car_results,
    fuel_keyboard,
    home_keyboard,
    language_keyboard,
    profile_actions,
    transmission_keyboard,
)
from automotive_bot.models import Car, Favorite, User, ViewingRequest
from automotive_bot.services import (
    get_user_language,
    is_administrator,
    money_text,
    notify_administrators,
    primary_administrator_url,
    remember_user_language,
    save_telegram_user,
    telegram_user_link,
)
from automotive_bot.states import ContactFlow, CustomerSearch, ViewingRequestFlow
from automotive_bot.translation import translate_description

router = Router(name="customer")
WELCOME_IMAGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "attached_assets"
    / "generated_images"
    / "autokomis_avatar.png"
)


def _all_button_texts(key: str) -> set[str]:
    return {language[key] for language in TEXTS.values()}


def _all_menu_button_texts() -> set[str]:
    keys = (
        "btn_cars",
        "btn_search",
        "btn_favorites",
        "btn_requests",
        "btn_profile",
        "btn_business_message",
        "btn_contact",
        "btn_language",
        "btn_help",
        "btn_admin",
    )
    return set().union(*(_all_button_texts(key) for key in keys))


async def _localized_user(session_factory, telegram_id: int) -> tuple[str, bool]:
    return (
        await get_user_language(session_factory, telegram_id),
        await is_administrator(session_factory, telegram_id),
    )


async def _profile_text(session_factory, telegram_id: int, language: str) -> str:
    async with session_factory() as session:
        user = await session.get(User, telegram_id)
        favorites = int(
            await session.scalar(
                select(func.count())
                .select_from(Favorite)
                .where(Favorite.user_id == telegram_id)
            )
            or 0
        )
        requests = int(
            await session.scalar(
                select(func.count())
                .select_from(ViewingRequest)
                .where(ViewingRequest.user_id == telegram_id)
            )
            or 0
        )
    language_names = {
        "ru": "Русский",
        "pl": "Polski",
        "uk": "Українська",
        "en": "English",
        "de": "Deutsch",
    }
    name = escape(user.display_name if user else str(telegram_id))
    username = (
        f"@{escape(user.username)}"
        if user and user.username
        else t(language, "profile_username_empty")
    )
    return (
        f"<b>{t(language, 'profile_title')}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{t(language, 'profile_name')}: {name}\n"
        f"{t(language, 'profile_username')}: {username}\n"
        f"{t(language, 'profile_language')}: {language_names.get(language, language_names['ru'])}\n"
        f"{t(language, 'profile_favorites')}: {favorites}\n"
        f"{t(language, 'profile_requests')}: {requests}\n"
        f"{t(language, 'profile_telegram_id')}: <code>{telegram_id}</code>"
    )


async def _request_history_text(session_factory, user_id: int, language: str) -> str:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(ViewingRequest, Car)
                .join(Car, Car.id == ViewingRequest.car_id)
                .where(ViewingRequest.user_id == user_id)
                .order_by(ViewingRequest.created_at.desc())
                .limit(25)
            )
        ).all()
    if not rows:
        return t(language, "requests_empty")
    return "\n\n".join(
        f"<b>#{request.id} · {escape(car.make_model)}</b>\n"
        f"{status_badge(language, request.status)}\n"
        f"{t(language, 'label_appointment_time')}: {escape(request.preferred_time)}"
        for request, car in rows
    )


async def _search_conditions(filters: dict) -> list:
    conditions = [Car.status == "available"]
    term = str(filters.get("term", "")).strip()
    if term:
        pattern = f"%{term}%"
        conditions.append(
            or_(Car.make_model.ilike(pattern), Car.description.ilike(pattern))
        )
    fuel = filters.get("fuel")
    if fuel and fuel != "any":
        conditions.append(
            or_(
                Car.fuel_type == fuel,
                Car.fuel_type.like(f"{fuel}+%"),
                Car.fuel_type.like(f"%+{fuel}"),
                Car.fuel_type.like(f"%+{fuel}+%"),
            )
        )
    transmission = filters.get("transmission")
    if transmission and transmission != "any":
        conditions.append(Car.transmission == transmission)
    year_min = int(filters.get("year_min") or 0)
    if year_min:
        conditions.append(Car.year >= year_min)
    price_max = filters.get("price_max")
    if price_max:
        conditions.append(Car.price <= Decimal(str(price_max)))
    return conditions


async def _show_car_page(
    bot: Bot,
    chat_id: int,
    user_id: int,
    session_factory,
    settings: Settings,
    state: FSMContext,
    page: int,
    language: str,
    replace_message: Message | None = None,
) -> None:
    page_size = 8
    data = await state.get_data()
    list_kind = data.get("list_kind", "all")

    async with session_factory() as session:
        if list_kind == "favorites":
            base = (
                select(Car)
                .join(Favorite, Favorite.car_id == Car.id)
                .where(Favorite.user_id == user_id, Car.status != "sold")
            )
            count_stmt = (
                select(func.count())
                .select_from(Car)
                .join(Favorite, Favorite.car_id == Car.id)
                .where(Favorite.user_id == user_id, Car.status != "sold")
            )
        else:
            conditions = (
                await _search_conditions(data)
                if list_kind == "search"
                else [Car.status == "available"]
            )
            base = select(Car).where(*conditions)
            count_stmt = select(func.count()).select_from(Car).where(*conditions)

        total = int(await session.scalar(count_stmt) or 0)
        cars = list(
            (
                await session.scalars(
                    base.options(selectinload(Car.photos))
                    .order_by(Car.created_at.desc(), Car.id.desc())
                    .offset(page * page_size)
                    .limit(page_size + 1)
                )
            ).all()
        )

    has_more = len(cars) > page_size
    cars = cars[:page_size]
    if not cars:
        if list_kind == "favorites":
            message = t(language, "favorites_empty")
        elif list_kind == "search":
            message = t(language, "search_none")
        else:
            message = t(language, "cars_empty")
        if replace_message:
            await replace_message.edit_text(
                message, reply_markup=back_keyboard(language)
            )
        else:
            await bot.send_message(
                chat_id, message, reply_markup=back_keyboard(language)
            )
        return

    await state.update_data(list_page=page)
    rows = [
        (
            car.id,
            t(
                language,
                "car_list_line",
                name=car.make_model,
                year=car.year,
            ).replace("  ·", " ·")
            + f" · {status_badge(language, car.status)}",
        )
        for car in cars
    ]
    heading = (
        "search_results"
        if list_kind == "search"
        else "btn_favorites"
        if list_kind == "favorites"
        else "btn_cars"
    )
    text = f"{t(language, heading)} ({total})"
    markup = car_results(
        language,
        rows,
        page,
        has_more,
        back_callback="menu:home",
    )
    if replace_message:
        await replace_message.edit_text(text, reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, reply_markup=markup)


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _truncate_utf16(text: str, limit: int) -> str:
    if _utf16_length(text) <= limit:
        return text
    if limit <= 0:
        return ""
    result: list[str] = []
    used = 0
    for character in text:
        units = _utf16_length(character)
        if used + units > limit - 1:
            break
        result.append(character)
        used += units
    return "".join(result).rstrip() + "…"


def _car_caption(
    car: Car,
    language: str,
    currency: str,
    photo_index: int = 0,
    photo_count: int = 0,
    description_text: str | None = None,
    translation_available: bool = True,
) -> str:
    fuel = fuel_label(language, car.fuel_type)
    transmission = t(
        language, TRANSMISSION_KEYS.get(car.transmission, "trans_other")
    )
    mileage = f"{car.mileage:,} {t(language, 'unit_km')}"
    year_line = f"📅 {t(language, 'label_year')}: {car.year}"
    mileage_line = f"🛞 {t(language, 'label_mileage')}: {mileage}"
    fuel_line = f"⛽ {t(language, 'label_fuel')}: {fuel}"
    transmission_line = f"⚙️ {t(language, 'label_transmission')}: {transmission}"
    description_label = t(language, "label_description")
    price = money_text(car.price, currency)
    status = status_badge(language, car.status)
    photo_counter = (
        f"📷 {photo_index + 1}/{photo_count}\n\n" if photo_count > 1 else ""
    )
    fixed_text = (
        f"{car.make_model}\n{status}\n\n{photo_counter}"
        f"{price}\n\n{t(language, 'specifications')}\n"
        f"{year_line} · {mileage_line}\n{fuel_line} · {transmission_line}\n\n"
        f"{description_label}\n"
    )
    description = (description_text if description_text is not None else car.description or "—").strip()
    if not translation_available:
        description = f"{description}\n\n{t(language, 'description_translation_unavailable')}"
    description = _truncate_utf16(
        description, max(0, 970 - _utf16_length(fixed_text))
    )
    return (
        f"🚘 <b>{escape(car.make_model)}</b>\n"
        f"{status}\n\n"
        f"{photo_counter}"
        f"💰 <b>{price}</b>\n\n"
        f"<b>{t(language, 'specifications')}</b>\n"
        f"{year_line} · {mileage_line}\n"
        f"{fuel_line} · {transmission_line}\n\n"
        f"<b>{description_label}</b>\n{escape(description)}"
    )


async def _show_car(
    bot: Bot,
    chat_id: int,
    user_id: int,
    car_id: int,
    session_factory,
    settings: Settings,
    language: str,
) -> None:
    async with session_factory() as session:
        car = await session.scalar(
            select(Car)
            .options(selectinload(Car.photos))
            .where(Car.id == car_id)
        )
        if car is None:
            await bot.send_message(chat_id, t(language, "car_missing"))
            return
        is_favorite = (
            await session.get(Favorite, (user_id, car_id)) is not None
        )
        photos = [photo.file_id for photo in car.photos]
        status = car.status
        original_description = car.description or ""
    translated_description, translation_available = await translate_description(
        original_description, language, settings.google_translate_api_key
    )
    caption = _car_caption(
        car,
        language,
        settings.currency,
        photo_count=len(photos),
        description_text=translated_description,
        translation_available=translation_available,
    )
    contact_url = await primary_administrator_url(session_factory)
    markup = car_actions(
        language,
        car_id,
        is_favorite,
        contact_url,
        photo_count=len(photos),
    )
    if status != "available":
        markup.inline_keyboard = [
            row
            for row in markup.inline_keyboard
            if not any(button.callback_data == f"appointment:{car_id}" for button in row)
        ]
    if photos:
        await bot.send_photo(
            chat_id,
            photo=photos[0],
            caption=caption,
            reply_markup=markup,
            parse_mode="HTML",
        )
    else:
        await bot.send_message(
            chat_id, caption, reply_markup=markup, parse_mode="HTML"
        )


@router.message(Command("start"))
async def start_command(message: Message, session_factory, state: FSMContext) -> None:
    if not message.from_user:
        return
    await state.clear()
    await save_telegram_user(session_factory, message.from_user)
    language = await get_user_language(session_factory, message.from_user.id)
    await message.answer(
        t(language, "language_prompt"), reply_markup=language_keyboard()
    )


@router.message(Command("help"))
async def help_command(
    message: Message, session_factory, state: FSMContext
) -> None:
    if not message.from_user:
        return
    await state.clear()
    language, admin = await _localized_user(session_factory, message.from_user.id)
    await message.answer(
        t(language, "help"),
        reply_markup=home_keyboard(language, admin),
        parse_mode="HTML",
    )


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext, session_factory) -> None:
    await state.clear()
    if message.from_user:
        language, admin = await _localized_user(session_factory, message.from_user.id)
        await message.answer(t(language, "btn_cancel"), reply_markup=home_keyboard(language, admin))


@router.message(F.text.in_(_all_menu_button_texts()))
async def navigate_from_main_menu(
    message: Message,
    state: FSMContext,
    session_factory,
    bot: Bot,
    settings: Settings,
) -> None:
    if not message.from_user or not message.text:
        return

    button = message.text
    await state.clear()
    if button in _all_button_texts("btn_cars"):
        await browse_cars(message, session_factory, bot, settings, state)
    elif button in _all_button_texts("btn_search"):
        await start_search(message, state, session_factory)
    elif button in _all_button_texts("btn_favorites"):
        await show_favorites(message, state, session_factory, bot, settings)
    elif button in _all_button_texts("btn_requests"):
        await my_requests(message, session_factory)
    elif button in _all_button_texts("btn_profile"):
        await show_profile(message, session_factory)
    elif button in (
        _all_button_texts("btn_business_message")
        | _all_button_texts("btn_contact")
    ):
        await start_contact(message, state, session_factory)
    elif button in _all_button_texts("btn_language"):
        await language_menu(message, session_factory)
    elif button in _all_button_texts("btn_help"):
        await help_command(message, session_factory, state)
    elif button in _all_button_texts("btn_admin"):
        language = await get_user_language(session_factory, message.from_user.id)
        if await is_administrator(session_factory, message.from_user.id):
            await message.answer(
                t(language, "admin_menu"),
                reply_markup=admin_menu_keyboard(language),
            )
        else:
            await message.answer(t(language, "admin_denied"))


@router.callback_query(F.data.startswith("language:"))
async def choose_language(callback: CallbackQuery, session_factory) -> None:
    if not callback.from_user:
        return
    language = str(callback.data).split(":", 1)[1]
    if language not in LANGUAGES:
        await callback.answer()
        return
    await save_telegram_user(session_factory, callback.from_user)
    async with session_factory() as session:
        user = await session.get(User, callback.from_user.id)
        if user:
            user.language = language
            await session.commit()
    remember_user_language(callback.from_user.id, language)
    admin = await is_administrator(session_factory, callback.from_user.id)
    await callback.answer(t(language, "language_set"))
    if callback.message:
        await callback.message.answer_photo(
            photo=FSInputFile(WELCOME_IMAGE_PATH),
            caption=t(language, "welcome"),
            reply_markup=home_keyboard(language, admin),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "menu:home")
async def home_menu(callback: CallbackQuery, session_factory, state: FSMContext) -> None:
    await state.clear()
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language, admin = await _localized_user(session_factory, callback.from_user.id)
    await callback.answer()
    await callback.message.answer_photo(
        photo=FSInputFile(WELCOME_IMAGE_PATH),
        caption=t(language, "welcome"),
        reply_markup=home_keyboard(language, admin),
        parse_mode="HTML",
    )


@router.message(StateFilter(None), F.text.in_(_all_button_texts("btn_language")))
async def language_menu(message: Message, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    await message.answer(t(language, "language_prompt"), reply_markup=language_keyboard())


@router.message(StateFilter(None), F.text.in_(_all_button_texts("btn_profile")))
async def show_profile(message: Message, session_factory) -> None:
    if not message.from_user:
        return
    language = await get_user_language(session_factory, message.from_user.id)
    await message.answer(
        await _profile_text(session_factory, message.from_user.id, language),
        reply_markup=profile_actions(language),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:profile")
async def show_profile_callback(
    callback: CallbackQuery, session_factory, state: FSMContext
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    language = await get_user_language(session_factory, callback.from_user.id)
    await callback.answer()
    await callback.message.answer(
        await _profile_text(session_factory, callback.from_user.id, language),
        reply_markup=profile_actions(language),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:favorites")
async def show_favorites_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory,
    bot: Bot,
    settings: Settings,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    await state.update_data(list_kind="favorites")
    language = await get_user_language(session_factory, callback.from_user.id)
    await callback.answer()
    await _show_car_page(
        bot,
        callback.message.chat.id,
        callback.from_user.id,
        session_factory,
        settings,
        state,
        0,
        language,
    )


@router.callback_query(F.data == "menu:requests")
async def show_requests_callback(
    callback: CallbackQuery, session_factory, state: FSMContext
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    language = await get_user_language(session_factory, callback.from_user.id)
    text = await _request_history_text(
        session_factory, callback.from_user.id, language
    )
    await callback.answer()
    await callback.message.answer(
        text,
        reply_markup=back_keyboard(language),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:contact")
async def start_contact_callback(
    callback: CallbackQuery, state: FSMContext, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    await state.clear()
    await state.set_state(ContactFlow.message)
    await callback.answer()
    await callback.message.answer(
        t(language, "contact_prompt"),
        reply_markup=back_keyboard(language),
    )


@router.message(StateFilter(None), F.text.in_(_all_button_texts("btn_cars")))
async def browse_cars(message: Message, session_factory, bot: Bot, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(list_kind="all")
    language = await get_user_language(session_factory, message.from_user.id)
    await _show_car_page(bot, message.chat.id, message.from_user.id, session_factory, settings, state, 0, language)


@router.callback_query(F.data == "menu:cars")
async def browse_cars_callback(callback: CallbackQuery, session_factory, bot: Bot, settings: Settings, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.clear()
    await state.update_data(list_kind="all")
    language = await get_user_language(session_factory, callback.from_user.id)
    await callback.answer()
    await _show_car_page(bot, callback.message.chat.id, callback.from_user.id, session_factory, settings, state, 0, language)


@router.message(StateFilter(None), F.text.in_(_all_button_texts("btn_search")))
async def start_search(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    await state.clear()
    await state.update_data(list_kind="search")
    await state.set_state(CustomerSearch.term)
    await message.answer(t(language, "search_term_prompt"))


@router.message(CustomerSearch.term)
async def receive_search_term(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    term = (message.text or "").strip()
    await state.update_data(term="" if term == "-" else term, list_kind="search")
    await state.set_state(CustomerSearch.fuel)
    await message.answer(
        t(language, "search_fuel_prompt"),
        reply_markup=fuel_keyboard(language, "search:fuel"),
    )


@router.callback_query(CustomerSearch.fuel, F.data.startswith("search:fuel:"))
async def search_choose_fuel(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, callback.from_user.id)
    await state.update_data(fuel=str(callback.data).split(":")[-1])
    await state.set_state(CustomerSearch.transmission)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            t(language, "search_transmission_prompt"),
            reply_markup=transmission_keyboard(language, "search:trans"),
        )


@router.callback_query(CustomerSearch.transmission, F.data.startswith("search:trans:"))
async def search_choose_transmission(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, callback.from_user.id)
    await state.update_data(transmission=str(callback.data).split(":")[-1])
    await state.set_state(CustomerSearch.year_min)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(language, "search_year_prompt"))


@router.message(CustomerSearch.year_min)
async def search_receive_year(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    try:
        year = int((message.text or "").strip())
        if year != 0 and not 1886 <= year <= 2100:
            raise ValueError
    except ValueError:
        await message.answer(t(language, "admin_invalid_year"))
        return
    await state.update_data(year_min=year)
    await state.set_state(CustomerSearch.price_max)
    await message.answer(t(language, "search_price_prompt"))


@router.message(CustomerSearch.price_max)
async def search_receive_price(message: Message, state: FSMContext, session_factory, bot: Bot, settings: Settings) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    try:
        price = Decimal("".join((message.text or "").split()).replace(",", "."))
        if price < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer(t(language, "admin_invalid_number"))
        return
    await state.update_data(price_max=float(price) if price else None, list_kind="search")
    await state.set_state(None)
    await _show_car_page(bot, message.chat.id, message.from_user.id, session_factory, settings, state, 0, language)


@router.callback_query(F.data.startswith("cars:page:"))
async def change_car_page(callback: CallbackQuery, state: FSMContext, session_factory, bot: Bot, settings: Settings) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    page = max(0, int(str(callback.data).split(":")[-1]))
    language = await get_user_language(session_factory, callback.from_user.id)
    await callback.answer()
    await _show_car_page(
        bot,
        callback.message.chat.id,
        callback.from_user.id,
        session_factory,
        settings,
        state,
        page,
        language,
        replace_message=callback.message,
    )


@router.message(StateFilter(None), F.text.in_(_all_button_texts("btn_favorites")))
async def show_favorites(message: Message, state: FSMContext, session_factory, bot: Bot, settings: Settings) -> None:
    await state.clear()
    await state.update_data(list_kind="favorites")
    language = await get_user_language(session_factory, message.from_user.id)
    await _show_car_page(bot, message.chat.id, message.from_user.id, session_factory, settings, state, 0, language)


@router.callback_query(F.data.startswith("car:photo:"))
async def change_car_photo(
    callback: CallbackQuery,
    session_factory,
    settings: Settings,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    _, _, raw_car_id, raw_index = str(callback.data).split(":")
    car_id, photo_index = int(raw_car_id), int(raw_index)
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        car = await session.scalar(
            select(Car)
            .options(selectinload(Car.photos))
            .where(Car.id == car_id)
        )
        if car is None or not car.photos:
            await callback.answer(t(language, "car_missing"), show_alert=True)
            return
        photos = [photo.file_id for photo in car.photos]
        if not 0 <= photo_index < len(photos):
            await callback.answer()
            return
        is_favorite = await session.get(
            Favorite, (callback.from_user.id, car_id)
        ) is not None
        status = car.status
        original_description = car.description or ""
    translated_description, translation_available = await translate_description(
        original_description, language, settings.google_translate_api_key
    )
    caption = _car_caption(
        car,
        language,
        settings.currency,
        photo_index=photo_index,
        photo_count=len(photos),
        description_text=translated_description,
        translation_available=translation_available,
    )
    contact_url = await primary_administrator_url(session_factory)
    markup = car_actions(
        language,
        car_id,
        is_favorite,
        contact_url,
        photo_count=len(photos),
        photo_index=photo_index,
    )
    if status != "available":
        markup.inline_keyboard = [
            row
            for row in markup.inline_keyboard
            if not any(
                button.callback_data == f"appointment:{car_id}" for button in row
            )
        ]
    await callback.answer()
    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=photos[photo_index], caption=caption, parse_mode="HTML"
        ),
        reply_markup=markup,
    )


@router.callback_query(F.data.startswith("car:back:"))
async def back_to_car_list(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory,
    bot: Bot,
    settings: Settings,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    list_kind = data.get("list_kind", "all")
    if list_kind not in ("all", "favorites", "search"):
        list_kind = "all"
    page = max(0, int(data.get("list_page", 0)))
    await state.set_state(None)
    await state.update_data(list_kind=list_kind)
    language = await get_user_language(session_factory, callback.from_user.id)
    await callback.answer()
    await callback.message.delete()
    await _show_car_page(
        bot,
        callback.message.chat.id,
        callback.from_user.id,
        session_factory,
        settings,
        state,
        page,
        language,
    )


@router.callback_query(F.data.startswith("car:"))
async def open_car(
    callback: CallbackQuery,
    session_factory,
    bot: Bot,
    settings: Settings,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    car_id = int(str(callback.data).split(":")[1])
    language = await get_user_language(session_factory, callback.from_user.id)
    await callback.answer()
    await callback.message.delete()
    await _show_car(
        bot, callback.message.chat.id, callback.from_user.id, car_id,
        session_factory, settings, language
    )


@router.callback_query(F.data.startswith("favorite:"))
async def toggle_favorite(
    callback: CallbackQuery,
    session_factory,
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    user_id = callback.from_user.id
    parts = str(callback.data).split(":")
    car_id = int(parts[1])
    photo_index = int(parts[2]) if len(parts) > 2 else 0
    language = await get_user_language(session_factory, user_id)
    async with session_factory() as session:
        car = await session.scalar(
            select(Car)
            .options(selectinload(Car.photos))
            .where(Car.id == car_id)
        )
        if car is None:
            await callback.answer(t(language, "car_missing"), show_alert=True)
            return
        favorite = await session.get(Favorite, (user_id, car_id))
        if favorite:
            await session.delete(favorite)
            response = t(language, "favorite_removed")
        else:
            if await session.get(User, user_id) is None:
                await save_telegram_user(session_factory, callback.from_user)
            session.add(Favorite(user_id=user_id, car_id=car_id))
            response = t(language, "favorite_added")
        photos_count = len(car.photos)
        status = car.status
        await session.commit()
    contact_url = await primary_administrator_url(session_factory)
    markup = car_actions(
        language,
        car_id,
        not bool(favorite),
        contact_url,
        photo_count=photos_count,
        photo_index=min(photo_index, max(photos_count - 1, 0)),
    )
    if status != "available":
        markup.inline_keyboard = [
            row
            for row in markup.inline_keyboard
            if not any(
                button.callback_data == f"appointment:{car_id}" for button in row
            )
        ]
    await callback.answer(response)
    await callback.message.edit_reply_markup(reply_markup=markup)


@router.callback_query(F.data.regexp(r"^appointment:[0-9]+$"))
async def start_appointment(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    car_id = int(str(callback.data).split(":")[1])
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        car = await session.get(Car, car_id)
        if car is None or car.status != "available":
            await callback.answer(t(language, "car_missing"), show_alert=True)
            return
    await state.update_data(car_id=car_id)
    await state.set_state(ViewingRequestFlow.preferred_time)
    await callback.answer()
    if callback.message:
        today = dealership_today()
        await callback.message.answer(
            f"{t(language, 'appointment_time_prompt')}\n\n"
            f"{t(language, 'appointment_timezone')}",
            reply_markup=appointment_date_keyboard(
                language, today.year, today.month, today
            ),
        )


@router.message(ViewingRequestFlow.preferred_time)
async def appointment_picker_reminder(
    message: Message, state: FSMContext, session_factory
) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    data = await state.get_data()
    selected_date = data.get("appointment_date")
    view_date = (
        date.fromisoformat(selected_date)
        if selected_date
        else dealership_today()
    )
    await message.answer(
        f"{t(language, 'appointment_time_prompt')}\n\n"
        f"{t(language, 'appointment_timezone')}",
        reply_markup=appointment_date_keyboard(
            language, view_date.year, view_date.month
        ),
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data.startswith("viewing:month:")
)
async def appointment_change_month(
    callback: CallbackQuery, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    _, _, _, raw_year, raw_month = str(callback.data).split(":")
    today = dealership_today()
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=appointment_date_keyboard(
            language, int(raw_year), int(raw_month), today
        )
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data.startswith("viewing:select-month:")
)
async def appointment_open_month_picker(
    callback: CallbackQuery, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    _, _, _, raw_year, raw_month = str(callback.data).split(":")
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=appointment_month_keyboard(
            language, int(raw_year), int(raw_month), dealership_today()
        )
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data.startswith("viewing:year:")
)
async def appointment_change_picker_year(
    callback: CallbackQuery, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    _, _, raw_year, raw_month = str(callback.data).split(":")
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=appointment_month_keyboard(
            language, int(raw_year), int(raw_month), dealership_today()
        )
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data.startswith("viewing:calendar:")
)
async def appointment_return_from_month_picker(
    callback: CallbackQuery, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    _, _, raw_year, raw_month = str(callback.data).split(":")
    today = dealership_today()
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=appointment_date_keyboard(
            language, int(raw_year), int(raw_month), today
        )
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data.startswith("viewing:date:")
)
async def appointment_choose_date(
    callback: CallbackQuery, state: FSMContext, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    selected_date = date.fromisoformat(str(callback.data).split(":")[-1])
    today = dealership_today()
    if not today <= selected_date <= latest_appointment_date(today):
        await callback.answer(
            t(language, "appointment_invalid_date"), show_alert=True
        )
        return
    await state.update_data(
        appointment_date=selected_date.isoformat(),
        appointment_hour=None,
        appointment_minute=None,
    )
    await callback.answer()
    await callback.message.edit_text(
        f"{t(language, 'appointment_pick_hour', date=selected_date.strftime('%d.%m.%Y'))}\n\n"
        f"{t(language, 'appointment_timezone')}",
        reply_markup=appointment_hour_keyboard(language, selected_date),
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data == "viewing:choose-date"
)
async def appointment_return_to_calendar(
    callback: CallbackQuery, state: FSMContext, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    data = await state.get_data()
    selected_date = data.get("appointment_date")
    view_date = date.fromisoformat(selected_date) if selected_date else dealership_today()
    today = dealership_today()
    await callback.answer()
    await callback.message.edit_text(
        f"{t(language, 'appointment_time_prompt')}\n\n"
        f"{t(language, 'appointment_timezone')}",
        reply_markup=appointment_date_keyboard(
            language, view_date.year, view_date.month, today
        ),
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data.startswith("viewing:hour:")
)
async def appointment_choose_hour(
    callback: CallbackQuery, state: FSMContext, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    data = await state.get_data()
    selected_date = data.get("appointment_date")
    if not selected_date:
        await callback.answer(t(language, "appointment_invalid_date"), show_alert=True)
        return
    hour = int(str(callback.data).split(":")[-1])
    if not 0 <= hour <= 23:
        await callback.answer()
        return
    selected_day = date.fromisoformat(selected_date)
    if not appointment_time_is_future(selected_day, hour, 59):
        await callback.answer(t(language, "appointment_time_past"), show_alert=True)
        return
    await state.update_data(appointment_hour=hour, appointment_minute=None)
    await callback.answer()
    await callback.message.edit_text(
        f"{t(language, 'appointment_pick_minute', date=date.fromisoformat(selected_date).strftime('%d.%m.%Y'), hour=f'{hour:02d}:__')}\n\n"
        f"{t(language, 'appointment_timezone')}",
        reply_markup=appointment_minute_keyboard(language, selected_day, hour),
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data == "viewing:choose-hour"
)
async def appointment_return_to_hours(
    callback: CallbackQuery, state: FSMContext, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    data = await state.get_data()
    selected_date = data.get("appointment_date")
    if not selected_date:
        await callback.answer(t(language, "appointment_invalid_date"), show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        f"{t(language, 'appointment_pick_hour', date=date.fromisoformat(selected_date).strftime('%d.%m.%Y'))}\n\n"
        f"{t(language, 'appointment_timezone')}",
        reply_markup=appointment_hour_keyboard(
            language, date.fromisoformat(selected_date)
        ),
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data.startswith("viewing:minute:")
)
async def appointment_choose_minute(
    callback: CallbackQuery, state: FSMContext, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    data = await state.get_data()
    selected_date = data.get("appointment_date")
    hour = data.get("appointment_hour")
    if selected_date is None or hour is None:
        await callback.answer(t(language, "appointment_invalid_date"), show_alert=True)
        return
    minute = int(str(callback.data).split(":")[-1])
    if not 0 <= minute <= 59:
        await callback.answer()
        return
    if not appointment_time_is_future(
        date.fromisoformat(selected_date), int(hour), minute
    ):
        await callback.answer(t(language, "appointment_time_past"), show_alert=True)
        return
    await state.update_data(appointment_minute=minute)
    chosen = datetime.combine(
        date.fromisoformat(selected_date),
        datetime.min.time().replace(hour=hour, minute=minute),
        tzinfo=DEALERSHIP_TIMEZONE,
    )
    shown_time = chosen.strftime("%d.%m.%Y %H:%M")
    await callback.answer()
    await callback.message.edit_text(
        f"{t(language, 'appointment_confirm_time', time=shown_time)}\n\n"
        f"{t(language, 'appointment_timezone')}",
        reply_markup=appointment_confirmation_keyboard(language),
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data == "viewing:choose-minute"
)
async def appointment_return_to_minutes(
    callback: CallbackQuery, state: FSMContext, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    data = await state.get_data()
    selected_date = data.get("appointment_date")
    hour = data.get("appointment_hour")
    if selected_date is None or hour is None:
        await callback.answer(t(language, "appointment_invalid_date"), show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        f"{t(language, 'appointment_change_minutes', hour=f'{hour:02d}')}\n"
        f"{t(language, 'appointment_timezone')}",
        reply_markup=appointment_minute_keyboard(
            language, date.fromisoformat(selected_date), int(hour)
        ),
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data == "viewing:confirm"
)
async def appointment_confirm_time(
    callback: CallbackQuery, state: FSMContext, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    selected_date = data.get("appointment_date")
    hour = data.get("appointment_hour")
    minute = data.get("appointment_minute")
    today = dealership_today()
    if (
        not selected_date
        or hour is None
        or minute is None
        or not today
        <= date.fromisoformat(selected_date)
        <= latest_appointment_date(today)
    ):
        language = await get_user_language(session_factory, callback.from_user.id)
        await callback.answer(
            t(language, "appointment_invalid_date"), show_alert=True
        )
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    chosen = datetime.combine(
        date.fromisoformat(selected_date),
        datetime.min.time().replace(hour=hour, minute=minute),
        tzinfo=DEALERSHIP_TIMEZONE,
    )
    if chosen <= datetime.now(DEALERSHIP_TIMEZONE):
        await callback.answer(t(language, "appointment_time_past"), show_alert=True)
        return
    preferred_time = (
        f"{chosen.strftime('%d.%m.%Y %H:%M')} (Europe/Warsaw)"
    )
    await state.update_data(preferred_time=preferred_time)
    await state.set_state(ViewingRequestFlow.message)
    await callback.answer()
    await callback.message.edit_text(
        t(language, "appointment_message_prompt"),
        reply_markup=back_keyboard(language, f"car:{data.get('car_id')}"),
    )


@router.callback_query(
    ViewingRequestFlow.preferred_time, F.data == "viewing:cancel"
)
async def appointment_cancel(
    callback: CallbackQuery, state: FSMContext, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        t(language, "appointment_cancelled"),
        reply_markup=back_keyboard(
            language, f"car:{data['car_id']}"
        ),
    )


@router.callback_query(F.data == "viewing:noop")
async def appointment_ignore_calendar_button(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(ViewingRequestFlow.message)
async def appointment_receive_message(message: Message, state: FSMContext, session_factory, bot: Bot) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    language = await get_user_language(session_factory, message.from_user.id)
    note = (message.text or "").strip()
    note = "" if note == "-" else note
    if len(note) > 2000:
        await message.answer(t(language, "message_too_long"))
        return
    async with session_factory() as session:
        user = await session.get(User, message.from_user.id)
        if user is None:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                display_name=message.from_user.full_name,
                language=language,
            )
            session.add(user)
        else:
            user.username = message.from_user.username
            user.display_name = message.from_user.full_name
        car = await session.scalar(
            select(Car).where(Car.id == data.get("car_id"), Car.status == "available")
        )
        if car is None:
            await state.clear()
            await message.answer(t(language, "car_missing"))
            return
        request = ViewingRequest(
            user_id=message.from_user.id,
            car_id=car.id,
            preferred_time=data["preferred_time"],
            message=note,
        )
        session.add(request)
        await session.commit()
        request_id = request.id
        car_name = car.make_model
    await state.clear()
    await message.answer(t(language, "appointment_created"))
    customer = message.from_user.full_name or str(message.from_user.id)
    notify_text = t(
        language,
        "notify_new_request",
        request_id=request_id,
        car=escape(car_name),
        customer=escape(customer),
        customer_link=telegram_user_link(
            message.from_user.id, message.from_user.username, language
        ),
        user_id=message.from_user.id,
        time=escape(data["preferred_time"]),
        message=escape(note or "—"),
    )
    await notify_administrators(bot, session_factory, notify_text)


@router.message(StateFilter(None), F.text.in_(_all_button_texts("btn_requests")))
async def my_requests(message: Message, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    await message.answer(
        await _request_history_text(session_factory, message.from_user.id, language),
        reply_markup=back_keyboard(language),
        parse_mode="HTML",
    )


@router.message(
    StateFilter(None),
    F.text.in_(
        _all_button_texts("btn_business_message") | _all_button_texts("btn_contact")
    ),
)
async def start_contact(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    await state.clear()
    await state.set_state(ContactFlow.message)
    await message.answer(
        t(language, "contact_prompt"), reply_markup=back_keyboard(language)
    )


@router.callback_query(F.data.startswith("contact:car:"))
async def start_listing_contact(
    callback: CallbackQuery, state: FSMContext, session_factory
) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    car_id = int(str(callback.data).split(":")[-1])
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        car = await session.get(Car, car_id)
        if car is None:
            await callback.answer(t(language, "car_missing"), show_alert=True)
            return
        car_name = car.make_model
    await state.update_data(car_id=car_id)
    await state.set_state(ContactFlow.message)
    await callback.answer()
    await callback.message.answer(
        t(language, "contact_seller_prompt", car=escape(car_name)),
        reply_markup=back_keyboard(language, f"car:{car_id}"),
    )


@router.message(ContactFlow.message)
async def contact_business(message: Message, state: FSMContext, session_factory, bot: Bot) -> None:
    if not message.from_user:
        return
    language = await get_user_language(session_factory, message.from_user.id)
    body = (message.text or "").strip()
    if not body:
        await message.answer(t(language, "contact_prompt"))
        return
    if len(body) > 3500:
        await message.answer(t(language, "message_too_long"))
        return
    data = await state.get_data()
    car_id = data.get("car_id")
    customer = escape(message.from_user.full_name or str(message.from_user.id))
    customer_link = telegram_user_link(
        message.from_user.id, message.from_user.username, language
    )
    if car_id:
        async with session_factory() as session:
            car = await session.get(Car, int(car_id))
            if car is None:
                await state.clear()
                await message.answer(t(language, "car_missing"))
                return
            text = t(
                language,
                "notify_listing_contact",
                car=escape(car.make_model),
                customer=customer,
                customer_link=customer_link,
                user_id=message.from_user.id,
                message=escape(body),
            )
    else:
        text = t(
            language,
            "notify_contact",
            customer=customer,
            customer_link=customer_link,
            user_id=message.from_user.id,
            message=escape(body),
        )
    delivered = await notify_administrators(bot, session_factory, text)
    await state.clear()
    if delivered:
        await message.answer(t(language, "contact_sent"))
    else:
        await message.answer(t(language, "no_admin"))



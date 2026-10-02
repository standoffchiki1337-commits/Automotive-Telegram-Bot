from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from automotive_bot.config import Settings
from automotive_bot.filters import AdminOnly
from automotive_bot.i18n import (
    FUEL_KEYS,
    STATUS_KEYS,
    TEXTS,
    TRANSMISSION_KEYS,
    status_badge,
    t,
)
from automotive_bot.keyboards import (
    admin_car_actions,
    admin_menu_keyboard,
    car_results,
    confirmation_keyboard,
    done_keyboard,
    edit_fields_keyboard,
    fuel_keyboard,
    request_actions,
    transmission_keyboard,
)
from automotive_bot.models import (
    Administrator,
    Car,
    CarPhoto,
    User,
    ViewingRequest,
)
from automotive_bot.services import (
    display_name,
    get_user_language,
    money_text,
)
from automotive_bot.states import AddCarFlow, AdministratorFlow, EditCarFlow

logger = logging.getLogger(__name__)
router = Router(name="administrators")
router.message.filter(AdminOnly())
router.callback_query.filter(AdminOnly())


def _all_button_texts(key: str) -> set[str]:
    return {language[key] for language in TEXTS.values()}


async def _show_admin_menu(message: Message, language: str) -> None:
    await message.answer(
        t(language, "admin_menu"), reply_markup=admin_menu_keyboard(language)
    )


@router.message(Command("admin"))
async def admin_command(message: Message, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    await _show_admin_menu(message, language)


async def _admin_car_text(session_factory, car_id: int, language: str, settings: Settings) -> str | None:
    async with session_factory() as session:
        car = await session.scalar(
            select(Car).options(selectinload(Car.photos)).where(Car.id == car_id)
        )
        if car is None:
            return None
        fuel = t(language, FUEL_KEYS.get(car.fuel_type, "fuel_any"))
        transmission = t(
            language, TRANSMISSION_KEYS.get(car.transmission, "trans_other")
        )
        return (
            f"<b>{escape(car.make_model)}</b>\n"
            f"{status_badge(language, car.status)}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"<b>{money_text(car.price, settings.currency)}</b>\n\n"
            f"<b>{t(language, 'specifications')}</b>\n"
            f"{t(language, 'label_year')}: {car.year}   ·   "
            f"{t(language, 'label_mileage')}: {car.mileage:,} {t(language, 'unit_km')}\n"
            f"{t(language, 'label_fuel')}: {fuel}\n"
            f"{t(language, 'label_transmission')}: {transmission}\n"
            "\n"
            f"<b>{t(language, 'label_description')}:</b>\n{escape(car.description or '—')}"
        )


async def _show_admin_car(
    callback: CallbackQuery,
    car_id: int,
    session_factory,
    settings: Settings,
    language: str,
) -> None:
    if not callback.message:
        return
    text = await _admin_car_text(session_factory, car_id, language, settings)
    if text is None:
        await callback.message.answer(t(language, "car_missing"))
        return
    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=admin_car_actions(language, car_id),
    )
    statuses = [
        [
            InlineKeyboardButton(
                text=t(language, f"status_{status}"),
                callback_data=f"admin:status:{car_id}:{status}",
            )
        ]
        for status in ("available", "reserved", "sold")
    ]
    await callback.message.answer(
        t(language, "label_status"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=statuses),
    )


async def _finish_car_creation(
    message: Message,
    state: FSMContext,
    session_factory,
    language: str,
    settings: Settings,
) -> None:
    data = await state.get_data()
    photos = list(data.get("photos", []))[:10]
    async with session_factory() as session:
        car = Car(
            make_model=data["make_model"],
            year=int(data["year"]),
            price=Decimal(str(data["price"])),
            mileage=int(data["mileage"]),
            fuel_type=data["fuel_type"],
            transmission=data["transmission"],
            description=data["description"],
            status="available",
            created_by=message.from_user.id,
        )
        session.add(car)
        await session.flush()
        for position, file_id in enumerate(photos):
            session.add(CarPhoto(car_id=car.id, file_id=file_id, position=position))
        await session.commit()
        car_id = car.id
    await state.clear()
    summary = await _admin_car_text(session_factory, car_id, language, settings)
    await message.answer(t(language, "admin_car_created"))
    if summary:
        await message.answer(summary, parse_mode="HTML")


@router.message(StateFilter(None), F.text.in_(_all_button_texts("btn_admin")))
async def admin_menu_from_button(message: Message, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    await _show_admin_menu(message, language)


@router.callback_query(F.data == "admin:panel")
async def admin_panel(callback: CallbackQuery, session_factory) -> None:
    language = await get_user_language(session_factory, callback.from_user.id)
    await callback.answer()
    if callback.message:
        await _show_admin_menu(callback.message, language)


@router.callback_query(F.data == "admin:add")
async def add_car_start(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, callback.from_user.id)
    await state.clear()
    await state.set_state(AddCarFlow.make_model)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(language, "admin_car_prompt"))


@router.message(AddCarFlow.make_model)
async def add_car_make_model(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    value = (message.text or "").strip()
    if len(value) < 2:
        await message.answer(t(language, "admin_car_prompt"))
        return
    await state.update_data(make_model=value)
    await state.set_state(AddCarFlow.year)
    await message.answer(t(language, "admin_year_prompt"))


@router.message(AddCarFlow.year)
async def add_car_year(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    try:
        year = int((message.text or "").strip())
        if not 1886 <= year <= 2100:
            raise ValueError
    except ValueError:
        await message.answer(t(language, "admin_invalid_year"))
        return
    await state.update_data(year=year)
    await state.set_state(AddCarFlow.price)
    await message.answer(t(language, "admin_price_prompt"))


@router.message(AddCarFlow.price)
async def add_car_price(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    try:
        price = Decimal((message.text or "").strip().replace(",", "."))
        if price <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer(t(language, "admin_invalid_price"))
        return
    await state.update_data(price=str(price))
    await state.set_state(AddCarFlow.mileage)
    await message.answer(t(language, "admin_mileage_prompt"))


@router.message(AddCarFlow.mileage)
async def add_car_mileage(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    try:
        mileage = int((message.text or "").strip())
        if mileage < 0:
            raise ValueError
    except ValueError:
        await message.answer(t(language, "admin_invalid_mileage"))
        return
    await state.update_data(mileage=mileage)
    await state.set_state(AddCarFlow.fuel)
    await message.answer(
        t(language, "admin_fuel_prompt"),
            reply_markup=fuel_keyboard(language, "admin:addfuel", include_any=False),
    )


@router.callback_query(AddCarFlow.fuel, F.data.startswith("admin:addfuel:"))
async def add_car_fuel(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, callback.from_user.id)
    fuel = str(callback.data).split(":")[-1]
    if fuel == "any" or fuel not in FUEL_KEYS:
        await callback.answer()
        return
    await state.update_data(fuel_type=fuel)
    await state.set_state(AddCarFlow.transmission)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            t(language, "admin_transmission_prompt"),
            reply_markup=transmission_keyboard(language, "admin:addtrans"),
        )


@router.callback_query(AddCarFlow.transmission, F.data.startswith("admin:addtrans:"))
async def add_car_transmission(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, callback.from_user.id)
    transmission = str(callback.data).split(":")[-1]
    if transmission not in TRANSMISSION_KEYS:
        await callback.answer()
        return
    await state.update_data(transmission=transmission)
    await state.set_state(AddCarFlow.description)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(language, "admin_description_prompt"))


@router.message(AddCarFlow.description)
async def add_car_description(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    description = (message.text or "").strip()
    if not description:
        await message.answer(t(language, "admin_description_prompt"))
        return
    if len(description) > 3000:
        await message.answer(t(language, "message_too_long"))
        return
    await state.update_data(description=description, photos=[])
    await state.set_state(AddCarFlow.photos)
    await message.answer(
        t(language, "admin_photos_prompt"),
        reply_markup=done_keyboard(language, "admin:addphotos:done"),
    )


@router.message(AddCarFlow.photos, F.photo)
async def add_car_photo(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    data = await state.get_data()
    photos = list(data.get("photos", []))
    if len(photos) >= 10:
        await message.answer(t(language, "admin_photo_limit"))
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(
        t(language, "admin_photo_added", count=len(photos)),
        reply_markup=done_keyboard(language, "admin:addphotos:done"),
    )


@router.callback_query(AddCarFlow.photos, F.data == "admin:addphotos:done")
async def finish_add_car(callback: CallbackQuery, state: FSMContext, session_factory, settings: Settings) -> None:
    language = await get_user_language(session_factory, callback.from_user.id)
    await callback.answer()
    if callback.message:
        await _finish_car_creation(
            callback.message, state, session_factory, language, settings
        )


@router.callback_query(F.data.startswith("admin:cars:"))
async def list_admin_cars(callback: CallbackQuery, session_factory, settings: Settings) -> None:
    if not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    page = max(0, int(str(callback.data).split(":")[-1]))
    page_size = 8
    async with session_factory() as session:
        total = int(await session.scalar(select(func.count()).select_from(Car)) or 0)
        cars = list(
            (
                await session.scalars(
                    select(Car)
                    .order_by(Car.created_at.desc(), Car.id.desc())
                    .offset(page * page_size)
                    .limit(page_size + 1)
                )
            ).all()
        )
    if not cars:
        await callback.answer()
        await callback.message.answer(t(language, "admin_cars_empty"))
        return
    has_more = len(cars) > page_size
    cars = cars[:page_size]
    rows = [
        (
            car.id,
            f"{car.make_model} — {money_text(car.price, settings.currency)} · "
             f"{car.year} · {status_badge(language, car.status)}",
        )
        for car in cars
    ]
    await callback.answer()
    await callback.message.answer(
        f"{t(language, 'btn_manage_cars')} ({total})",
        reply_markup=car_results(
            language, rows, page, has_more, admin=True, back_callback="admin:panel"
        ),
    )


@router.callback_query(F.data.startswith("admin:car:"))
async def open_admin_car(callback: CallbackQuery, session_factory, settings: Settings) -> None:
    if not callback.message:
        await callback.answer()
        return
    car_id = int(str(callback.data).split(":")[-1])
    language = await get_user_language(session_factory, callback.from_user.id)
    await callback.answer()
    await _show_admin_car(callback, car_id, session_factory, settings, language)


@router.callback_query(F.data.startswith("admin:status:"))
async def update_car_status(callback: CallbackQuery, session_factory, settings: Settings) -> None:
    if not callback.message:
        await callback.answer()
        return
    _, _, raw_id, status = str(callback.data).split(":")
    car_id = int(raw_id)
    language = await get_user_language(session_factory, callback.from_user.id)
    if status not in ("available", "reserved", "sold"):
        await callback.answer()
        return
    async with session_factory() as session:
        car = await session.get(Car, car_id)
        if car is None:
            await callback.answer(t(language, "car_missing"), show_alert=True)
            return
        car.status = status
        await session.commit()
    await callback.answer(t(language, "admin_status_updated"))
    await _show_admin_car(callback, car_id, session_factory, settings, language)


@router.callback_query(F.data.startswith("admin:edit:"))
async def edit_car_start(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    if not callback.message:
        await callback.answer()
        return
    car_id = int(str(callback.data).split(":")[-1])
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        if await session.get(Car, car_id) is None:
            await callback.answer(t(language, "car_missing"), show_alert=True)
            return
    await state.clear()
    await state.update_data(car_id=car_id)
    await callback.answer()
    await callback.message.answer(
        t(language, "admin_edit_prompt"),
        reply_markup=edit_fields_keyboard(language, car_id),
    )


@router.callback_query(F.data.startswith("admin:editfield:"))
async def choose_edit_field(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    if not callback.message:
        await callback.answer()
        return
    _, _, _, raw_id, field = str(callback.data).split(":")
    car_id = int(raw_id)
    language = await get_user_language(session_factory, callback.from_user.id)
    editable = {
        "make_model",
        "year",
        "price",
        "mileage",
        "fuel_type",
        "transmission",
        "description",
    }
    if field not in editable:
        await callback.answer()
        return
    await state.clear()
    await state.update_data(car_id=car_id, field=field)
    if field == "fuel_type":
        await state.set_state(EditCarFlow.value)
        await callback.answer()
        await callback.message.answer(
            t(language, "admin_fuel_prompt"),
            reply_markup=fuel_keyboard(
                language,
                f"admin:editchoice:{car_id}:fuel_type",
                include_any=False,
            ),
        )
        return
    if field == "transmission":
        await state.set_state(EditCarFlow.value)
        await callback.answer()
        await callback.message.answer(
            t(language, "admin_transmission_prompt"),
            reply_markup=transmission_keyboard(
                language, f"admin:editchoice:{car_id}:transmission"
            ),
        )
        return
    await state.set_state(EditCarFlow.value)
    await callback.answer()
    await callback.message.answer(t(language, "admin_edit_value"))


@router.callback_query(EditCarFlow.value, F.data.startswith("admin:editchoice:"))
async def edit_car_choice(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory,
    settings: Settings,
) -> None:
    parts = str(callback.data).split(":")
    car_id, field, value = int(parts[2]), parts[3], parts[4]
    language = await get_user_language(session_factory, callback.from_user.id)
    if field == "fuel_type" and value not in FUEL_KEYS:
        await callback.answer(t(language, "admin_invalid_number"), show_alert=True)
        return
    if field == "transmission" and value not in TRANSMISSION_KEYS:
        await callback.answer(t(language, "admin_invalid_number"), show_alert=True)
        return
    async with session_factory() as session:
        car = await session.get(Car, car_id)
        if car is None:
            await callback.answer(t(language, "car_missing"), show_alert=True)
            return
        setattr(car, field, value)
        await session.commit()
    await state.clear()
    await callback.answer(t(language, "admin_saved"))
    if callback.message:
        await _show_admin_car(callback, car_id, session_factory, settings, language)


def _parse_edit_value(field: str, raw: str):
    value = raw.strip()
    if field == "make_model":
        return value if len(value) >= 2 else None
    if field == "description":
        return value
    if field == "year":
        year = int(value)
        return year if 1886 <= year <= 2100 else None
    if field == "price":
        price = Decimal(value.replace(",", "."))
        return price if price > 0 else None
    if field == "mileage":
        mileage = int(value)
        return mileage if mileage >= 0 else None
    return None


@router.message(EditCarFlow.value)
async def edit_car_text_value(message: Message, state: FSMContext, session_factory, settings: Settings) -> None:
    data = await state.get_data()
    field = data.get("field")
    if field in ("fuel_type", "transmission"):
        return
    language = await get_user_language(session_factory, message.from_user.id)
    try:
        parsed = _parse_edit_value(field, message.text or "")
    except (ValueError, InvalidOperation):
        parsed = None
    if field == "description" and len(message.text or "") > 3000:
        parsed = None
    if parsed is None:
        error_key = {
            "year": "admin_invalid_year",
            "price": "admin_invalid_price",
            "mileage": "admin_invalid_mileage",
        }.get(field, "admin_invalid_number")
        await message.answer(t(language, error_key))
        return
    async with session_factory() as session:
        car = await session.get(Car, int(data["car_id"]))
        if car is None:
            await state.clear()
            await message.answer(t(language, "car_missing"))
            return
        setattr(car, field, parsed)
        await session.commit()
    car_id = int(data["car_id"])
    await state.clear()
    await message.answer(t(language, "admin_saved"))
    text = await _admin_car_text(session_factory, car_id, language, settings)
    if text:
        await message.answer(text, parse_mode="HTML", reply_markup=admin_car_actions(language, car_id))


@router.callback_query(F.data.startswith("admin:delete:"))
async def ask_delete_car(callback: CallbackQuery, session_factory) -> None:
    if not callback.message:
        await callback.answer()
        return
    car_id = int(str(callback.data).split(":")[-1])
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        if await session.get(Car, car_id) is None:
            await callback.answer(t(language, "car_missing"), show_alert=True)
            return
    await callback.answer()
    await callback.message.answer(
        t(language, "admin_delete_prompt"),
        reply_markup=confirmation_keyboard(
            language, f"admin:deleteyes:{car_id}", f"admin:car:{car_id}"
        ),
    )


@router.callback_query(F.data.startswith("admin:deleteyes:"))
async def delete_car(callback: CallbackQuery, session_factory) -> None:
    car_id = int(str(callback.data).split(":")[-1])
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        car = await session.get(Car, car_id)
        if car is not None:
            await session.delete(car)
            await session.commit()
    await callback.answer(t(language, "admin_deleted"))
    if callback.message:
        await callback.message.answer(t(language, "admin_deleted"))


@router.callback_query(F.data.startswith("admin:photos:"))
async def add_photos_start(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    if not callback.message:
        await callback.answer()
        return
    car_id = int(str(callback.data).split(":")[-1])
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        if await session.get(Car, car_id) is None:
            await callback.answer(t(language, "car_missing"), show_alert=True)
            return
    await state.clear()
    await state.update_data(car_id=car_id)
    await state.set_state(EditCarFlow.photos)
    await callback.answer()
    await callback.message.answer(
        t(language, "admin_photos_prompt"),
        reply_markup=done_keyboard(language, f"admin:photosdone:{car_id}"),
    )


@router.message(EditCarFlow.photos, F.photo)
async def add_photos_to_car(message: Message, state: FSMContext, session_factory) -> None:
    data = await state.get_data()
    car_id = int(data["car_id"])
    language = await get_user_language(session_factory, message.from_user.id)
    async with session_factory() as session:
        car = await session.scalar(
            select(Car).options(selectinload(Car.photos)).where(Car.id == car_id)
        )
        if car is None:
            await state.clear()
            await message.answer(t(language, "car_missing"))
            return
        if len(car.photos) >= 10:
            await message.answer(t(language, "admin_photo_limit"))
            return
        session.add(
            CarPhoto(
                car_id=car_id,
                file_id=message.photo[-1].file_id,
                position=len(car.photos),
            )
        )
        await session.commit()
        count = len(car.photos) + 1
    await message.answer(
        t(language, "admin_photo_added", count=count),
        reply_markup=done_keyboard(language, f"admin:photosdone:{car_id}"),
    )


@router.callback_query(EditCarFlow.photos, F.data.startswith("admin:photosdone:"))
async def finish_edit_photos(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    car_id = int(str(callback.data).split(":")[-1])
    language = await get_user_language(session_factory, callback.from_user.id)
    await state.clear()
    await callback.answer(t(language, "photos_saved"))
    if callback.message:
        await callback.message.answer(
            t(language, "photos_saved"),
            reply_markup=admin_car_actions(language, car_id),
        )


@router.callback_query(F.data == "admin:requests")
async def list_viewing_requests(callback: CallbackQuery, session_factory) -> None:
    if not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(ViewingRequest, Car, User)
                .join(Car, Car.id == ViewingRequest.car_id)
                .join(User, User.telegram_id == ViewingRequest.user_id)
                .order_by(ViewingRequest.created_at.desc())
                .limit(30)
            )
        ).all()
    await callback.answer()
    if not rows:
        await callback.message.answer(t(language, "admin_requests_empty"))
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"#{request.id} · {car.make_model} · {customer.display_name}"[:60],
                    callback_data=f"admin:req:{request.id}",
                )
            ]
            for request, car, customer in rows
        ]
        + [[InlineKeyboardButton(text=t(language, "btn_back"), callback_data="admin:panel")]]
    )
    await callback.message.answer(
        t(language, "btn_manage_requests"), reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("admin:req:"))
async def open_viewing_request(callback: CallbackQuery, session_factory) -> None:
    if not callback.message:
        await callback.answer()
        return
    request_id = int(str(callback.data).split(":")[-1])
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        row = (
            await session.execute(
                select(ViewingRequest, Car, User)
                .join(Car, Car.id == ViewingRequest.car_id)
                .join(User, User.telegram_id == ViewingRequest.user_id)
                .where(ViewingRequest.id == request_id)
            )
        ).first()
    await callback.answer()
    if not row:
        await callback.message.answer(t(language, "admin_requests_empty"))
        return
    request, car, customer = row
    text = t(
        language,
        "request_details",
        request_id=request.id,
        car=escape(car.make_model),
        customer=escape(display_name(customer, request.user_id)),
        user_id=request.user_id,
        time=escape(request.preferred_time),
        message=escape(request.message or "—"),
        status=t(language, STATUS_KEYS.get(request.status, "status_pending")),
    )
    await callback.message.answer(
        text, reply_markup=request_actions(language, request.id)
    )


@router.callback_query(F.data.startswith("admin:reqstatus:"))
async def update_request_status(callback: CallbackQuery, session_factory, bot: Bot) -> None:
    parts = str(callback.data).split(":")
    request_id, new_status = int(parts[2]), parts[3]
    language = await get_user_language(session_factory, callback.from_user.id)
    if new_status not in ("confirmed", "completed", "cancelled"):
        await callback.answer()
        return
    async with session_factory() as session:
        request = await session.get(ViewingRequest, request_id)
        if request is None:
            await callback.answer(t(language, "admin_requests_empty"), show_alert=True)
            return
        request.status = new_status
        user_id = request.user_id
        await session.commit()
    user_language = await get_user_language(session_factory, user_id)
    try:
        await bot.send_message(
            user_id,
            t(
                user_language,
                "notify_request_status",
                request_id=request_id,
                status=t(user_language, STATUS_KEYS[new_status]),
            ),
        )
    except TelegramAPIError:
        logger.info("Could not notify customer %s about request %s.", user_id, request_id)
    await callback.answer(t(language, "admin_request_updated"))
    if callback.message:
        await callback.message.answer(t(language, "admin_request_updated"))


@router.callback_query(F.data == "admin:admins")
async def list_administrators(callback: CallbackQuery, session_factory) -> None:
    if not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        ids = list(
            (
                await session.scalars(
                    select(Administrator.telegram_id).order_by(Administrator.created_at)
                )
            ).all()
        )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "btn_add_admin"), callback_data="admin:addadmin")],
            [InlineKeyboardButton(text=t(language, "btn_remove_admin"), callback_data="admin:removeadmin")],
            [InlineKeyboardButton(text=t(language, "btn_back"), callback_data="admin:panel")],
        ]
    )
    label = "\n".join(str(telegram_id) for telegram_id in ids) or t(language, "admin_list_empty")
    await callback.answer()
    await callback.message.answer(label, reply_markup=keyboard)


@router.callback_query(F.data == "admin:addadmin")
async def add_admin_start(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, callback.from_user.id)
    await state.clear()
    await state.set_state(AdministratorFlow.add_id)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(language, "admin_id_prompt"))


@router.message(AdministratorFlow.add_id)
async def add_admin_receive_id(message: Message, state: FSMContext, session_factory, bot: Bot) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    try:
        telegram_id = int((message.text or "").strip())
        if telegram_id <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t(language, "admin_invalid_number"))
        return
    async with session_factory() as session:
        existing = await session.get(Administrator, telegram_id)
        if existing is None:
            session.add(Administrator(telegram_id=telegram_id, added_by=message.from_user.id))
            await session.commit()
    await state.clear()
    await message.answer(t(language, "admin_added"))
    if existing is None:
        try:
            await bot.send_message(
                telegram_id,
                t(language, "admin_menu"),
            )
        except TelegramAPIError:
            logger.info("New administrator %s has not opened the bot yet.", telegram_id)


@router.callback_query(F.data == "admin:removeadmin")
async def remove_admin_start(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, callback.from_user.id)
    await state.clear()
    await state.set_state(AdministratorFlow.remove_id)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(language, "admin_id_prompt"))


@router.message(AdministratorFlow.remove_id)
async def remove_admin_receive_id(message: Message, state: FSMContext, session_factory) -> None:
    language = await get_user_language(session_factory, message.from_user.id)
    try:
        telegram_id = int((message.text or "").strip())
        if telegram_id <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t(language, "admin_invalid_number"))
        return
    async with session_factory() as session:
        admin = await session.get(Administrator, telegram_id)
        count = int(await session.scalar(select(func.count()).select_from(Administrator)) or 0)
        if admin is None:
            response = t(language, "admin_not_found")
        elif count <= 1:
            response = t(language, "admin_last_protected")
        elif telegram_id == message.from_user.id:
            response = t(language, "admin_self_protected")
        else:
            await session.delete(admin)
            await session.commit()
            response = t(language, "admin_removed")
    await state.clear()
    await message.answer(response)


@router.callback_query(F.data == "admin:stats")
async def show_admin_stats(callback: CallbackQuery, session_factory) -> None:
    if not callback.message:
        await callback.answer()
        return
    language = await get_user_language(session_factory, callback.from_user.id)
    async with session_factory() as session:
        users = int(await session.scalar(select(func.count()).select_from(User)) or 0)
        cars = int(await session.scalar(select(func.count()).select_from(Car)) or 0)
        requests = int(
            await session.scalar(select(func.count()).select_from(ViewingRequest)) or 0
        )
    await callback.answer()
    await callback.message.answer(
        t(language, "admin_stats", users=users, cars=cars, requests=requests)
    )

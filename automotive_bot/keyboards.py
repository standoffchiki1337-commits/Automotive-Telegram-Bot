from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from automotive_bot.i18n import LANGUAGES, t


def language_keyboard() -> InlineKeyboardMarkup:
    labels = {
        "ru": "Русский",
        "pl": "Polski",
        "uk": "Українська",
        "en": "English",
        "de": "Deutsch",
    }
    buttons = [
        InlineKeyboardButton(text=labels[code], callback_data=f"language:{code}")
        for code in LANGUAGES
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    )


def home_keyboard(language: str, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=t(language, "btn_cars")), KeyboardButton(text=t(language, "btn_search"))],
        [KeyboardButton(text=t(language, "btn_favorites")), KeyboardButton(text=t(language, "btn_requests"))],
        [
            KeyboardButton(text=t(language, "btn_profile")),
            KeyboardButton(text=t(language, "btn_business_message")),
        ],
        [KeyboardButton(text=t(language, "btn_language"))],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=t(language, "btn_admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def back_keyboard(language: str, callback: str = "menu:home") -> InlineKeyboardMarkup:
    if callback == "menu:home":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(language, "btn_main_menu"), callback_data=callback)]
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "btn_back"), callback_data=callback)],
            [InlineKeyboardButton(text=t(language, "btn_main_menu"), callback_data="menu:home")],
        ]
    )


def fuel_keyboard(
    language: str, callback_prefix: str, include_any: bool = True
) -> InlineKeyboardMarkup:
    options = [
        ("petrol", "fuel_petrol"),
        ("diesel", "fuel_diesel"),
        ("electric", "fuel_electric"),
        ("hybrid", "fuel_hybrid"),
        ("lpg", "fuel_lpg"),
    ]
    if include_any:
        options.insert(0, ("any", "fuel_any"))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, label), callback_data=f"{callback_prefix}:{value}")]
            for value, label in options
        ]
    )


def transmission_keyboard(language: str, callback_prefix: str) -> InlineKeyboardMarkup:
    options = [
        ("any", "trans_any"),
        ("manual", "trans_manual"),
        ("automatic", "trans_automatic"),
        ("other", "trans_other"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, label), callback_data=f"{callback_prefix}:{value}")]
            for value, label in options
        ]
    )


def car_actions(
    language: str,
    car_id: int,
    is_favorite: bool,
    contact_url: str | None,
    photo_count: int = 1,
    photo_index: int = 0,
) -> InlineKeyboardMarkup:
    favorite_key = "btn_unfavorite" if is_favorite else "btn_favorite"
    contact_button = (
        InlineKeyboardButton(text=t(language, "btn_contact"), url=contact_url)
        if contact_url
        else InlineKeyboardButton(
            text=t(language, "btn_contact"), callback_data=f"contact:car:{car_id}"
        )
    )
    rows = [
        [
            InlineKeyboardButton(
                text=t(language, favorite_key),
                callback_data=f"favorite:{car_id}:{photo_index}",
            )
        ]
    ]
    if photo_count > 1:
        previous_index = (photo_index - 1) % photo_count
        next_index = (photo_index + 1) % photo_count
        rows.append(
            [
                InlineKeyboardButton(
                    text="‹",
                    callback_data=f"car:photo:{car_id}:{previous_index}",
                ),
                InlineKeyboardButton(
                    text="›",
                    callback_data=f"car:photo:{car_id}:{next_index}",
                ),
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=t(language, "btn_appointment"),
                    callback_data=f"appointment:{car_id}",
                ),
                contact_button,
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "btn_back"), callback_data=f"car:back:{car_id}"
                ),
                InlineKeyboardButton(
                    text=t(language, "btn_main_menu"), callback_data="menu:home"
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def car_results(
    language: str,
    cars: list[tuple[int, str]],
    page: int,
    has_more: bool,
    admin: bool = False,
    back_callback: str = "menu:home",
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label[:60], callback_data=f"{'admin:car' if admin else 'car'}:{car_id}")]
        for car_id, label in cars
    ]
    pagination: list[InlineKeyboardButton] = []
    if page > 0:
        pagination.append(
            InlineKeyboardButton(text="‹", callback_data=f"{'admin:cars' if admin else 'cars:page'}:{page - 1}")
        )
    if has_more:
        pagination.append(
            InlineKeyboardButton(text="›", callback_data=f"{'admin:cars' if admin else 'cars:page'}:{page + 1}")
        )
    if pagination:
        rows.append(pagination)
    if back_callback == "menu:home":
        rows.append([InlineKeyboardButton(text=t(language, "btn_main_menu"), callback_data="menu:home")])
    else:
        rows.append(
            [
                InlineKeyboardButton(text=t(language, "btn_back"), callback_data=back_callback),
                InlineKeyboardButton(text=t(language, "btn_main_menu"), callback_data="menu:home"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def status_keyboard(language: str, car_id: int) -> InlineKeyboardMarkup:
    labels = {
        "available": "status_available",
        "reserved": "status_reserved",
        "sold": "status_sold",
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, label),
                    callback_data=f"admin:status:{car_id}:{status}",
                )
            ]
            for status, label in labels.items()
        ]
    )


def admin_car_actions(language: str, car_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(language, "btn_edit"), callback_data=f"admin:edit:{car_id}"),
                InlineKeyboardButton(text=t(language, "btn_photos"), callback_data=f"admin:photos:{car_id}"),
            ],
            [InlineKeyboardButton(text=t(language, "btn_delete"), callback_data=f"admin:delete:{car_id}")],
            [
                InlineKeyboardButton(text=t(language, "btn_back"), callback_data="admin:cars:0"),
                InlineKeyboardButton(text=t(language, "btn_admin_menu"), callback_data="admin:panel"),
            ],
            [InlineKeyboardButton(text=t(language, "btn_main_menu"), callback_data="menu:home")],
        ]
    )


def admin_menu_keyboard(language: str) -> InlineKeyboardMarkup:
    add_car = InlineKeyboardButton(
        text=t(language, "btn_add_car"), callback_data="admin:add"
    )
    manage_cars = InlineKeyboardButton(
        text=t(language, "btn_manage_cars"), callback_data="admin:cars:0"
    )
    requests = InlineKeyboardButton(
        text=t(language, "btn_manage_requests"), callback_data="admin:requests"
    )
    admins = InlineKeyboardButton(
        text=t(language, "btn_manage_admins"), callback_data="admin:admins"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [add_car, manage_cars],
            [requests, admins],
            [
                InlineKeyboardButton(
                    text=t(language, "btn_stats"), callback_data="admin:stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "btn_main_menu"), callback_data="menu:home"
                )
            ],
        ]
    )


def edit_fields_keyboard(language: str, car_id: int) -> InlineKeyboardMarkup:
    fields = [
        ("make_model", "field_make_model"),
        ("year", "field_year"),
        ("price", "field_price"),
        ("mileage", "field_mileage"),
        ("fuel_type", "field_fuel"),
        ("transmission", "field_transmission"),
        ("description", "field_description"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, label), callback_data=f"admin:editfield:{car_id}:{field}")]
            for field, label in fields
        ]
        + [[InlineKeyboardButton(text=t(language, "btn_back"), callback_data=f"admin:car:{car_id}")]]
    )


def confirmation_keyboard(language: str, yes_callback: str, no_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(language, "btn_confirm_delete"), callback_data=yes_callback),
                InlineKeyboardButton(text=t(language, "btn_keep"), callback_data=no_callback),
            ]
        ]
    )


def done_keyboard(language: str, callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "btn_done"), callback_data=callback)],
            [InlineKeyboardButton(text=t(language, "btn_skip"), callback_data=callback)],
        ]
    )


def request_actions(language: str, request_id: int) -> InlineKeyboardMarkup:
    options = [
        ("confirmed", "status_confirmed"),
        ("completed", "status_completed"),
        ("cancelled", "status_cancelled"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, label),
                    callback_data=f"admin:reqstatus:{request_id}:{status}",
                )
            ]
            for status, label in options
        ]
        + [
            [
                InlineKeyboardButton(text=t(language, "btn_back"), callback_data="admin:requests"),
                InlineKeyboardButton(text=t(language, "btn_admin_menu"), callback_data="admin:panel"),
            ],
            [InlineKeyboardButton(text=t(language, "btn_main_menu"), callback_data="menu:home")],
        ]
    )


def profile_actions(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(language, "btn_favorites"), callback_data="menu:favorites"),
                InlineKeyboardButton(text=t(language, "btn_requests"), callback_data="menu:requests"),
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "btn_business_message"),
                    callback_data="menu:contact",
                ),
                InlineKeyboardButton(text=t(language, "btn_main_menu"), callback_data="menu:home"),
            ],
        ]
    )

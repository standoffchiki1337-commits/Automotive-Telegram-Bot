from __future__ import annotations

import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from automotive_bot.i18n import t

DEALERSHIP_TIMEZONE = ZoneInfo("Europe/Warsaw")


def latest_appointment_date(today: date | None = None) -> date:
    current = today or dealership_today()
    try:
        return current.replace(year=current.year + 1)
    except ValueError:
        # Keep leap-day bookings within the same one-year window.
        return current.replace(year=current.year + 1, day=28)

MONTHS = {
    "ru": (
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
    ),
    "pl": (
        "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
        "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
    ),
    "uk": (
        "січень", "лютий", "березень", "квітень", "травень", "червень",
        "липень", "серпень", "вересень", "жовтень", "листопад", "грудень",
    ),
    "en": (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ),
    "de": (
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ),
}

WEEKDAYS = {
    "ru": ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"),
    "pl": ("Pn", "Wt", "Śr", "Cz", "Pt", "So", "N"),
    "uk": ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"),
    "en": ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"),
    "de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
}


def dealership_today() -> date:
    return datetime.now(DEALERSHIP_TIMEZONE).date()


def appointment_time_is_future(
    selected_date: date,
    hour: int,
    minute: int,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(DEALERSHIP_TIMEZONE)
    chosen = datetime.combine(
        selected_date,
        datetime.min.time().replace(hour=hour, minute=minute),
        tzinfo=DEALERSHIP_TIMEZONE,
    )
    return chosen > current


def appointment_date_keyboard(
    language: str, year: int, month: int, today: date | None = None
) -> InlineKeyboardMarkup:
    today = today or dealership_today()
    latest = latest_appointment_date(today)
    first_month = today.replace(day=1)
    last_month = latest.replace(day=1)
    requested_month = date(year, month, 1)
    if requested_month < first_month:
        requested_month = first_month
    elif requested_month > last_month:
        requested_month = last_month
    year, month = requested_month.year, requested_month.month

    months = MONTHS.get(language, MONTHS["ru"])
    weekdays = WEEKDAYS.get(language, WEEKDAYS["ru"])
    rows = [
        [
            InlineKeyboardButton(
                text=f"{months[month - 1]} {year}",
                callback_data=f"viewing:select-month:{year}:{month}",
            )
        ],
        [
            InlineKeyboardButton(text=day, callback_data="viewing:noop")
            for day in weekdays
        ],
    ]
    for week in calendar.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(
                    InlineKeyboardButton(text="·", callback_data="viewing:noop")
                )
                continue
            chosen = date(year, month, day)
            if today <= chosen <= latest:
                row.append(
                    InlineKeyboardButton(
                        text=f"{day:02d}",
                        callback_data=f"viewing:date:{chosen.isoformat()}",
                    )
                )
            else:
                row.append(
                    InlineKeyboardButton(text="·", callback_data="viewing:noop")
                )
        rows.append(row)

    previous = date(year - 1, 12, 1) if month == 1 else date(year, month - 1, 1)
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    rows.append(
        [
            InlineKeyboardButton(
                text="‹",
                callback_data=(
                    f"viewing:month:{previous.year}:{previous.month}"
                    if previous >= first_month
                    else "viewing:noop"
                ),
            ),
            InlineKeyboardButton(
                text="›",
                callback_data=(
                    f"viewing:month:{following.year}:{following.month}"
                    if following <= last_month
                    else "viewing:noop"
                ),
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=t(language, "btn_cancel"), callback_data="viewing:cancel"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def appointment_month_keyboard(
    language: str,
    year: int,
    selected_month: int,
    today: date | None = None,
) -> InlineKeyboardMarkup:
    today = today or dealership_today()
    first_month = today.replace(day=1)
    last_month = latest_appointment_date(today).replace(day=1)
    year = min(max(year, first_month.year), last_month.year)
    months = MONTHS.get(language, MONTHS["ru"])

    previous_year = year - 1
    following_year = year + 1
    rows = [
        [
            InlineKeyboardButton(
                text="‹",
                callback_data=(
                    f"viewing:year:{previous_year}:{selected_month}"
                    if previous_year >= first_month.year
                    else "viewing:noop"
                ),
            ),
            InlineKeyboardButton(text=str(year), callback_data="viewing:noop"),
            InlineKeyboardButton(
                text="›",
                callback_data=(
                    f"viewing:year:{following_year}:{selected_month}"
                    if following_year <= last_month.year
                    else "viewing:noop"
                ),
            ),
        ]
    ]
    for start in range(1, 13, 3):
        row = []
        for month in range(start, start + 3):
            month_date = date(year, month, 1)
            is_available = first_month <= month_date <= last_month
            row.append(
                InlineKeyboardButton(
                    text=(
                        f"✓ {months[month - 1]}"
                        if month == selected_month
                        else months[month - 1]
                    ),
                    callback_data=(
                        f"viewing:month:{year}:{month}"
                        if is_available
                        else "viewing:noop"
                    ),
                )
            )
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text=t(language, "appointment_back_date"),
                callback_data=f"viewing:calendar:{year}:{selected_month}",
            ),
            InlineKeyboardButton(
                text=t(language, "btn_cancel"), callback_data="viewing:cancel"
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def appointment_hour_keyboard(
    language: str,
    selected_date: date | None = None,
    now: datetime | None = None,
) -> InlineKeyboardMarkup:
    current = now or datetime.now(DEALERSHIP_TIMEZONE)

    def can_choose_hour(hour: int) -> bool:
        return (
            selected_date is None
            or selected_date > current.date()
            or (
                selected_date == current.date()
                and appointment_time_is_future(selected_date, hour, 59, current)
            )
        )

    rows = [
        [
            InlineKeyboardButton(
                text=f"{hour:02d}" if can_choose_hour(hour) else "·",
                callback_data=(
                    f"viewing:hour:{hour:02d}"
                    if can_choose_hour(hour)
                    else "viewing:noop"
                ),
            )
            for hour in range(start, start + 4)
        ]
        for start in range(0, 24, 4)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=t(language, "appointment_back_date"),
                callback_data="viewing:choose-date",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def appointment_minute_keyboard(
    language: str,
    selected_date: date | None = None,
    selected_hour: int | None = None,
    now: datetime | None = None,
) -> InlineKeyboardMarkup:
    current = now or datetime.now(DEALERSHIP_TIMEZONE)
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"{minute:02d}"
                    if selected_date is None
                    or selected_hour is None
                    or appointment_time_is_future(
                        selected_date, selected_hour, minute, current
                    )
                    else "·"
                ),
                callback_data=(
                    f"viewing:minute:{minute:02d}"
                    if selected_date is None
                    or selected_hour is None
                    or appointment_time_is_future(
                        selected_date, selected_hour, minute, current
                    )
                    else "viewing:noop"
                ),
            )
            for minute in range(start, start + 6)
        ]
        for start in range(0, 60, 6)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=t(language, "appointment_back_hour"),
                callback_data="viewing:choose-hour",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def appointment_confirmation_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ {t(language, 'appointment_confirm_button')}",
                    callback_data="viewing:confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "appointment_back_minute"),
                    callback_data="viewing:choose-minute",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "appointment_back_date"),
                    callback_data="viewing:choose-date",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "btn_cancel"),
                    callback_data="viewing:cancel",
                )
            ],
        ]
    )
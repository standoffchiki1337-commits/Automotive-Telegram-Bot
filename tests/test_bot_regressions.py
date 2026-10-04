from datetime import date, datetime
from decimal import Decimal
import unittest
from types import SimpleNamespace

from automotive_bot.appointment_calendar import (
    DEALERSHIP_TIMEZONE,
    appointment_date_keyboard,
    appointment_hour_keyboard,
    appointment_month_keyboard,
    appointment_minute_keyboard,
    appointment_time_is_future,
    latest_appointment_date,
)
from automotive_bot.config import Settings
from automotive_bot.database import create_database, initialize_database
from automotive_bot.i18n import (
    fuel_label,
    selected_fuel_types,
    toggle_fuel_type,
)
from automotive_bot.keyboards import fuel_selection_keyboard
from automotive_bot.models import Car
from automotive_bot.services import money_text
from automotive_bot.handlers.customer import _car_caption
from sqlalchemy import select


class FuelSelectionTests(unittest.TestCase):
    def test_multiple_fuel_types_are_saved_and_displayed(self) -> None:
        selected = toggle_fuel_type((), "petrol")
        selected = toggle_fuel_type(selected, "lpg")

        self.assertEqual(selected, ("petrol", "lpg"))
        self.assertEqual(selected_fuel_types("+".join(selected)), selected)
        self.assertEqual(fuel_label("ru", "+".join(selected)), "Бензин + Газ / LPG")

    def test_fuel_selection_is_capped_at_three_and_can_be_unselected(self) -> None:
        selected = ("petrol", "diesel", "electric")

        with self.assertRaises(ValueError):
            toggle_fuel_type(selected, "hybrid")

        self.assertEqual(toggle_fuel_type(selected, "diesel"), ("petrol", "electric"))

    def test_multiselect_keyboard_has_toggle_and_done_actions(self) -> None:
        keyboard = fuel_selection_keyboard("ru", "admin:addfuel", ["petrol"])
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertIn("admin:addfuel:toggle:petrol", callbacks)
        self.assertIn("admin:addfuel:done", callbacks)

class FuelStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_fuel_types_persist_without_a_schema_change(self) -> None:
        settings = Settings(
            bot_token="test",
            database_url="sqlite+aiosqlite:///:memory:",
            admin_ids=(),
            currency="PLN",
        )
        engine, session_factory = create_database(settings)
        try:
            await initialize_database(engine, session_factory, ())
            async with session_factory() as session:
                car = Car(
                    make_model="Test car",
                    year=2020,
                    price=Decimal("10000"),
                    mileage=50000,
                    fuel_type="diesel+electric+hybrid",
                    transmission="automatic",
                    description="Test listing",
                    status="available",
                    created_by=1,
                )
                session.add(car)
                await session.commit()
                car_id = car.id
            async with session_factory() as session:
                stored = await session.scalar(select(Car).where(Car.id == car_id))
                self.assertIsNotNone(stored)
                self.assertEqual(
                    stored.fuel_type, "diesel+electric+hybrid"
                )
        finally:
            await engine.dispose()


class PriceDisplayTests(unittest.TestCase):
    def test_prices_are_always_displayed_in_polish_zloty(self) -> None:
        self.assertEqual(money_text(Decimal("125000.50"), "EUR"), "125 000,5 zł")
        self.assertNotIn("€", money_text(Decimal("125000.50"), "EUR"))


class CarCaptionTranslationTests(unittest.TestCase):
    def test_translated_description_is_used_and_fallback_is_visible(self) -> None:
        car = SimpleNamespace(
            make_model="Test car",
            status="available",
            price=Decimal("12500"),
            year=2020,
            mileage=50000,
            fuel_type="petrol",
            transmission="automatic",
            description="Исходное описание",
        )

        caption = _car_caption(
            car,
            "de",
            "PLN",
            description_text="Übersetzte Beschreibung",
            translation_available=True,
        )
        self.assertIn("Übersetzte Beschreibung", caption)
        self.assertNotIn("Исходное описание", caption)

        fallback_caption = _car_caption(
            car,
            "de",
            "PLN",
            description_text=car.description,
            translation_available=False,
        )
        self.assertIn("Исходное описание", fallback_caption)
        self.assertIn("Übersetzung vorübergehend nicht verfügbar", fallback_caption)


class AppointmentTimeTests(unittest.TestCase):
    def test_picker_disables_times_that_have_already_passed_today(self) -> None:
        today = date(2026, 10, 4)
        now = datetime(2026, 10, 4, 11, 30, tzinfo=DEALERSHIP_TIMEZONE)
        hours = appointment_hour_keyboard("ru", today, now)
        minutes = appointment_minute_keyboard("ru", today, 11, now)

        hour_buttons = {
            button.callback_data: button.text
            for row in hours.inline_keyboard
            for button in row
        }
        minute_buttons = {
            button.callback_data: button.text
            for row in minutes.inline_keyboard
            for button in row
        }
        self.assertEqual(hour_buttons["viewing:noop"], "·")
        self.assertEqual(minute_buttons["viewing:noop"], "·")
        self.assertNotEqual(minute_buttons["viewing:minute:36"], "·")

    def test_appointment_time_must_be_in_the_future(self) -> None:
        now = datetime(2026, 10, 4, 11, 30, tzinfo=DEALERSHIP_TIMEZONE)

        self.assertFalse(appointment_time_is_future(date(2026, 10, 4), 11, 30, now))
        self.assertTrue(appointment_time_is_future(date(2026, 10, 4), 11, 36, now))

    def test_calendar_supports_direct_month_and_year_selection(self) -> None:
        today = date(2026, 10, 4)
        calendar_keyboard = appointment_date_keyboard("ru", 2026, 10, today)
        month_button = calendar_keyboard.inline_keyboard[0][0]
        self.assertEqual(month_button.callback_data, "viewing:select-month:2026:10")

        picker = appointment_month_keyboard("de", 2027, 10, today)
        callbacks = {
            button.callback_data
            for row in picker.inline_keyboard
            for button in row
        }
        self.assertIn("viewing:month:2027:3", callbacks)
        self.assertIn("viewing:year:2026:10", callbacks)
        self.assertIn("viewing:calendar:2027:10", callbacks)

    def test_appointment_horizon_is_one_calendar_year_including_leap_day(self) -> None:
        self.assertEqual(
            latest_appointment_date(date(2026, 10, 4)), date(2027, 10, 4)
        )
        self.assertEqual(
            latest_appointment_date(date(2024, 2, 29)), date(2025, 2, 28)
        )


if __name__ == "__main__":
    unittest.main()
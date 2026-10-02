from aiogram.fsm.state import State, StatesGroup


class CustomerSearch(StatesGroup):
    term = State()
    fuel = State()
    transmission = State()
    year_min = State()
    price_max = State()


class ViewingRequestFlow(StatesGroup):
    preferred_time = State()
    message = State()


class ContactFlow(StatesGroup):
    message = State()


class AddCarFlow(StatesGroup):
    make_model = State()
    year = State()
    price = State()
    mileage = State()
    fuel = State()
    transmission = State()
    description = State()
    photos = State()


class EditCarFlow(StatesGroup):
    value = State()
    photos = State()


class AdministratorFlow(StatesGroup):
    add_id = State()
    remove_id = State()

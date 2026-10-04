# Automotive Telegram Bot

An aiogram 3 bot for an automotive business. Customers can find vehicles, save favorites, contact the business, and request viewings. Administrators can manage inventory, photos, request statuses, and administrator access.

## Features

- Russian, Polish, Ukrainian, English, and German menus and customer flows
- Vehicle catalog with search by make/model or description, plus fuel, transmission, year, and price filters
- Compact single-message listing cards with price, mileage, year, fuel type, transmission, description, status badge, and photo navigation
- Customer favorites and viewing-request history
- Listing contact buttons open the Telegram account of the administrator who added the vehicle
- Bot contact messages and viewing requests reach administrators with a clickable customer Telegram profile
- Administrator tools for listing creation, editing, deletion, inventory status, and photos
- Viewing request management with administrator notifications and customer status updates
- Persistent SQLAlchemy storage using SQLite by default; PostgreSQL is supported through `DATABASE_URL`

## Run in Replit

1. Set the Telegram token as a Replit Secret named `BOT_TOKEN`. Do not place the real token in source code.
2. Add the Telegram numeric ID of the first administrator through `ADMIN_IDS`, or run the bootstrap command below.
3. To translate vehicle descriptions, enable Cloud Translation in Google Cloud and add `GOOGLE_TRANSLATE_API_KEY` to the Railway service variables. Restrict the key to the Cloud Translation API. The key is optional; without it, descriptions remain in their original language and the bot says translation is unavailable.
4. Start the **Automotive Telegram Bot** workflow.

If an administrator is added via `ADMIN_IDS`, the bot creates that administrator record on startup. Remove that ID from `ADMIN_IDS` after setup if you want subsequent removal from the in-bot administrator menu to remain permanent.

## Deploy on Railway

`railpack.json` configures a single Python service from the repository root and starts the Telegram bot with `uv`. In Railway, use the repository root (`/`) as the service's root directory; do not deploy the individual JavaScript workspace packages as bot services.

1. Create or select one Railway service connected to this repository, using the repository root as its root directory.
2. Add `BOT_TOKEN` in that service's Variables. Optionally add `ADMIN_IDS` and `GOOGLE_TRANSLATE_API_KEY`.
3. Attach a Railway Volume to the service at `/app/data` to keep the default SQLite database across redeploys. Leave `DATABASE_URL` unset to use SQLite.
4. Keep one running replica: Telegram long polling should not run in multiple instances with the same bot token.

Railway's automatic import for JavaScript workspaces can create extra services for packages such as `api-spec` and `api-client-react`. The repository configuration cannot remove services already created in Railway. Keep the root Python bot service and remove unused package services in Railway's project view only after confirming they have no data or volumes you need.

## Run locally

Python 3.11+ and `uv` are used by the project.

```sh
cp .env.example .env
# Set BOT_TOKEN in .env and optionally set ADMIN_IDS.
uv run --env-file .env python -m automotive_bot.main
```

To create the first administrator in the configured database:

```sh
uv run --env-file .env python -m automotive_bot.bootstrap_admin 123456789
```

Replace the example with the administrator's numeric Telegram user ID. The bot must be started by each administrator in Telegram before it can send them notifications.

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `BOT_TOKEN` | Yes | Telegram bot token. Store as a Replit Secret or local environment variable. |
| `DATABASE_URL` | No | Defaults to `sqlite+aiosqlite:///./data/automotive.db`; accepts PostgreSQL URLs as well. |
| `ADMIN_IDS` | No | Comma-separated initial administrator Telegram IDs, for example `123456789,987654321`. |
| `GOOGLE_TRANSLATE_API_KEY` | No | Google Cloud Translation API key. Descriptions are translated to each customer's selected language; without a key, the original is shown with a notice. |

SQLite data is stored in `data/automotive.db`. For hosted PostgreSQL, set `DATABASE_URL` to the managed database URL. The database schema is initialized when the bot starts.
Prices are displayed in Polish złoty (`zł`).

## Customer controls

Use `/start` to choose a language before opening the menu. Main-menu buttons remain usable during an active prompt and take the user to the selected section. The **Contact seller** button on a vehicle listing opens the primary bot administrator's Telegram account. Customers can browse available vehicles, filter the catalog, save favorites, request an appointment, review their own requests, or send a message to the business.

## Administrator controls

Open the administrator panel from the menu. Administrator access is stored in the database. The first administrator can be seeded with `ADMIN_IDS` or `automotive_bot.bootstrap_admin`; administrators can then add or remove other administrators from the bot.

The vehicle **Contact seller** button opens the earliest active administrator's Telegram account. If that administrator is removed, the next active administrator becomes the contact.

When adding photos, send up to 10 photos one at a time or as an album and finish with the **Done** button. Photos are referenced by their Telegram file IDs rather than copied into the database.

## Project layout

```text
automotive_bot/
  config.py             Environment-based configuration
  database.py           Async engine and schema initialization
  models.py             Users, administrators, cars, photos, favorites, requests
  i18n.py               Russian, Polish, Ukrainian, English, and German strings
  keyboards.py          Telegram menus and inline keyboards
  states.py             Customer and administrator conversation states
  handlers/
    customer.py         Customer catalog, search, favorites, contact, appointments
    admin.py            Inventory, request, and administrator management
  main.py               Polling entry point
  bootstrap_admin.py    First-administrator setup command
```

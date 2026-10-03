# Automotive Telegram Bot

A multilingual Telegram bot for browsing vehicle listings, managing favorites and viewing requests, and administering an automotive inventory.

## Run & Operate

- Start the **Automotive Telegram Bot** workflow — run the Telegram long-polling service
- `uv run python -m automotive_bot.main` — run the bot locally
- `uv run python -m automotive_bot.bootstrap_admin <TELEGRAM_ID>` — add the first administrator
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required env: `BOT_TOKEN` (Replit Secret)
- Optional env: `DATABASE_URL`, `ADMIN_IDS`, `CURRENCY`

## Stack

- Python 3.11, aiogram 3, SQLAlchemy async
- SQLite by default; PostgreSQL supported through `DATABASE_URL`
- Existing workspace tooling: pnpm, TypeScript, Express API, and Drizzle

## Where things live

- `automotive_bot/handlers/customer.py` — catalog, search, favorites, appointments, and contact
- `automotive_bot/handlers/admin.py` — listings, photos, viewing requests, and administrator management
- `automotive_bot/models.py` — persistent data model
- `automotive_bot/i18n.py` — Russian, Polish, Ukrainian, English, and German bot text
- `README.md` — configuration and run instructions

## Architecture decisions

- Telegram long polling avoids requiring a public webhook endpoint.
- Vehicle photos are referenced by Telegram file IDs rather than duplicated in the database.
- Listing contact buttons open the Telegram account that created the listing; use its username when available and fall back to its Telegram user ID.
- SQLite is the no-configuration development default; PostgreSQL works through `DATABASE_URL`.
- First-admin access is explicitly bootstrapped by the project owner or an existing administrator, never assigned to an arbitrary first user.

## Product

- Customers can browse/filter vehicles, save favorites, request viewings, contact the business, and review their own saved items and requests.
- Administrators can manage vehicle inventory, photos, request statuses, and administrator access.

## User preferences

- Keep `BOT_TOKEN` in an environment secret, never in source code.

## Gotchas

- Administrators must open the bot in Telegram before it can send private notifications to them.
- `ADMIN_IDS` are re-seeded into the database on startup; remove an ID from the environment after bootstrapping if in-bot removal should persist.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details

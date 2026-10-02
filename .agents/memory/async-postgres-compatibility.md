---
name: Async PostgreSQL compatibility
description: Replit PostgreSQL URL options and SQLAlchemy async driver requirements.
---

**Rule:** When this bot uses SQLAlchemy's asyncpg driver with Replit's injected PostgreSQL URL, translate libpq `sslmode` to asyncpg's `ssl` option and remove unsupported `channel_binding`. Include SQLAlchemy's `asyncio` extra.

**Why:** Without URL normalization, asyncpg receives an unsupported `sslmode` argument; without the extra, SQLAlchemy async fails because `greenlet` is missing.

**How to apply:** Keep the URL adaptation and SQLAlchemy dependency extra together if the database driver or package declaration changes. Never log the database URL.
---
name: Automotive bot scope
description: Standing scope constraints and the seller identity assumption for changes to the automotive Telegram bot.
---

Keep this project as the existing aiogram Telegram bot. Preserve customer and administrator flows, PostgreSQL support, long polling, and persistent data. Do not add web apps, paid services, AI features, dependencies, deployments, or extra services without an explicit request.

Бот работает у пользователя на Railway; здесь агент меняет код, а не настраивает запуск на Replit.

**Why:** Пользователь сказал: «Я бота держу на рейл вее а ты меняешь код».

**How to apply:** Работать над запрошенными изменениями кода; не запускать и не настраивать бот на Replit без отдельного запроса.

**Why:** The owner set these constraints as the expected scope for work on this project.

**How to apply:** Prefer changes within the existing bot and stack. Ask before broadening the project or changing stored-data behavior.

For Railway, use one service built from the repository root to run the Python bot. Do not deploy the JavaScript workspace packages as separate Railway services.

**Why:** The owner explicitly requested a single Railway bot service instead of multiple services created by JavaScript monorepo auto-import.

**How to apply:** Keep Railway build and start configuration targeted at the root Python bot; do not delete existing Railway services without checking their data and volumes.

For listing contact, open the primary bot administrator's Telegram account. Link to its public username when available and fall back to its Telegram user ID when not.

**Why:** The owner explicitly requested listing inquiries go to the bot administrator's account rather than the listing creator.

**How to apply:** Select the earliest active administrator as the primary contact; if that administrator is removed, use the next active administrator.

Translate vehicle descriptions into the customer's selected bot language using Google Cloud Translation, while preserving the stored original. Configure the Google API key on Railway, not in source code.

**Why:** The owner requested that Russian or Ukrainian listings display in the customer's chosen language, including German, and selected Google Cloud Translation for the integration.

**How to apply:** Keep source descriptions unchanged, translate when rendering car cards (including photo navigation), cache successful results, and show the original with a clear notice if translation is unavailable.

Main-menu buttons must work from any active conversation flow; customers and admins should not need `/start` just to navigate away from a prompt.

**Why:** The owner reported that pressing buttons during bot flows could leave users needing to restart the bot.

**How to apply:** Treat home-keyboard selections as navigation, clear the current FSM state before dispatching the chosen action, and keep inline return buttons clearing state too.
---
name: Automotive bot scope
description: Standing scope constraints and the seller identity assumption for changes to the automotive Telegram bot.
---

Keep this project as the existing aiogram Telegram bot. Preserve customer and administrator flows, PostgreSQL support, long polling, and persistent data. Do not add web apps, paid services, AI features, dependencies, deployments, or extra services without an explicit request.

**Why:** The owner set these constraints as the expected scope for work on this project.

**How to apply:** Prefer changes within the existing bot and stack. Ask before broadening the project or changing stored-data behavior.

For listing contact, use the Telegram account that created the listing. Link to its public username when available and fall back to its Telegram user ID when not.

**Why:** This uses existing listing ownership without adding a separate seller-handle setting. The owner has not separately confirmed that the creator is always the intended seller.

**How to apply:** Reuse this behavior for listing-level contact unless the owner specifies a different seller identity model.
---
name: Argos offline dependency size
description: Why this bot pins the upstream Argos source instead of using the older PyPI release.
---

Use the pinned upstream Argos source revision for offline translation. The older PyPI release makes Stanza mandatory, which pulls in PyTorch and CUDA packages that greatly increase the bot image.

**Why:** A package installation added several gigabytes of unnecessary dependencies to the development environment and would make the Railway image impractical.

**How to apply:** Before changing the Argos source pin or package extras, inspect the resolved dependency tree and keep translation CPU-only with Stanza optional.

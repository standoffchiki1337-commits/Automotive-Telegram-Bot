from __future__ import annotations

import logging

from automotive_bot.translation import install_required_translation_models


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    install_required_translation_models()
    logging.getLogger(__name__).info("Offline Argos translation models are ready.")


if __name__ == "__main__":
    main()

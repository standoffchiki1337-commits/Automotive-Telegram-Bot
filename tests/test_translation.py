from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from automotive_bot.translation import (
    REQUIRED_MODEL_PAIRS,
    _translation_cache,
    install_required_translation_models,
    translate_description,
)


class TranslationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _translation_cache.clear()

    async def test_translation_detects_ukrainian_and_caches_result(self) -> None:
        description = "Гарний автомобіль у відмінному стані"
        with patch(
            "automotive_bot.translation._translate_with_argos",
            return_value="Ein gepflegtes Auto",
        ) as translate:
            first = await translate_description(description, "de")
            cached = await translate_description(description, "de")

        self.assertEqual(first, ("Ein gepflegtes Auto", True))
        self.assertEqual(cached, first)
        translate.assert_called_once_with(description, "uk", "de")

    async def test_translation_detects_russian_source(self) -> None:
        description = "Автомобиль в хорошем состоянии"
        with patch(
            "automotive_bot.translation._translate_with_argos",
            return_value="A car in good condition",
        ) as translate:
            result = await translate_description(description, "en")

        self.assertEqual(result, ("A car in good condition", True))
        translate.assert_called_once_with(description, "ru", "en")

    async def test_same_language_does_not_call_translation_model(self) -> None:
        description = "Автомобиль в хорошем состоянии"
        with patch("automotive_bot.translation._translate_with_argos") as translate:
            result = await translate_description(description, "ru")

        self.assertEqual(result, (description, True))
        translate.assert_not_called()

    async def test_missing_model_keeps_original_description(self) -> None:
        description = "Автомобиль в хорошем состоянии"
        with patch(
            "automotive_bot.translation._translate_with_argos",
            side_effect=RuntimeError("model unavailable"),
        ):
            result = await translate_description(description, "de")

        self.assertEqual(result, (description, False))

    async def test_empty_description_does_not_load_models(self) -> None:
        with patch("automotive_bot.translation._translate_with_argos") as translate:
            result = await translate_description(" — ", "de")

        self.assertEqual(result, ("—", True))
        translate.assert_not_called()

    def test_model_installer_installs_every_required_pair(self) -> None:
        models = {
            pair: SimpleNamespace(from_code=pair[0], to_code=pair[1], install=Mock())
            for pair in REQUIRED_MODEL_PAIRS
        }
        installed = [
            SimpleNamespace(from_code=source, to_code=target)
            for source, target in REQUIRED_MODEL_PAIRS
        ]
        with (
            patch(
                "argostranslate.package.get_installed_packages",
                side_effect=[[], installed],
            ),
            patch("argostranslate.package.update_package_index"),
            patch(
                "argostranslate.package.get_available_packages",
                return_value=list(models.values()),
            ),
        ):
            install_required_translation_models()

        for model in models.values():
            model.install.assert_called_once()


if __name__ == "__main__":
    unittest.main()

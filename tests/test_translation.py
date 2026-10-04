from __future__ import annotations

import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from automotive_bot.translation import translate_description


class _Response:
    def __init__(self, body: dict) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class TranslationTests(unittest.IsolatedAsyncioTestCase):
    async def test_translation_detects_source_and_caches_result(self) -> None:
        response = _Response(
            {
                "data": {
                    "translations": [
                        {
                            "detectedSourceLanguage": "uk",
                            "translatedText": "A reliable car",
                        }
                    ]
                }
            }
        )
        description = "Ухоженный автомобиль"
        with patch("automotive_bot.translation.urlopen", return_value=response) as call:
            translated = await translate_description(
                description, "de", "unit-test-key"
            )
            cached = await translate_description(
                description, "de", "unit-test-key"
            )

        self.assertEqual(translated, ("A reliable car", True))
        self.assertEqual(cached, translated)
        self.assertEqual(call.call_count, 1)
        request = call.call_args.args[0]
        self.assertEqual(parse_qs(urlsplit(request.full_url).query)["key"], ["unit-test-key"])
        payload = json.loads(request.data)
        self.assertEqual(payload["q"], description)
        self.assertEqual(payload["target"], "de")
        self.assertNotIn("source", payload)

    async def test_missing_api_key_keeps_original_description(self) -> None:
        with patch("automotive_bot.translation.urlopen") as call:
            result = await translate_description(
                "Автомобиль в хорошем состоянии", "de", ""
            )

        self.assertEqual(result, ("Автомобиль в хорошем состоянии", False))
        call.assert_not_called()

    async def test_api_error_keeps_original_description(self) -> None:
        description = "Автомобиль в хорошем состоянии"
        with patch(
            "automotive_bot.translation.urlopen",
            side_effect=OSError("API unavailable"),
        ):
            result = await translate_description(
                description, "de", "another-unit-test-key"
            )

        self.assertEqual(result, (description, False))


if __name__ == "__main__":
    unittest.main()
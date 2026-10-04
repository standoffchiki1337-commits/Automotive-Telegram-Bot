from __future__ import annotations

import asyncio
from collections import OrderedDict
import html
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

GOOGLE_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"
MAX_CACHED_TRANSLATIONS = 512
_translation_cache: OrderedDict[tuple[str, str], str] = OrderedDict()


def _translate_with_google(
    text: str, target_language: str, api_key: str
) -> str:
    query = urlencode({"key": api_key})
    request = Request(
        f"{GOOGLE_TRANSLATE_URL}?{query}",
        data=json.dumps(
            {"q": text, "target": target_language, "format": "text"}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    translated = payload["data"]["translations"][0]["translatedText"]
    if not isinstance(translated, str) or not translated.strip():
        raise ValueError("Google Cloud Translation returned no translated text.")
    return html.unescape(translated)


async def translate_description(
    text: str, target_language: str, api_key: str
) -> tuple[str, bool]:
    """Return translated description and whether translation succeeded."""
    original = text.strip()
    if not original or original == "—":
        return original or "—", True
    if not api_key:
        return original, False

    cache_key = (original, target_language)
    cached = _translation_cache.get(cache_key)
    if cached is not None:
        _translation_cache.move_to_end(cache_key)
        return cached, True

    try:
        translated = await asyncio.to_thread(
            _translate_with_google, original, target_language, api_key
        )
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
    ):
        # Do not include exception details: HTTP errors can contain the API key URL.
        logger.warning("Google Cloud Translation request failed.")
        return original, False

    _translation_cache[cache_key] = translated
    _translation_cache.move_to_end(cache_key)
    while len(_translation_cache) > MAX_CACHED_TRANSLATIONS:
        _translation_cache.popitem(last=False)
    return translated, True
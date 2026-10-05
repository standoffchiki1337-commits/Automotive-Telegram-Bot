from __future__ import annotations

import asyncio
from collections import OrderedDict
import logging
import os
from pathlib import Path

from langid import classify

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("ARGOS_PACKAGES_DIR", str(_PROJECT_ROOT / "argos-packages"))
os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")

REQUIRED_MODEL_PAIRS = (
    ("ru", "en"),
    ("en", "ru"),
    ("uk", "en"),
    ("en", "uk"),
    ("pl", "en"),
    ("en", "pl"),
    ("de", "en"),
    ("en", "de"),
)
SUPPORTED_LANGUAGES = frozenset({"ru", "pl", "uk", "en", "de"})
UKRAINIAN_LETTERS = frozenset("іїєґ")
RUSSIAN_LETTERS = frozenset("ыъэё")
MAX_CACHED_TRANSLATIONS = 512
_translation_cache: OrderedDict[tuple[str, str], str] = OrderedDict()


def install_required_translation_models() -> None:
    """Install the free Argos models needed for all bot languages."""
    Path(os.environ["ARGOS_PACKAGES_DIR"]).mkdir(parents=True, exist_ok=True)
    from argostranslate import package

    installed = {
        (model.from_code, model.to_code)
        for model in package.get_installed_packages()
        if model.from_code and model.to_code
    }
    missing = set(REQUIRED_MODEL_PAIRS) - installed
    if not missing:
        return

    package.update_package_index()
    available = {
        (model.from_code, model.to_code): model
        for model in package.get_available_packages()
        if model.from_code and model.to_code
    }
    for source, target in REQUIRED_MODEL_PAIRS:
        pair = (source, target)
        if pair not in missing:
            continue
        model = available.get(pair)
        if model is None:
            raise RuntimeError(
                f"No Argos model is available for {source} -> {target}."
            )
        logger.info("Installing offline Argos model %s -> %s.", source, target)
        model.install()

    installed = {
        (model.from_code, model.to_code)
        for model in package.get_installed_packages()
        if model.from_code and model.to_code
    }
    missing = set(REQUIRED_MODEL_PAIRS) - installed
    if missing:
        pairs = ", ".join(f"{source}->{target}" for source, target in sorted(missing))
        raise RuntimeError(f"Argos translation models were not installed: {pairs}.")


def _detect_source_language(text: str) -> str:
    lowered = text.casefold()
    ukrainian_count = sum(character in UKRAINIAN_LETTERS for character in lowered)
    russian_count = sum(character in RUSSIAN_LETTERS for character in lowered)
    if ukrainian_count > russian_count:
        return "uk"
    if russian_count > ukrainian_count:
        return "ru"

    try:
        detected, _score = classify(text)
    except Exception:
        detected = "ru"
    return detected if detected in SUPPORTED_LANGUAGES else "ru"


def _translate_with_argos(text: str, source: str, target: str) -> str:
    from argostranslate import translate

    languages = {
        language.code: language for language in translate.get_installed_languages()
    }
    source_language = languages.get(source)
    target_language = languages.get(target)
    if source_language is None or target_language is None:
        raise RuntimeError("Required Argos language model is not installed.")

    translation = source_language.get_translation(target_language)
    if translation is None:
        raise RuntimeError(f"No Argos route is available for {source} -> {target}.")
    translated = translation.translate(text)
    if not isinstance(translated, str) or not translated.strip():
        raise RuntimeError("Argos returned an empty translation.")
    return translated


async def translate_description(
    text: str, target_language: str
) -> tuple[str, bool]:
    """Return an offline translation and whether translation succeeded."""
    original = text.strip()
    if not original or original == "—":
        return original or "—", True
    if target_language not in SUPPORTED_LANGUAGES:
        return original, False

    source_language = _detect_source_language(original)
    if source_language == target_language:
        return original, True

    cache_key = (original, target_language)
    cached = _translation_cache.get(cache_key)
    if cached is not None:
        _translation_cache.move_to_end(cache_key)
        return cached, True

    try:
        translated = await asyncio.to_thread(
            _translate_with_argos, original, source_language, target_language
        )
    except Exception as exc:
        logger.warning(
            "Offline Argos translation failed for %s -> %s (%s).",
            source_language,
            target_language,
            type(exc).__name__,
        )
        return original, False

    _translation_cache[cache_key] = translated
    _translation_cache.move_to_end(cache_key)
    while len(_translation_cache) > MAX_CACHED_TRANSLATIONS:
        _translation_cache.popitem(last=False)
    return translated, True

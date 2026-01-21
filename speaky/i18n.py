import locale
from pathlib import Path
from typing import Dict

import yaml

from .paths import get_locales_path

# Supported languages
SUPPORTED_LANGUAGES = ["en", "zh", "zh_TW", "ja", "ko", "de", "fr", "es", "pt", "ru"]


class I18n:
    def __init__(self):
        self._current_lang = "auto"
        self._system_lang = self._detect_system_language()
        self._translations: Dict[str, Dict[str, str]] = {}
        self._load_translations()

    def _get_locales_dir(self) -> Path:
        """Get the locales directory path"""
        return get_locales_path()

    def _load_translations(self):
        """Load all translation files from locales directory"""
        locales_dir = self._get_locales_dir()
        for lang in SUPPORTED_LANGUAGES:
            lang_file = locales_dir / f"{lang}.yaml"
            if lang_file.exists():
                with open(lang_file, "r", encoding="utf-8") as f:
                    self._translations[lang] = yaml.safe_load(f) or {}

    def _detect_system_language(self) -> str:
        """Detect system language from locale"""
        try:
            lang, _ = locale.getdefaultlocale()
            if lang:
                lang_lower = lang.lower()
                # Check for Traditional Chinese first
                if lang_lower.startswith("zh") and ("tw" in lang_lower or "hk" in lang_lower or "hant" in lang_lower):
                    return "zh_TW"
                elif lang_lower.startswith("zh"):
                    return "zh"
                elif lang_lower.startswith("ja"):
                    return "ja"
                elif lang_lower.startswith("ko"):
                    return "ko"
                elif lang_lower.startswith("de"):
                    return "de"
                elif lang_lower.startswith("fr"):
                    return "fr"
                elif lang_lower.startswith("es"):
                    return "es"
                elif lang_lower.startswith("pt"):
                    return "pt"
                elif lang_lower.startswith("ru"):
                    return "ru"
                elif lang_lower.startswith("en"):
                    return "en"
        except Exception:
            pass
        return "en"

    def set_language(self, lang: str):
        """Set current UI language"""
        self._current_lang = lang

    @property
    def current_language(self) -> str:
        """Get effective current language"""
        if self._current_lang == "auto":
            return self._system_lang
        return self._current_lang

    def t(self, key: str, **kwargs) -> str:
        """Get translation for key with optional format arguments"""
        lang = self.current_language
        translations = self._translations.get(lang, {})
        fallback = self._translations.get("en", {})
        text = translations.get(key) or fallback.get(key) or key
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass
        return text

    def get_language_name(self, lang_code: str) -> str:
        """Get display name for a language code in current language"""
        return self.t(f"lang_name_{lang_code}")


# Global instance
i18n = I18n()


def t(key: str, **kwargs) -> str:
    """Shortcut for i18n.t()"""
    return i18n.t(key, **kwargs)

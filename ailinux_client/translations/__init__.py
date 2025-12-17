"""
AILinux Client Translations
===========================

Internationalization support for German, English, French, Spanish.
"""
import json
import os
import locale
from pathlib import Path
from typing import Dict, Optional

# Supported languages
SUPPORTED_LANGUAGES = {
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español"
}

# Default language
DEFAULT_LANGUAGE = "en"

# Global translator instance
_translator: Optional["Translator"] = None


class Translator:
    """Simple JSON-based translator for the AILinux Client"""

    def __init__(self, language: str = None):
        self.translations_dir = Path(__file__).parent
        self.current_language = language or self._detect_language()
        self.translations: Dict[str, str] = {}
        self._load_translations()

    def _detect_language(self) -> str:
        """Detect system language"""
        try:
            # Try to get system locale
            lang = locale.getdefaultlocale()[0]
            if lang:
                lang_code = lang.split("_")[0].lower()
                if lang_code in SUPPORTED_LANGUAGES:
                    return lang_code
        except:
            pass

        # Check environment variables
        for env_var in ["LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES"]:
            lang = os.environ.get(env_var, "")
            if lang:
                lang_code = lang.split("_")[0].split(".")[0].lower()
                if lang_code in SUPPORTED_LANGUAGES:
                    return lang_code

        return DEFAULT_LANGUAGE

    def _load_translations(self):
        """Load translations for current language"""
        # English is the base - no translation needed
        if self.current_language == "en":
            self.translations = {}
            return

        translation_file = self.translations_dir / f"{self.current_language}.json"
        if translation_file.exists():
            try:
                with open(translation_file, "r", encoding="utf-8") as f:
                    self.translations = json.load(f)
            except Exception as e:
                print(f"Error loading translations: {e}")
                self.translations = {}
        else:
            self.translations = {}

    def set_language(self, language: str):
        """Change current language"""
        if language in SUPPORTED_LANGUAGES:
            self.current_language = language
            self._load_translations()

    def tr(self, text: str, **kwargs) -> str:
        """Translate text - returns original if no translation found"""
        translated = self.translations.get(text, text)
        # Support format placeholders
        if kwargs:
            try:
                translated = translated.format(**kwargs)
            except:
                pass
        return translated

    def get_available_languages(self) -> Dict[str, str]:
        """Return available languages"""
        return SUPPORTED_LANGUAGES.copy()


def get_translator() -> Translator:
    """Get or create global translator instance"""
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def tr(text: str, **kwargs) -> str:
    """Convenience function for translation"""
    return get_translator().tr(text, **kwargs)


def set_language(language: str):
    """Set application language"""
    get_translator().set_language(language)


def get_current_language() -> str:
    """Get current language code"""
    return get_translator().current_language

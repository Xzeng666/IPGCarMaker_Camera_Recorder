from __future__ import annotations

import string
import unittest

from carmaker_gui.i18n import (
    LANGUAGE_SETTING_KEY,
    TRANSLATIONS,
    LanguageManager,
    detect_system_language,
    resolve_initial_language,
)


class FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.sync_count = 0

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):  # noqa: N802 - mirrors QSettings
        self.values[key] = value

    def sync(self):
        self.sync_count += 1


class LanguageResolutionTests(unittest.TestCase):
    def test_first_launch_uses_chinese_system_locale(self):
        self.assertEqual(detect_system_language("zh_CN"), "zh")
        self.assertEqual(resolve_initial_language(None, "zh-Hans-CN"), "zh")

    def test_first_launch_defaults_to_english_for_other_locales(self):
        self.assertEqual(detect_system_language("en_US"), "en")
        self.assertEqual(detect_system_language("de_DE"), "en")
        self.assertEqual(detect_system_language(None), "en")

    def test_saved_language_overrides_system_locale(self):
        self.assertEqual(resolve_initial_language("en", "zh_CN"), "en")
        self.assertEqual(resolve_initial_language("zh", "en_US"), "zh")

    def test_invalid_saved_value_falls_back_to_system_locale(self):
        self.assertEqual(resolve_initial_language("fr", "zh_CN"), "zh")


class LanguageManagerTests(unittest.TestCase):
    def test_detected_language_is_persisted_on_first_launch(self):
        settings = FakeSettings()
        manager = LanguageManager(settings, "zh_CN")
        self.assertEqual(manager.language, "zh")
        self.assertEqual(settings.values[LANGUAGE_SETTING_KEY], "zh")
        self.assertEqual(settings.sync_count, 1)

    def test_changed_language_is_restored_by_next_manager(self):
        settings = FakeSettings()
        first = LanguageManager(settings, "en_US")
        self.assertTrue(first.set_language("zh"))
        second = LanguageManager(settings, "en_US")
        self.assertEqual(second.language, "zh")

    def test_switching_to_current_language_is_still_persisted(self):
        settings = FakeSettings({LANGUAGE_SETTING_KEY: "en"})
        manager = LanguageManager(settings, "zh_CN")
        self.assertFalse(manager.set_language("en"))
        self.assertEqual(settings.values[LANGUAGE_SETTING_KEY], "en")

    def test_translation_catalogs_have_matching_keys_and_placeholders(self):
        english = TRANSLATIONS["en"]
        chinese = TRANSLATIONS["zh"]
        self.assertEqual(set(english), set(chinese))
        formatter = string.Formatter()
        for key in english:
            english_fields = {
                name for _, name, _, _ in formatter.parse(english[key]) if name
            }
            chinese_fields = {
                name for _, name, _, _ in formatter.parse(chinese[key]) if name
            }
            self.assertEqual(english_fields, chinese_fields, key)
            self.assertTrue(english[key].strip(), key)
            self.assertTrue(chinese[key].strip(), key)


if __name__ == "__main__":
    unittest.main()

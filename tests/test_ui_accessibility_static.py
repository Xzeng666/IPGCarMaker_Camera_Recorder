from __future__ import annotations

import unittest

from carmaker_gui.theme import COLORS


def _luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    rgb = [int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def channel(v: float) -> float:
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = [channel(v) for v in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    l1, l2 = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


class UiAccessibilityStaticTests(unittest.TestCase):
    def test_main_text_contrast(self):
        self.assertGreaterEqual(_contrast(COLORS["text"], COLORS["bg"]), 4.5)
        self.assertGreaterEqual(_contrast(COLORS["text"], COLORS["panel"]), 4.5)

    def test_muted_text_contrast(self):
        self.assertGreaterEqual(_contrast(COLORS["muted"], COLORS["bg"]), 4.5)
        self.assertGreaterEqual(_contrast(COLORS["muted"], COLORS["panel"]), 4.5)

    def test_primary_button_contrast(self):
        self.assertGreaterEqual(_contrast("#FFFFFF", COLORS["accent"]), 4.5)


if __name__ == "__main__":
    unittest.main()

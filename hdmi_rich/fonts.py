"""
TTF font loader for the rich UI.

Ships a single OFL-licensed mono/CRT-style TTF (VT323) at fixed pixel
sizes.  All widgets pick from Fonts.tiny/small/medium/large/xlarge - if a
widget wants a bespoke size it can call Fonts.at(size), but standardised
sizes keep the visual language coherent.
"""

from __future__ import annotations

import os

_FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
FONT_PATH = os.path.join(_FONT_DIR, "VT323-Regular.ttf")


class Fonts:
    """Lazy pygame font loader.  Call once after pygame.init()."""

    def __init__(self):
        import pygame

        pygame.font.init()
        self.tiny = pygame.font.Font(FONT_PATH, 22)
        self.small = pygame.font.Font(FONT_PATH, 32)
        self.medium = pygame.font.Font(FONT_PATH, 48)
        self.large = pygame.font.Font(FONT_PATH, 72)
        self.xlarge = pygame.font.Font(FONT_PATH, 120)
        self._cache: dict[int, "pygame.font.Font"] = {}

    def at(self, size: int):
        import pygame

        f = self._cache.get(size)
        if f is None:
            f = pygame.font.Font(FONT_PATH, size)
            self._cache[size] = f
        return f

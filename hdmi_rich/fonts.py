"""
TTF font loader for the rich UI.

Ships a single OFL-licensed mono/CRT-style TTF (VT323) at named tiers
(tiny / small / medium / large / xlarge / xxlarge).  Every tier is a
CachedFont wrapper: repeated (text, colour) renders return a cached
surface converted to the display's pixel format, so subsequent blits
are ~5x faster than raw font.render().  The cache is bounded so a
runaway pathological input can't grow the process forever.
"""

from __future__ import annotations

import os

_FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
FONT_PATH = os.path.join(_FONT_DIR, "VT323-Regular.ttf")

_CACHE_HARD_CAP = 2048   # per-tier entry cap; well above every-screen worst case


class CachedFont:
    """Drop-in replacement for pygame.font.Font that memoises .render()."""

    def __init__(self, font):
        self._font = font
        self._cache: dict = {}

    def render(self, text, antialias, colour):
        # Normalise colour to a tuple so lookup is stable across list/Colour inputs.
        c = tuple(colour) if not isinstance(colour, tuple) else colour
        key = (text, bool(antialias), c)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        surf = self._font.render(text, antialias, colour)
        # Convert to display pixel format so future blits use fast paths.
        # Guard against being called before pygame.display.set_mode() (rare;
        # only relevant for the loading scene's first frame before we set up
        # the display surface).
        try:
            surf = surf.convert_alpha()
        except Exception:
            pass
        if len(self._cache) < _CACHE_HARD_CAP:
            self._cache[key] = surf
        return surf

    # Pass-through for any font metric a widget might reach for.
    def get_height(self):
        return self._font.get_height()

    def size(self, text):
        return self._font.size(text)


class Fonts:
    """Named-tier font accessor.  Instantiate once after pygame.display init."""

    def __init__(self):
        import pygame

        pygame.font.init()
        from hdmi_rich.screen import s

        self.tiny = CachedFont(pygame.font.Font(FONT_PATH, s(34)))
        self.small = CachedFont(pygame.font.Font(FONT_PATH, s(54)))
        self.medium = CachedFont(pygame.font.Font(FONT_PATH, s(62)))
        self.large = CachedFont(pygame.font.Font(FONT_PATH, s(92)))
        self.xlarge = CachedFont(pygame.font.Font(FONT_PATH, s(150)))
        self.xxlarge = CachedFont(pygame.font.Font(FONT_PATH, s(220)))

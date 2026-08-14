"""
Bottom ticker - a status bar drawn as an amber-outlined strip.

Static text for now (Phase 1); a scrolling variant lands in Phase 2 when
we wire weather + scene status messages through.
"""

from __future__ import annotations

import pygame

from hdmi_rich import theme
from hdmi_rich.screen import s

HEIGHT = s(100)
_PAD_X = s(24)


def draw(surface, fonts, y: int, message: str) -> None:
    w = surface.get_width()
    rect = pygame.Rect(0, y, w, HEIGHT)
    pygame.draw.rect(surface, theme.ACCENT, rect, 2)
    text_surf = fonts.small.render(message.upper(), True, theme.FAINT)
    surface.blit(
        text_surf, (_PAD_X, y + HEIGHT // 2 - text_surf.get_height() // 2)
    )

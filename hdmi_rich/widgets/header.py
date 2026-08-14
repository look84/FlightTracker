"""
Top banner - full-width bar with scene title left and active callsign right.

Rendered as a thin amber outline; the title reads in amber, the callsign
(the interesting bit) in phosphor green so the eye lands on it first.
"""

from __future__ import annotations

import pygame

from hdmi_rich import theme

HEIGHT = 96


def draw(surface, fonts, title: str, callsign: str | None = None) -> None:
    w = surface.get_width()
    # 2px amber outline gives it the console-panel feel
    pygame.draw.rect(surface, theme.ACCENT, pygame.Rect(0, 0, w, HEIGHT), 2)

    title_surf = fonts.medium.render(title.upper(), True, theme.ACCENT)
    surface.blit(title_surf, (24, HEIGHT // 2 - title_surf.get_height() // 2))

    if callsign:
        cs_surf = fonts.large.render(callsign.upper(), True, theme.PRIMARY)
        surface.blit(
            cs_surf,
            (w - cs_surf.get_width() - 24, HEIGHT // 2 - cs_surf.get_height() // 2),
        )

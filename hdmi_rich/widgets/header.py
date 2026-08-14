"""
Top banner - full-width bar with scene title left and active callsign right.

Rendered as a thin amber outline; the title reads in amber, the callsign
(the interesting bit) in phosphor green so the eye lands on it first.
"""

from __future__ import annotations

import pygame

from hdmi_rich import theme
from hdmi_rich.screen import s

HEIGHT = s(96)
_PAD_X = s(24)


def draw(surface, fonts, title: str, callsign: str | None = None) -> None:
    """Draw the top banner.

    * Outline + title colour switch from amber (STANDBY / idle) to
      phosphor green (an active scene) when *callsign* is present.
    * In active mode the title text flashes at 1 Hz (on 700 ms, off
      300 ms) to draw the eye - the outline itself stays lit.
    * The callsign, when set, is rendered centred across the banner
      in the large font (bigger than the title).
    """
    import time

    w = surface.get_width()
    is_active = bool(callsign)
    chrome_colour = theme.PRIMARY if is_active else theme.ACCENT

    pygame.draw.rect(surface, chrome_colour, pygame.Rect(0, 0, w, HEIGHT), 2)

    # Title flashes only in active mode; STANDBY stays solid.
    title_visible = True
    if is_active:
        title_visible = (time.monotonic() % 1.0) < 0.7
    if title_visible:
        title_surf = fonts.medium.render(title.upper(), True, chrome_colour)
        surface.blit(
            title_surf, (_PAD_X, HEIGHT // 2 - title_surf.get_height() // 2)
        )

    if callsign:
        cs_surf = fonts.large.render(callsign.upper(), True, theme.PRIMARY)
        surface.blit(
            cs_surf,
            (
                (w - cs_surf.get_width()) // 2,
                HEIGHT // 2 - cs_surf.get_height() // 2,
            ),
        )

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


def draw(
    surface,
    fonts,
    title: str,
    callsign: str | None = None,
    is_locked: bool = False,
) -> None:
    """Draw the top banner.

    * When *callsign* is None (idle / STANDBY) the *title* text is
      shown left-padded in amber and the outline is amber.
    * When *callsign* is set (active scene) the title is suppressed
      entirely; the outline is phosphor green and the callsign is
      rendered centred and flashing at 1 Hz (on 700 ms, off 300 ms).
    * When *is_locked* is True the left-side label reads "LOCKED" in
      amber (instead of "ACTIVE" in green) so a glance at the top bar
      distinguishes tap-pinned vs auto-cycling.
    """
    import time

    w = surface.get_width()
    is_active = bool(callsign)
    chrome_colour = theme.PRIMARY if is_active else theme.ACCENT

    pygame.draw.rect(surface, chrome_colour, pygame.Rect(0, 0, w, HEIGHT), 2)

    if is_active:
        # Left-justified state label - green in both cases; the label
        # text is the distinguisher (ACTIVE = auto-cycle, LOCKED = pinned).
        label_text = "LOCKED" if is_locked else "ACTIVE"
        label_surf = fonts.medium.render(label_text, True, theme.PRIMARY)
        surface.blit(
            label_surf, (_PAD_X, HEIGHT // 2 - label_surf.get_height() // 2)
        )
        # Centred callsign in an inverse-video "flight strip" block -
        # filled green rect with black text - flashing at 1 Hz for a
        # distinctly ATC/CRT feel.  Tight vertical padding keeps the
        # block inside the fixed header height without needing to
        # cascade a taller HEIGHT through every scene's layout math.
        if (time.monotonic() % 1.0) < 0.7:
            cs_text = callsign.upper()
            cs_surf = fonts.large.render(cs_text, True, theme.BACKGROUND)
            pad_x = s(28)
            pad_y = s(4)
            block_w = cs_surf.get_width() + pad_x * 2
            block_h = cs_surf.get_height() + pad_y * 2
            block_x = (w - block_w) // 2
            block_y = HEIGHT // 2 - block_h // 2
            pygame.draw.rect(
                surface,
                theme.PRIMARY,
                pygame.Rect(block_x, block_y, block_w, block_h),
            )
            surface.blit(cs_surf, (block_x + pad_x, block_y + pad_y))
    else:
        # Idle title only, left-padded, solid.
        title_surf = fonts.medium.render(title.upper(), True, chrome_colour)
        surface.blit(
            title_surf, (_PAD_X, HEIGHT // 2 - title_surf.get_height() // 2)
        )

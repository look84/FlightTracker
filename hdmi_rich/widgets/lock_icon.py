"""
Small pygame-drawn padlock icon, used to mark a pinned / locked flight.

Keeps the visual language consistent with the rest of the ATC chrome
(thin outlined shapes, no anti-aliasing) so it doesn't stand out as a
foreign glyph inserted amongst VT323 text.
"""

from __future__ import annotations

import pygame


def draw(surface, cx: int, cy: int, size: int, colour) -> None:
    """Draw a padlock icon centred at (cx, cy).

    ``size`` is the total icon height in physical pixels.  The body is
    roughly 60% of that; the shackle sits above it.  A single-pixel
    keyhole dot is drawn inside the body so the shape reads clearly
    even at small sizes.
    """
    size = max(6, size)
    thick = max(1, size // 8)
    body_h = int(size * 0.60)
    body_w = int(size * 0.65)
    shackle_h = size - body_h
    shackle_w = int(body_w * 0.65)

    body_left = cx - body_w // 2
    body_top = cy - size // 2 + shackle_h
    pygame.draw.rect(
        surface, colour, (body_left, body_top, body_w, body_h), thick
    )

    sh_left = cx - shackle_w // 2
    sh_right = cx + shackle_w // 2
    sh_top = body_top - shackle_h + thick
    # Left / right legs of the shackle
    pygame.draw.line(surface, colour, (sh_left, sh_top), (sh_left, body_top), thick)
    pygame.draw.line(surface, colour, (sh_right, sh_top), (sh_right, body_top), thick)
    # Top of the shackle
    pygame.draw.line(
        surface, colour, (sh_left, sh_top), (sh_right, sh_top), thick
    )

    # Keyhole dot
    dot_r = max(1, thick)
    pygame.draw.circle(
        surface, colour, (cx, body_top + body_h // 2), dot_r
    )

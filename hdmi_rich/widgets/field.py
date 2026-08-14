"""
A single tabular field, stacked layout:

    LABEL              <- tiny amber, top-left of rect
    VALUE UNIT         <- medium primary + small faint, below label

Stacked so long values (e.g. six-digit altitudes) can extend rightward
without ever bumping into the label.  Values in the same rect column
share a common left edge (rect.x), so rows still visually align even
though right-edges vary with value width.
"""

from __future__ import annotations

import pygame

from hdmi_rich import theme

LABEL_TO_VALUE_GAP = 4     # vertical gap between label row and value row
VALUE_TO_UNIT_GAP = 12     # horizontal gap between value and unit


def draw(
    surface,
    fonts,
    rect: pygame.Rect,
    label: str,
    value: str,
    unit: str = "",
    label_colour=theme.ACCENT,
    value_colour=theme.PRIMARY,
    unit_colour=theme.FAINT,
) -> None:
    """Render a single stacked field row inside *rect*."""
    label_surf = fonts.tiny.render(label.upper(), True, label_colour)
    surface.blit(label_surf, (rect.x, rect.y + 2))

    value_surf = fonts.medium.render(value.upper(), True, value_colour)
    value_y = rect.y + label_surf.get_height() + LABEL_TO_VALUE_GAP
    surface.blit(value_surf, (rect.x, value_y))

    if unit:
        unit_surf = fonts.small.render(unit.upper(), True, unit_colour)
        unit_x = rect.x + value_surf.get_width() + VALUE_TO_UNIT_GAP
        # Baseline-align to the value's baseline (value bottom minus small
        # bit for the descender), so the unit reads as a suffix rather than
        # floating in the middle of the value.
        unit_y = value_y + value_surf.get_height() - unit_surf.get_height() - 4
        surface.blit(unit_surf, (unit_x, unit_y))

"""
A single tabular field: LABEL <right-aligned VALUE> UNIT.

The unit occupies a fixed-width column at the right edge so that VALUEs
in the same rect column share one right edge across rows - critical for
readable ATC-style tabular data.
"""

from __future__ import annotations

import pygame

from hdmi_rich import theme

# Reserved horizontal space for the unit label at the right of each field.
# Wide enough for "FPM"/"KTS"/"UTC"/"KM/H" at the current small font size.
UNIT_COL_W = 112
UNIT_GUTTER = 12   # gap between value and unit


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
    """Render a single field row inside *rect*."""
    label_surf = fonts.small.render(label.upper(), True, label_colour)
    surface.blit(
        label_surf, (rect.x, rect.y + (rect.height - label_surf.get_height()) // 2)
    )

    # Fixed unit column on the right - all fields in the same rect column
    # share this anchor so their VALUEs right-align identically.
    unit_x = rect.right - UNIT_COL_W
    value_right = unit_x - UNIT_GUTTER

    if unit:
        unit_surf = fonts.small.render(unit.upper(), True, unit_colour)
        surface.blit(
            unit_surf,
            (
                unit_x,
                rect.y + (rect.height - unit_surf.get_height()) // 2 + 6,
            ),
        )

    value_surf = fonts.medium.render(value.upper(), True, value_colour)
    surface.blit(
        value_surf,
        (
            value_right - value_surf.get_width(),
            rect.y + (rect.height - value_surf.get_height()) // 2,
        ),
    )

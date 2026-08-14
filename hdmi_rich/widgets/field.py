"""
A single tabular field: LABEL <right-aligned VALUE UNIT>.

Draws inside a bounding rect so multiple fields can be stacked into a
data column without individual widget knowing about layout siblings.
"""

from __future__ import annotations

import pygame

from hdmi_rich import theme


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
    surface.blit(label_surf, (rect.x, rect.y + (rect.height - label_surf.get_height()) // 2))

    unit_w = 0
    if unit:
        unit_surf = fonts.small.render(unit.upper(), True, unit_colour)
        unit_w = unit_surf.get_width()
        surface.blit(
            unit_surf,
            (
                rect.right - unit_w,
                rect.y + (rect.height - unit_surf.get_height()) // 2 + 6,
            ),
        )

    value_surf = fonts.medium.render(value.upper(), True, value_colour)
    right_edge = rect.right - unit_w - (12 if unit else 0)
    surface.blit(
        value_surf,
        (
            right_edge - value_surf.get_width(),
            rect.y + (rect.height - value_surf.get_height()) // 2,
        ),
    )

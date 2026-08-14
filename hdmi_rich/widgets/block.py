"""
Block widget - the ATC "panel" chrome: thin amber outline with a
top-left corner label.  Scenes stack these into a quadrant grid.

Split into ``chrome`` (renders outline + chip - called from the scene's
static-chrome pass) and ``inner`` (returns the padded content rect
without drawing anything - called per-frame so dynamic content knows
where to draw).
"""

from __future__ import annotations

import pygame

from hdmi_rich import theme


def chrome(surface, fonts, rect: pygame.Rect, label: str) -> pygame.Rect:
    """Draw the block outline + chip label onto *surface*.  Returns the
    inner (padded) rect for convenience."""
    pygame.draw.rect(surface, theme.ACCENT, rect, 2)
    if label:
        pad_x = 16
        label_surf = fonts.small.render(label.upper(), True, theme.ACCENT)
        chip_w = label_surf.get_width() + 20
        chip_h = label_surf.get_height() + 4
        chip = pygame.Rect(rect.x + pad_x, rect.y - chip_h // 2, chip_w, chip_h)
        pygame.draw.rect(surface, theme.BACKGROUND, chip)
        surface.blit(label_surf, (chip.x + 10, chip.y + 2))
    return inner(rect)


def inner(rect: pygame.Rect) -> pygame.Rect:
    """Return the padded content rect (no drawing)."""
    return rect.inflate(-40, -40)


# Back-compat: single-call form still works for callers that don't
# split chrome vs. dynamic content.
def draw(surface, fonts, rect: pygame.Rect, label: str) -> pygame.Rect:
    return chrome(surface, fonts, rect, label)

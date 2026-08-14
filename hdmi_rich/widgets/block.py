"""
Block widget - the ATC "panel" chrome: thin amber outline with a
top-left corner label.  Scenes stack these into a quadrant grid.
"""

from __future__ import annotations

import pygame

from hdmi_rich import theme


def draw(surface, fonts, rect: pygame.Rect, label: str) -> pygame.Rect:
    """Draw the block chrome, return the inner rect (padded content area)."""
    pygame.draw.rect(surface, theme.ACCENT, rect, 2)
    if label:
        pad_x, pad_y = 16, 10
        label_surf = fonts.small.render(label.upper(), True, theme.ACCENT)
        # Chip on the top border - erase behind the text so it looks embedded
        chip_w = label_surf.get_width() + 20
        chip_h = label_surf.get_height() + 4
        chip = pygame.Rect(rect.x + pad_x, rect.y - chip_h // 2, chip_w, chip_h)
        pygame.draw.rect(surface, theme.BACKGROUND, chip)
        surface.blit(label_surf, (chip.x + 10, chip.y + 2))
    return rect.inflate(-40, -40)

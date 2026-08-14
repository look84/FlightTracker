"""
Digital clock widget - big HH:MM:SS + smaller day/date subline.

Standalone widget used by the idle scene in Phase 2; exposed here so
scenes can share the styling.
"""

from __future__ import annotations

from datetime import datetime

from hdmi_rich import theme


def draw(surface, fonts, x: int, y: int, now: datetime | None = None) -> None:
    now = now or datetime.now()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%a %d %b").upper()

    time_surf = fonts.xlarge.render(time_str, True, theme.PRIMARY)
    surface.blit(time_surf, (x, y))
    date_surf = fonts.small.render(date_str, True, theme.ACCENT)
    surface.blit(date_surf, (x, y + time_surf.get_height() - 8))

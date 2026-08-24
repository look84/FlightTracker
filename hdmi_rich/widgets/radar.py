"""
ATC-style radar widget: concentric rings, rotating sweep line, contact
blips with fading trails.

Split into ``draw_grid`` (rings, cardinal ticks, N label, range label -
called from the scene's static-chrome pass) and ``draw_animation``
(sweep wedge, blips - called per-frame).  ``draw`` is a back-compat
alias that renders both.
"""

from __future__ import annotations

import math

import pygame

from hdmi_rich import theme
from hdmi_rich.screen import s

SWEEP_PERIOD_S = 8.0
RING_COUNT = 4
BLIP_GLOW_S = 1.5


def draw_grid(
    surface,
    fonts,
    cx: int,
    cy: int,
    radius: int,
    outer_range_label: str = "",
) -> None:
    """Static radar chrome: rings, cross-hair, N tick + label, range label."""
    for i in range(1, RING_COUNT + 1):
        r = int(radius * i / RING_COUNT)
        pygame.draw.circle(surface, theme.DIM, (cx, cy), r, 1)
    pygame.draw.line(surface, theme.DIM, (cx - radius, cy), (cx + radius, cy), 1)
    pygame.draw.line(surface, theme.DIM, (cx, cy - radius), (cx, cy + radius), 1)

    tick_h = s(14)
    pygame.draw.line(
        surface,
        theme.ACCENT,
        (cx, cy - radius - tick_h),
        (cx, cy - radius),
        2,
    )
    n_surf = fonts.tiny.render("N", True, theme.ACCENT)
    surface.blit(
        n_surf,
        (cx - n_surf.get_width() // 2, cy - radius - tick_h - n_surf.get_height() - s(2)),
    )
    if outer_range_label:
        r_surf = fonts.tiny.render(outer_range_label, True, theme.FAINT)
        surface.blit(r_surf, (cx + radius + s(6), cy - r_surf.get_height() // 2))


def draw_animation(
    surface,
    fonts,
    cx: int,
    cy: int,
    radius: int,
    contacts: list[tuple[float, float, str]],
    t: float,
    current_index: int = -1,
    locked: bool = False,
) -> None:
    """Dynamic radar bits: sweep wedge + contact blips.

    ``current_index`` marks the flight currently featured in the main
    data card; ``locked`` is True when the operator has tapped to pin
    that flight.  The featured blip renders with a green target ring
    when auto-cycling and an amber ring when locked - matching the
    ATC pattern of "target designated" (amber) vs "target selected"
    (green).
    """
    sweep_angle_deg = (t / SWEEP_PERIOD_S) * 360 % 360
    _draw_sweep_wedge(surface, cx, cy, radius, sweep_angle_deg)

    for i, (bearing_deg, range_norm, _label) in enumerate(contacts):
        rng = max(0.0, min(1.0, range_norm)) * radius
        ang = math.radians(bearing_deg - 90)
        bx = cx + math.cos(ang) * rng
        by = cy + math.sin(ang) * rng
        _draw_blip(
            surface,
            bx,
            by,
            sweep_angle_deg,
            bearing_deg,
            is_current=(i == current_index),
            is_locked=(i == current_index and locked),
        )


def draw(
    surface,
    fonts,
    cx: int,
    cy: int,
    radius: int,
    contacts: list[tuple[float, float, str]],
    t: float,
    outer_range_label: str = "",
) -> None:
    """Back-compat: full radar in one call.  Prefer draw_grid + draw_animation."""
    draw_grid(surface, fonts, cx, cy, radius, outer_range_label)
    draw_animation(surface, fonts, cx, cy, radius, contacts, t)


def _draw_sweep_wedge(surface, cx: int, cy: int, radius: int, angle_deg: float) -> None:
    steps = 14
    span = 55
    for i in range(steps):
        frac = i / steps
        theta = math.radians(angle_deg - span * frac - 90)
        alpha = int(200 * (1 - frac))
        x2 = cx + math.cos(theta) * radius
        y2 = cy + math.sin(theta) * radius
        c = (
            int(theme.PRIMARY[0] * alpha / 255),
            int(theme.PRIMARY[1] * alpha / 255),
            int(theme.PRIMARY[2] * alpha / 255),
        )
        pygame.draw.line(surface, c, (cx, cy), (x2, y2), 1)

    theta = math.radians(angle_deg - 90)
    x2 = cx + math.cos(theta) * radius
    y2 = cy + math.sin(theta) * radius
    pygame.draw.line(surface, theme.PRIMARY, (cx, cy), (x2, y2), 2)


def _draw_blip(
    surface,
    bx: float,
    by: float,
    sweep_deg: float,
    bearing_deg: float,
    is_current: bool = False,
    is_locked: bool = False,
) -> None:
    delta = (sweep_deg - bearing_deg) % 360
    freshness = 1.0 - min(1.0, delta / (SWEEP_PERIOD_S * 360 / SWEEP_PERIOD_S / 4))
    ix, iy = int(bx), int(by)

    if is_current:
        # Larger bright dot + a green target ring.  When tap-pinned we
        # add a second concentric ring so shape (not colour) carries
        # the pinned distinction - keeps green as the "selected" colour
        # everywhere on screen (radar / contacts row / header LOCKED
        # label all agree).
        pygame.draw.circle(surface, theme.PRIMARY, (ix, iy), max(3, s(7)))
        pygame.draw.circle(surface, theme.PRIMARY, (ix, iy), max(6, s(14)), 2)
        if is_locked:
            pygame.draw.circle(
                surface, theme.PRIMARY, (ix, iy), max(9, s(22)), 2
            )
    else:
        pygame.draw.circle(surface, theme.PRIMARY, (ix, iy), max(2, s(4)))

    if freshness > 0.0:
        r = int(s(6) + s(12) * freshness)
        c = (
            int(theme.PRIMARY[0] * freshness),
            int(theme.PRIMARY[1] * freshness),
            int(theme.PRIMARY[2] * freshness),
        )
        pygame.draw.circle(surface, c, (ix, iy), r, 1)

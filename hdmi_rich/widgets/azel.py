"""
Az-El polar plot widget for the satellite scene.

Split into ``draw_grid`` (static rings, ticks, cross-hair, cardinal
labels - called from the scene's static-chrome pass) and
``draw_animation`` (trajectory + current position dot + beam -
called per-frame).  ``draw`` is a back-compat alias.
"""

from __future__ import annotations

import math

import pygame

from hdmi_rich import theme
from hdmi_rich.screen import s


def _project(cx: int, cy: int, radius: int, az_deg: float, el_deg: float) -> tuple[int, int]:
    r = radius * max(0.0, (90.0 - el_deg) / 90.0)
    a = math.radians(az_deg - 90)
    return int(cx + r * math.cos(a)), int(cy + r * math.sin(a))


def draw_grid(surface, fonts, cx: int, cy: int, radius: int) -> None:
    """Static az-el plot chrome: rings, cross-hair, cardinal ticks + labels."""
    for el in (0, 30, 60):
        r = int(radius * (90 - el) / 90)
        pygame.draw.circle(surface, theme.DIM, (cx, cy), r, 1)

    tick_len = s(18)
    label_off = s(40)
    cardinals = [(0, "N"), (90, "E"), (180, "S"), (270, "W")]
    for az_deg, label in cardinals:
        tx, ty = _project(cx, cy, radius, az_deg, 0)
        ang = math.radians(az_deg - 90)
        ox = int(tx + math.cos(ang) * tick_len)
        oy = int(ty + math.sin(ang) * tick_len)
        pygame.draw.line(surface, theme.ACCENT, (tx, ty), (ox, oy), 2)
        lx = int(tx + math.cos(ang) * label_off)
        ly = int(ty + math.sin(ang) * label_off)
        lbl_surf = fonts.medium.render(label, True, theme.ACCENT)
        surface.blit(
            lbl_surf, (lx - lbl_surf.get_width() // 2, ly - lbl_surf.get_height() // 2)
        )

    pygame.draw.circle(surface, theme.FAINT, (cx, cy), max(2, s(4)), 1)


def draw_animation(
    surface,
    fonts,
    cx: int,
    cy: int,
    radius: int,
    trajectory,
    current_az_el,
    t: float,
) -> None:
    """Dynamic bits: trajectory arc + current position dot + radial beam."""
    if trajectory:
        points = [
            _project(cx, cy, radius, az, el)
            for az, el, _rng, _dt in trajectory
            if el > 0
        ]
        if len(points) >= 2:
            pygame.draw.lines(surface, theme.FAINT, False, points, 2)

    if current_az_el is not None:
        az, el = current_az_el
        px, py = _project(cx, cy, radius, az, el)
        hx, hy = _project(cx, cy, radius, az, 0)
        pygame.draw.line(surface, theme.FAINT, (cx, cy), (hx, hy), 1)

        pulse = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 3))
        c = (
            int(theme.PRIMARY[0] * pulse),
            int(theme.PRIMARY[1] * pulse),
            int(theme.PRIMARY[2] * pulse),
        )
        pygame.draw.circle(surface, c, (px, py), max(4, s(12)))
        pygame.draw.circle(surface, theme.PRIMARY, (px, py), max(2, s(6)))


def draw(
    surface,
    fonts,
    cx: int,
    cy: int,
    radius: int,
    trajectory,
    current_az_el,
    t: float,
) -> None:
    """Back-compat: full az-el plot in one call."""
    draw_grid(surface, fonts, cx, cy, radius)
    draw_animation(surface, fonts, cx, cy, radius, trajectory, current_az_el, t)

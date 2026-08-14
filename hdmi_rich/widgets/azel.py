"""
Az-El polar plot widget for the satellite scene.

Standard "sky dome" projection: zenith at centre, horizon at outer
ring, azimuth mapped clockwise from north.  Draws faded rings at
30/60 deg elevation, cardinal N/E/S/W ticks, the trajectory arc for
the active pass, and a pulsing dot at the current position with a
radial "beam" from centre to horizon.
"""

from __future__ import annotations

import math

import pygame

from hdmi_rich import theme


def _project(cx: int, cy: int, radius: int, az_deg: float, el_deg: float) -> tuple[int, int]:
    """Convert (az, el) to screen (x, y).  el 90 = centre, 0 = outer."""
    r = radius * max(0.0, (90.0 - el_deg) / 90.0)
    a = math.radians(az_deg - 90)  # 0 deg north = up
    return int(cx + r * math.cos(a)), int(cy + r * math.sin(a))


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
    """Render the az-el plot.

    trajectory:      iterable of (az_deg, el_deg, range_km, datetime_utc);
                     the widget picks samples with el > 0 for drawing.
    current_az_el:   (az_deg, el_deg) or None if no active pass.
    t:               monotonic seconds for the pulse animation.
    """
    # -- Rings at el = 0, 30, 60 -----------------------------------------
    for el in (0, 30, 60):
        r = int(radius * (90 - el) / 90)
        pygame.draw.circle(surface, theme.DIM, (cx, cy), r, 1)

    # -- Cardinal ticks + labels -----------------------------------------
    cardinals = [(0, "N"), (90, "E"), (180, "S"), (270, "W")]
    for az_deg, label in cardinals:
        tx, ty = _project(cx, cy, radius, az_deg, 0)
        # Short tick outside the horizon ring
        ang = math.radians(az_deg - 90)
        ox = int(tx + math.cos(ang) * 18)
        oy = int(ty + math.sin(ang) * 18)
        pygame.draw.line(surface, theme.ACCENT, (tx, ty), (ox, oy), 2)
        # Label positioned just past the tick
        lx = int(tx + math.cos(ang) * 40)
        ly = int(ty + math.sin(ang) * 40)
        lbl_surf = fonts.medium.render(label, True, theme.ACCENT)
        surface.blit(
            lbl_surf, (lx - lbl_surf.get_width() // 2, ly - lbl_surf.get_height() // 2)
        )

    # -- Cross-hair through zenith --------------------------------------
    pygame.draw.circle(surface, theme.FAINT, (cx, cy), 4, 1)

    # -- Trajectory arc --------------------------------------------------
    if trajectory:
        points = [
            _project(cx, cy, radius, az, el)
            for az, el, _rng, _dt in trajectory
            if el > 0
        ]
        if len(points) >= 2:
            # Dim green line for the whole path
            pygame.draw.lines(surface, theme.FAINT, False, points, 2)

    # -- Current position dot + radial beam -----------------------------
    if current_az_el is not None:
        az, el = current_az_el
        px, py = _project(cx, cy, radius, az, el)
        # Faint radial beam from centre out to horizon at this azimuth
        hx, hy = _project(cx, cy, radius, az, 0)
        pygame.draw.line(surface, theme.FAINT, (cx, cy), (hx, hy), 1)

        # Pulsing bright dot
        pulse = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 3))
        c = (
            int(theme.PRIMARY[0] * pulse),
            int(theme.PRIMARY[1] * pulse),
            int(theme.PRIMARY[2] * pulse),
        )
        pygame.draw.circle(surface, c, (px, py), 12)
        pygame.draw.circle(surface, theme.PRIMARY, (px, py), 6)

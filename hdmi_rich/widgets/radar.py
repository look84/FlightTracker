"""
ATC-style radar widget: concentric rings, rotating sweep line, contact
blips with fading trails.

Consumers hand in contacts in *screen-space polar coordinates*
(bearing_deg 0-360 from north, range_norm 0..1 of the outer ring
radius).  The widget owns sweep animation and blip glow logic; scenes
pass a monotonic time value so animation is deterministic.
"""

from __future__ import annotations

import math

import pygame

from hdmi_rich import theme

SWEEP_PERIOD_S = 4.0     # one full rotation
RING_COUNT = 4           # 25 / 50 / 75 / 100 % rings
BLIP_GLOW_S = 1.5        # how long a blip stays bright after sweep passes


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
    """Draw a radar circle centred at (cx, cy) with *radius* outer radius.

    ``contacts`` are (bearing_deg, range_norm, label) tuples.
    ``t`` is a monotonic seconds value driving sweep + blip animation.
    ``outer_range_label`` is drawn at the top of the outer ring.
    """
    # Concentric dim rings + cross-hairs
    for i in range(1, RING_COUNT + 1):
        r = int(radius * i / RING_COUNT)
        pygame.draw.circle(surface, theme.DIM, (cx, cy), r, 1)
    pygame.draw.line(surface, theme.DIM, (cx - radius, cy), (cx + radius, cy), 1)
    pygame.draw.line(surface, theme.DIM, (cx, cy - radius), (cx, cy + radius), 1)

    # N-notch and outer-range label at the top
    tick_h = 14
    pygame.draw.line(
        surface,
        theme.ACCENT,
        (cx, cy - radius - tick_h),
        (cx, cy - radius),
        2,
    )
    n_surf = fonts.tiny.render("N", True, theme.ACCENT)
    surface.blit(n_surf, (cx - n_surf.get_width() // 2, cy - radius - tick_h - n_surf.get_height() - 2))
    if outer_range_label:
        r_surf = fonts.tiny.render(outer_range_label, True, theme.FAINT)
        surface.blit(r_surf, (cx + radius + 6, cy - r_surf.get_height() // 2))

    # Rotating sweep line - phosphor green at the head, dimming into a wedge
    sweep_angle_deg = (t / SWEEP_PERIOD_S) * 360 % 360
    _draw_sweep_wedge(surface, cx, cy, radius, sweep_angle_deg)

    # Blips
    for bearing_deg, range_norm, _label in contacts:
        rng = max(0.0, min(1.0, range_norm)) * radius
        ang = math.radians(bearing_deg - 90)   # 0 deg = north, screen y grows down
        bx = cx + math.cos(ang) * rng
        by = cy + math.sin(ang) * rng
        _draw_blip(surface, bx, by, sweep_angle_deg, bearing_deg)


def _draw_sweep_wedge(surface, cx: int, cy: int, radius: int, angle_deg: float) -> None:
    """Draw a fading wedge behind the leading sweep line."""
    steps = 28
    span = 55  # degrees of trailing wedge
    for i in range(steps):
        frac = i / steps
        theta = math.radians(angle_deg - span * frac - 90)
        alpha = int(200 * (1 - frac))
        x2 = cx + math.cos(theta) * radius
        y2 = cy + math.sin(theta) * radius
        # Direct line with modulated colour - pygame doesn't do per-pixel alpha
        # on the primary surface, so we blend by darkening the primary colour.
        c = (
            int(theme.PRIMARY[0] * alpha / 255),
            int(theme.PRIMARY[1] * alpha / 255),
            int(theme.PRIMARY[2] * alpha / 255),
        )
        pygame.draw.line(surface, c, (cx, cy), (x2, y2), 1)

    # Leading edge, full brightness
    theta = math.radians(angle_deg - 90)
    x2 = cx + math.cos(theta) * radius
    y2 = cy + math.sin(theta) * radius
    pygame.draw.line(surface, theme.PRIMARY, (cx, cy), (x2, y2), 2)


def _draw_blip(surface, bx: float, by: float, sweep_deg: float, bearing_deg: float) -> None:
    """Draw a contact blip; brighter if the sweep line just passed it."""
    # How long since sweep passed this bearing (wrapping 0..360)
    delta = (sweep_deg - bearing_deg) % 360
    freshness = 1.0 - min(1.0, delta / (SWEEP_PERIOD_S * 360 / SWEEP_PERIOD_S / 4))
    # Small always-visible dot
    pygame.draw.circle(surface, theme.PRIMARY, (int(bx), int(by)), 4)
    if freshness > 0.0:
        r = int(6 + 12 * freshness)
        c = (
            int(theme.PRIMARY[0] * freshness),
            int(theme.PRIMARY[1] * freshness),
            int(theme.PRIMARY[2] * freshness),
        )
        pygame.draw.circle(surface, c, (int(bx), int(by)), r, 1)

"""
Rich satellite scene - ATC-style pass tracker.

Shows a big Az-El polar plot on the left with the trajectory arc and
live position; the right column stacks a pass-window info block and
live telemetry (EL/AZ/RNG/SPD/ALT), both expanded to fill the space
between the header and the ticker.

Wins the scene manager on priority > flight while a pass is active
(AOS <= now <= LOS) and within the per-pass timeout window.  Reuses the
existing passes.compute_passes and passes.current_position so the maths
stays in one place.

Pass computation runs on a background thread (SGP4 for N satellites is
slow enough to hitch a 30fps render loop); has_data() reads a cached
list under a lock.
"""

from __future__ import annotations

import datetime as _dt
import threading
import time
from math import cos, radians, sin

import pygame

from hdmi_rich import theme
from hdmi_rich.chrome import SceneChrome
from hdmi_rich.scenes.scene_base import RichScene
from hdmi_rich.screen import VIRTUAL_H, s
from hdmi_rich.widgets import azel, block, header, ticker


# Fixed layout rects - values authored in 1080p units.  PASS WINDOW +
# TELEMETRY now split the right column between them, with a small gap.
_PLOT_RECT = pygame.Rect(s(24), s(120), s(900), s(840))
_WIN_RECT = pygame.Rect(s(948), s(120), s(940), s(400))
_TEL_RECT = pygame.Rect(s(948), s(560), s(940), s(400))

CYCLE_SECONDS = 4.0          # dwell on each active sat when there are several
REFRESH_MAX_AGE = 3600.0     # recompute passes every hour


class RichSatelliteScene(RichScene):
    priority = 2

    def __init__(self, cfg, fonts, tle_manager):
        self.cfg = cfg
        self.fonts = fonts
        self.tle_manager = tle_manager

        self._lock = threading.Lock()
        self._pass_windows: list = []
        self._computed_at = 0.0
        self._refresh_running = False

        self._cycle_index = 0
        self._cycle_last = 0.0
        self._chrome = SceneChrome()

    # ---- scene manager contract ---------------------------------------

    def has_data(self) -> bool:
        if not getattr(self.cfg, "satellite_tracking_enabled", False):
            return False
        self._maybe_kick_refresh()
        return bool(self._active_passes())

    def on_enter(self) -> None:
        self._cycle_index = 0
        self._cycle_last = time.monotonic()

    # ---- refresh (background) ------------------------------------------

    def _maybe_kick_refresh(self) -> None:
        with self._lock:
            if self._refresh_running:
                return
            stale = time.monotonic() - self._computed_at > REFRESH_MAX_AGE
            now_utc = _dt.datetime.utcnow()
            all_expired = self._pass_windows and all(
                w.los < now_utc for w in self._pass_windows
            )
            if self._pass_windows and not stale and not all_expired:
                return
            self._refresh_running = True

        threading.Thread(
            target=self._do_refresh, daemon=True, name="rich-passes-refresh"
        ).start()

    def _do_refresh(self) -> None:
        try:
            tles = self.tle_manager.try_get() if hasattr(self.tle_manager, "try_get") else None
            if tles is None:
                # TLE not ready yet - short blocking wait so the next
                # has_data() tick sees populated data if TLEs arrive.
                tles = self.tle_manager.get(timeout=5.0)
            if not tles:
                return
            from scenes.satellite.passes import compute_passes

            windows = compute_passes(
                tles,
                self.cfg.flight_lat,
                self.cfg.flight_lng,
                float(self.cfg.satellite_min_elevation),
                int(self.cfg.satellite_max_count),
            )
            with self._lock:
                self._pass_windows = windows
                self._computed_at = time.monotonic()
        finally:
            with self._lock:
                self._refresh_running = False

    def _active_passes(self):
        from scenes.satellite.passes import visible_passes

        with self._lock:
            snapshot = list(self._pass_windows)
        return visible_passes(
            snapshot,
            bool(self.cfg.satellite_timeout_enabled),
            int(self.cfg.satellite_timeout_seconds),
        )

    # ---- draw ---------------------------------------------------------

    def _render_static(self, bg) -> None:
        # Az-El plot chrome + grid, then the two right-column blocks.
        block.chrome(bg, self.fonts, _PLOT_RECT, "AZ / EL")
        inner = block.inner(_PLOT_RECT)
        radius = min(inner.width, inner.height) // 2 - s(40)
        azel.draw_grid(bg, self.fonts, inner.centerx, inner.centery, radius)

        block.chrome(bg, self.fonts, _WIN_RECT, "PASS WINDOW")
        block.chrome(bg, self.fonts, _TEL_RECT, "TELEMETRY")

    def draw(self, screen, t: float) -> None:
        surface = screen.surface
        surface.blit(self._chrome.get(surface, self._render_static), (0, 0))

        active = self._active_passes()
        window = None
        if active:
            if t - self._cycle_last > CYCLE_SECONDS:
                self._cycle_index = (self._cycle_index + 1) % len(active)
                self._cycle_last = t
            window = active[self._cycle_index % len(active)]

        header.draw(
            surface, self.fonts, "SATELLITE",
            (window.name if window else None),
        )

        # -- Az-El animation (trajectory + current pos + beam) -----------
        inner = block.inner(_PLOT_RECT)
        radius = min(inner.width, inner.height) // 2 - s(40)
        current = None
        traj = []
        if window is not None:
            from scenes.satellite.passes import current_position

            current = current_position(window)
            traj = window.trajectory
        azel.draw_animation(
            surface, self.fonts, inner.centerx, inner.centery, radius,
            traj, current, t,
        )

        # -- Right column dynamic content -------------------------------
        self._draw_window_info(surface, _WIN_RECT, window)
        self._draw_telemetry(surface, _TEL_RECT, window)

        # Ticker
        n = len(active)
        line = f"{n} PASS{'ES' if n != 1 else ''} ACTIVE  |  PRESS Q/ESC TO QUIT"
        ticker.draw(surface, self.fonts, VIRTUAL_H - ticker.HEIGHT, line)

    def _draw_window_info(self, surface, rect, window):
        inner = block.inner(rect)
        if window is None:
            self._dash(surface, inner, "NO ACTIVE PASS")
            return
        now = _dt.datetime.utcnow()
        elapsed = int((now - window.aos).total_seconds())
        remaining = int((window.los - now).total_seconds())
        rows = [
            ("AOS", window.aos.strftime("%H:%M:%S UTC")),
            ("LOS", window.los.strftime("%H:%M:%S UTC")),
            ("MAX EL", f"{int(window.max_el)} DEG"),
            ("+ELAPSED", _fmt_hms(max(0, elapsed))),
            ("-REMAIN", _fmt_hms(max(0, remaining))),
        ]
        row_h = s(70)
        for i, (label, value) in enumerate(rows):
            y = inner.y + s(4) + i * row_h
            l = self.fonts.small.render(label, True, theme.ACCENT)
            v = self.fonts.small.render(value, True, theme.PRIMARY)
            surface.blit(l, (inner.x, y))
            surface.blit(v, (inner.right - v.get_width(), y))

    def _draw_telemetry(self, surface, rect, window):
        inner = block.inner(rect)
        if window is None:
            self._dash(surface, inner, "NO TELEMETRY")
            return
        from scenes.satellite.passes import current_position

        pos = current_position(window)
        az_str = f"{pos[0]:05.1f}" if pos else "---.-"
        el_str = f"{pos[1]:04.1f}" if pos else "--.-"

        rng_km, speed_kmh, alt_km = _interpolate_metrics(window)

        rows = [
            ("EL", el_str, "DEG"),
            ("AZ", az_str, "DEG"),
            ("RNG", f"{rng_km:,.0f}" if rng_km is not None else "----", "KM"),
            (
                "SPD",
                f"{speed_kmh:,.0f}" if speed_kmh is not None else "----",
                "KM/H",
            ),
            ("ALT", f"{alt_km:,.0f}" if alt_km is not None else "----", "KM"),
        ]
        row_h = s(70)
        for i, (label, value, unit) in enumerate(rows):
            y = inner.y + i * row_h
            l = self.fonts.medium.render(label, True, theme.ACCENT)
            v = self.fonts.medium.render(value, True, theme.PRIMARY)
            u = self.fonts.small.render(unit, True, theme.FAINT)
            surface.blit(l, (inner.x, y))
            surface.blit(u, (inner.right - u.get_width(), y + s(8)))
            surface.blit(
                v, (inner.right - u.get_width() - s(12) - v.get_width(), y)
            )

    def _dash(self, surface, inner, msg):
        s = self.fonts.medium.render(msg, True, theme.FAINT)
        surface.blit(
            s,
            (
                inner.centerx - s.get_width() // 2,
                inner.centery - s.get_height() // 2,
            ),
        )


# --------------------------------------------------------------------------


def _fmt_hms(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _interpolate_metrics(window):
    """Return (range_km, speed_kmh, altitude_km) at 'now' for *window*.

    Range/altitude come from bracketing trajectory samples; speed is the
    tangential ground speed derived from the neighbouring samples.
    """
    traj = window.trajectory
    if not traj:
        return None, None, None
    now = _dt.datetime.utcnow()
    # Find bracket
    for i in range(len(traj) - 1):
        _, _, _, t0 = traj[i]
        _, _, _, t1 = traj[i + 1]
        if t0 <= now <= t1:
            az0, el0, r0, _ = traj[i]
            az1, el1, r1, _ = traj[i + 1]
            span = (t1 - t0).total_seconds()
            if span <= 0:
                return r0, None, r0
            frac = (now - t0).total_seconds() / span
            rng = r0 + (r1 - r0) * frac

            # Ground-track speed: convert az/el back into local Cartesian
            # points and compute the arc-chord over span.
            p0 = _local_xyz(az0, el0, r0)
            p1 = _local_xyz(az1, el1, r1)
            dx, dy, dz = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
            dist_km = (dx * dx + dy * dy + dz * dz) ** 0.5
            speed_kmh = dist_km / span * 3600.0

            return rng, speed_kmh, rng   # alt approximated by range for now
    az, el, r, _ = traj[-1]
    return r, None, r


def _local_xyz(az_deg: float, el_deg: float, r_km: float):
    az = radians(az_deg)
    el = radians(el_deg)
    r = r_km
    return (
        r * cos(el) * sin(az),
        r * cos(el) * cos(az),
        r * sin(el),
    )

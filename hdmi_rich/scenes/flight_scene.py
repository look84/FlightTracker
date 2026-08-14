"""
Rich ATC-style flight scene.

Layout:
    Left column  - primary data card (route + telemetry) for the flight
                   currently featured.  When multiple flights are in
                   range the featured flight cycles every CYCLE_SECONDS.
    Top right    - radar (square-ish, 3/5 of the right column height).
    Bottom right - CONTACTS panel: tabular list of every active flight,
                   with a chevron marking the currently-featured one.
    Header/ticker - top and bottom bars, standard chrome.

Radar positioning caveat: the ``Flight`` dataclass doesn't carry
lat/lng, so blip range is derived from the sort index (closest =
inner ring) and bearing from the aircraft's heading.  Piping lat/lng
through the data pipeline is a later improvement.
"""

from __future__ import annotations

import time

import pygame

from hdmi_rich import theme
from hdmi_rich.chrome import SceneChrome
from hdmi_rich.scenes.scene_base import RichScene
from hdmi_rich.screen import VIRTUAL_H, VIRTUAL_W, s
from hdmi_rich.widgets import block, field, header, radar, ticker

CONTENT_TOP = header.HEIGHT + s(24)
CONTENT_BOT = VIRTUAL_H - ticker.HEIGHT - s(24)
CARD_LEFT = s(32)
CARD_RIGHT = s(1000)
RADAR_LEFT = s(1040)
RADAR_RIGHT = s(1888)
RADAR_BOT = CONTENT_TOP + s(600)
CONTACTS_TOP = RADAR_BOT + s(24)
CYCLE_SECONDS = 5.0


class RichFlightScene(RichScene):
    priority = 1

    def __init__(self, overhead, cfg, fonts):
        self.overhead = overhead
        self.cfg = cfg
        self.fonts = fonts
        self._cycle_index = 0
        self._cycle_last = 0.0
        self._last_flight_id = None
        self._chrome = SceneChrome()

    def has_data(self) -> bool:
        return bool(getattr(self.overhead, "data", None))

    def on_enter(self) -> None:
        self._cycle_index = 0
        self._cycle_last = time.monotonic()

    def draw(self, screen, t: float) -> None:
        # One-blit background with all the static chrome (radar rings +
        # contacts block outline + column headers + aircraft separator).
        screen.surface.blit(
            self._chrome.get(screen.surface, self._render_static), (0, 0)
        )

        flights = self.overhead.data
        primary_index = self._pick_primary_index(flights, t)
        primary = flights[primary_index] if flights else None

        callsign = primary.callsign if primary else None
        header.draw(screen.surface, self.fonts, "ACTIVE CONTACT", callsign)

        if primary:
            self._draw_route(screen.surface, primary)
            self._draw_aircraft(screen.surface, primary)
            self._draw_telemetry(screen.surface, primary)

        self._draw_radar_dynamic(screen.surface, flights, t)
        self._draw_contacts_dynamic(screen.surface, flights, primary_index)

        n_contacts = len(flights)
        source = self._data_source_label()
        message = (
            f"{n_contacts} contact{'s' if n_contacts != 1 else ''} in range "
            f"|  source: {source}  |  press Q/ESC to quit"
        )
        ticker.draw(screen.surface, self.fonts, VIRTUAL_H - ticker.HEIGHT, message)

    # -- static chrome (rendered once, cached) --------------------------

    def _render_static(self, bg) -> None:
        # Radar rings + ticks + labels
        cx, cy, outer_r = self._radar_geometry()
        radar.draw_grid(
            bg,
            self.fonts,
            cx,
            cy,
            outer_r,
            f"{int(self.cfg.flight_radius)} KM",
        )

        # Contacts block chrome + column headers
        contacts_rect = self._contacts_rect()
        inner = block.chrome(bg, self.fonts, contacts_rect, "CONTACTS")
        for label, x in self._contacts_column_positions(inner):
            hdr = self.fonts.tiny.render(label, True, theme.FAINT)
            bg.blit(hdr, (x, inner.y))

        # Aircraft separator line
        sep_y = CONTENT_TOP + s(260)
        pygame.draw.line(
            bg, theme.DIM, (CARD_LEFT, sep_y), (CARD_RIGHT, sep_y), 1
        )

    # -- cycling --------------------------------------------------------

    def _pick_primary_index(self, flights, _t: float) -> int:
        """Advance the featured-flight cycle when multiple contacts are in range.

        Uses ``time.monotonic()`` directly rather than the animation clock
        so the cycle timing is unaffected by scene transitions.
        """
        n = len(flights)
        now = time.monotonic()
        if n == 0:
            self._cycle_index = 0
            return 0
        if n == 1:
            self._cycle_index = 0
            self._cycle_last = now
            self._last_flight_id = flights[0].flight_id
            return 0
        if now - self._cycle_last >= CYCLE_SECONDS:
            self._cycle_index = (self._cycle_index + 1) % n
            self._cycle_last = now
        else:
            self._cycle_index %= n
        self._last_flight_id = flights[self._cycle_index].flight_id
        return self._cycle_index

    # -- data card sections ---------------------------------------------

    def _draw_route(self, surface, flight) -> None:
        y = CONTENT_TOP
        origin = flight.origin or "???"
        dest = flight.destination or "???"

        origin_surf = self.fonts.xlarge.render(origin, True, theme.PRIMARY)
        arrow_surf = self.fonts.xlarge.render(">", True, theme.ACCENT)
        dest_surf = self.fonts.xlarge.render(dest, True, theme.PRIMARY)

        gap = s(32)
        total_w = (
            origin_surf.get_width() + arrow_surf.get_width() + dest_surf.get_width() + gap * 2
        )
        x = CARD_LEFT + ((CARD_RIGHT - CARD_LEFT) - total_w) // 2
        surface.blit(origin_surf, (x, y))
        surface.blit(arrow_surf, (x + origin_surf.get_width() + gap, y + s(8)))
        surface.blit(
            dest_surf,
            (x + origin_surf.get_width() + arrow_surf.get_width() + gap * 2, y),
        )

        y2 = y + origin_surf.get_height() + s(4)
        subline = self._subline_for_route(flight)
        if subline:
            sub_surf = self.fonts.small.render(subline, True, theme.FAINT)
            sub_x = CARD_LEFT + ((CARD_RIGHT - CARD_LEFT) - sub_surf.get_width()) // 2
            surface.blit(sub_surf, (sub_x, y2))

    def _subline_for_route(self, flight) -> str:
        origin = flight.origin_municipality or flight.origin_name or ""
        dest = flight.destination_municipality or flight.destination_name or ""
        if origin and dest:
            return f"{origin.upper()}  ->  {dest.upper()}"
        return ""

    def _draw_aircraft(self, surface, flight) -> None:
        # Separator line above the title is part of static chrome now.
        y = CONTENT_TOP + s(260)
        plane = flight.plane or "UNKNOWN TYPE"
        reg = flight.registration or ""
        title = plane.upper()
        if reg:
            title = f"{title}   |   REG {reg.upper()}"
        title_surf = self.fonts.large.render(title, True, theme.ACCENT)
        surface.blit(title_surf, (CARD_LEFT, y + s(16)))

    def _draw_telemetry(self, surface, flight) -> None:
        y = CONTENT_TOP + s(400)
        row_h = s(130)
        col_w = (CARD_RIGHT - CARD_LEFT) // 3

        rows = [
            [
                ("ALT", self._fmt_altitude(flight.altitude), "FT"),
                ("SPD", self._fmt_speed(flight.ground_speed), "KTS"),
                ("HDG", f"{int(flight.heading) % 360:03d}", "DEG"),
            ],
            [
                ("VS", self._fmt_vertical_speed(flight.vertical_speed), "FPM"),
                ("ETA", "--:--", "UTC"),
                ("DIST", "--", "KM"),
            ],
        ]
        for r, cols in enumerate(rows):
            for c, (label, value, unit) in enumerate(cols):
                rect = pygame.Rect(
                    CARD_LEFT + c * col_w, y + r * row_h, col_w - s(20), row_h - s(20)
                )
                field.draw(surface, self.fonts, rect, label, value, unit)

    # -- radar (dynamic) ------------------------------------------------

    def _radar_geometry(self) -> tuple[int, int, int]:
        radar_w = RADAR_RIGHT - RADAR_LEFT
        radar_h = RADAR_BOT - CONTENT_TOP
        cx = RADAR_LEFT + radar_w // 2
        cy = CONTENT_TOP + radar_h // 2
        outer_r = min(radar_w, radar_h) // 2 - s(40)
        return cx, cy, outer_r

    def _draw_radar_dynamic(self, surface, flights, t: float) -> None:
        cx, cy, outer_r = self._radar_geometry()
        contacts = []
        n = max(1, len(flights))
        for i, f in enumerate(flights):
            bearing = float(int(f.heading or 0) % 360)
            range_norm = 0.15 + (i / max(1, n)) * 0.75
            contacts.append((bearing, range_norm, f.callsign))
        radar.draw_animation(
            surface, self.fonts, cx, cy, outer_r, contacts, t
        )

    # -- contacts panel (dynamic) ---------------------------------------

    def _contacts_rect(self) -> pygame.Rect:
        return pygame.Rect(
            RADAR_LEFT,
            CONTACTS_TOP,
            RADAR_RIGHT - RADAR_LEFT,
            CONTENT_BOT - CONTACTS_TOP,
        )

    def _contacts_column_positions(self, inner):
        return [
            ("CALLSIGN", inner.x + s(40)),
            ("HDG", inner.x + s(340)),
            ("ALT", inner.x + s(480)),
            ("SPD", inner.right - s(140)),
        ]

    def _draw_contacts_dynamic(self, surface, flights, current_index: int) -> None:
        rect = self._contacts_rect()
        inner = block.inner(rect)

        if not flights:
            msg = self.fonts.small.render("NO CONTACTS", True, theme.FAINT)
            surface.blit(
                msg,
                (
                    inner.centerx - msg.get_width() // 2,
                    inner.centery - msg.get_height() // 2,
                ),
            )
            return

        col_positions = self._contacts_column_positions(inner)
        col_x = {
            "chev": inner.x,
            "callsign": col_positions[0][1],
            "hdg": col_positions[1][1],
            "alt": col_positions[2][1],
            "spd": col_positions[3][1],
        }

        row_h = s(62)
        max_rows = max(1, (inner.height - s(48)) // row_h)
        # Window the visible slice so the currently-featured flight is
        # always on screen when we cycle past the first max_rows contacts.
        if current_index < max_rows:
            window_start = 0
        else:
            window_start = current_index - max_rows + 1
        window_start = min(window_start, max(0, len(flights) - max_rows))
        visible = flights[window_start : window_start + max_rows]
        for i, f in enumerate(visible):
            actual_index = window_start + i
            y = inner.y + s(44) + i * row_h
            is_current = actual_index == current_index
            colour = theme.PRIMARY if is_current else theme.ACCENT
            if is_current:
                chev = self.fonts.small.render(">", True, theme.PRIMARY)
                surface.blit(chev, (col_x["chev"], y - s(4)))
            call = self.fonts.small.render(
                (f.callsign or "?").upper(), True, colour
            )
            hdg = self.fonts.small.render(
                f"{int(f.heading or 0) % 360:03d}", True, colour
            )
            alt = self.fonts.small.render(self._fmt_altitude(f.altitude), True, colour)
            spd = self.fonts.small.render(self._fmt_speed(f.ground_speed), True, colour)
            surface.blit(call, (col_x["callsign"], y))
            surface.blit(hdg, (col_x["hdg"], y))
            surface.blit(alt, (col_x["alt"], y))
            surface.blit(spd, (col_x["spd"], y))

    # -- formatting helpers --------------------------------------------

    def _data_source_label(self) -> str:
        if self.cfg.data_source == "fr24":
            return "FR24"
        if self.cfg.data_source == "osn":
            return "OpenSky"
        if self.cfg.data_source == "tar1090":
            return "tar1090"
        return "?"

    @staticmethod
    def _fmt_altitude(alt_ft) -> str:
        try:
            return f"{int(alt_ft):,}"
        except (TypeError, ValueError):
            return "----"

    @staticmethod
    def _fmt_speed(spd) -> str:
        try:
            return f"{int(spd)}"
        except (TypeError, ValueError):
            return "---"

    @staticmethod
    def _fmt_vertical_speed(vs) -> str:
        try:
            v = int(vs)
        except (TypeError, ValueError):
            return "----"
        sign = "+" if v > 0 else ""
        return f"{sign}{v}"

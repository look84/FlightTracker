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
from hdmi_rich.scenes.scene_base import RichScene
from hdmi_rich.widgets import block, field, header, radar, ticker

CONTENT_TOP = header.HEIGHT + 24
CONTENT_BOT = 1080 - ticker.HEIGHT - 24
CARD_LEFT = 32
CARD_RIGHT = 1000
RADAR_LEFT = 1040
RADAR_RIGHT = 1888
RADAR_BOT = CONTENT_TOP + 600
CONTACTS_TOP = RADAR_BOT + 24
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

    def has_data(self) -> bool:
        return bool(getattr(self.overhead, "data", None))

    def on_enter(self) -> None:
        self._cycle_index = 0
        self._cycle_last = time.monotonic()

    def draw(self, screen, t: float) -> None:
        flights = self.overhead.data
        primary_index = self._pick_primary_index(flights, t)
        primary = flights[primary_index] if flights else None

        callsign = primary.callsign if primary else None
        header.draw(screen.surface, self.fonts, "ACTIVE CONTACT", callsign)

        if primary:
            self._draw_route(screen.surface, primary)
            self._draw_aircraft(screen.surface, primary)
            self._draw_telemetry(screen.surface, primary)

        self._draw_radar(screen.surface, flights, t)
        self._draw_contacts(screen.surface, flights, primary_index)

        n_contacts = len(flights)
        source = self._data_source_label()
        message = (
            f"{n_contacts} contact{'s' if n_contacts != 1 else ''} in range "
            f"|  source: {source}  |  press Q/ESC to quit"
        )
        ticker.draw(screen.surface, self.fonts, 1080 - ticker.HEIGHT, message)

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

        gap = 32
        total_w = (
            origin_surf.get_width() + arrow_surf.get_width() + dest_surf.get_width() + gap * 2
        )
        x = CARD_LEFT + ((CARD_RIGHT - CARD_LEFT) - total_w) // 2
        surface.blit(origin_surf, (x, y))
        surface.blit(arrow_surf, (x + origin_surf.get_width() + gap, y + 8))
        surface.blit(
            dest_surf,
            (x + origin_surf.get_width() + arrow_surf.get_width() + gap * 2, y),
        )

        y2 = y + origin_surf.get_height() + 4
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
        y = CONTENT_TOP + 260
        rect = pygame.Rect(CARD_LEFT, y, CARD_RIGHT - CARD_LEFT, 60)
        pygame.draw.line(
            surface, theme.DIM, (rect.left, rect.top), (rect.right, rect.top), 1
        )
        plane = flight.plane or "UNKNOWN TYPE"
        reg = flight.registration or ""
        title = plane.upper()
        if reg:
            title = f"{title}   |   REG {reg.upper()}"
        title_surf = self.fonts.small.render(title, True, theme.ACCENT)
        surface.blit(title_surf, (rect.left, rect.top + 12))

    def _draw_telemetry(self, surface, flight) -> None:
        y = CONTENT_TOP + 380
        row_h = 110
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
                    CARD_LEFT + c * col_w, y + r * row_h, col_w - 20, row_h - 20
                )
                field.draw(surface, self.fonts, rect, label, value, unit)

    # -- radar ----------------------------------------------------------

    def _draw_radar(self, surface, flights, t: float) -> None:
        radar_w = RADAR_RIGHT - RADAR_LEFT
        radar_h = RADAR_BOT - CONTENT_TOP
        cx = RADAR_LEFT + radar_w // 2
        cy = CONTENT_TOP + radar_h // 2
        outer_r = min(radar_w, radar_h) // 2 - 40

        contacts = []
        n = max(1, len(flights))
        for i, f in enumerate(flights):
            bearing = float(int(f.heading or 0) % 360)
            range_norm = 0.15 + (i / max(1, n)) * 0.75
            contacts.append((bearing, range_norm, f.callsign))

        radar.draw(
            surface,
            self.fonts,
            cx,
            cy,
            outer_r,
            contacts,
            t,
            outer_range_label=f"{int(self.cfg.flight_radius)} KM",
        )

    # -- contacts panel -------------------------------------------------

    def _draw_contacts(self, surface, flights, current_index: int) -> None:
        rect = pygame.Rect(
            RADAR_LEFT, CONTACTS_TOP, RADAR_RIGHT - RADAR_LEFT, CONTENT_BOT - CONTACTS_TOP
        )
        inner = block.draw(surface, self.fonts, rect, "CONTACTS")

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

        col_x = {
            "chev": inner.x,
            "callsign": inner.x + 40,
            "hdg": inner.x + 340,
            "alt": inner.x + 480,
            "spd": inner.right - 140,
        }
        # Header row
        headers = [
            ("CALLSIGN", col_x["callsign"]),
            ("HDG", col_x["hdg"]),
            ("ALT", col_x["alt"]),
            ("SPD", col_x["spd"]),
        ]
        for label, x in headers:
            h = self.fonts.tiny.render(label, True, theme.FAINT)
            surface.blit(h, (x, inner.y))

        row_h = 40
        max_rows = max(1, (inner.height - 40) // row_h)
        for i, f in enumerate(flights[:max_rows]):
            y = inner.y + 36 + i * row_h
            is_current = i == current_index
            colour = theme.PRIMARY if is_current else theme.ACCENT
            if is_current:
                chev = self.fonts.small.render(">", True, theme.PRIMARY)
                surface.blit(chev, (col_x["chev"], y - 4))
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

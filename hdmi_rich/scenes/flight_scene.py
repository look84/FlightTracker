"""
Rich ATC-style flight scene.

Shows the closest overhead aircraft in a data card on the left, a radar
widget on the right, and a header/ticker top+bottom.  Reuses the same
``Overhead`` instance the classic display uses.

Radar positioning caveat (Phase 1): the ``Flight`` dataclass doesn't
carry lat/lng, so blip range is derived from the sort index (closest =
inner ring) and bearing from the aircraft's heading (direction of
travel, not bearing from observer).  Piping lat/lng through the data
pipeline is a Phase 2 improvement.
"""

from __future__ import annotations

import pygame

from hdmi_rich import theme
from hdmi_rich.scenes.scene_base import RichScene
from hdmi_rich.widgets import field, header, radar, ticker

CONTENT_TOP = header.HEIGHT + 24
CONTENT_BOT = 1080 - ticker.HEIGHT - 24
CARD_LEFT = 32
CARD_RIGHT = 1000
RADAR_LEFT = 1040
RADAR_RIGHT = 1888


class RichFlightScene(RichScene):
    priority = 1

    def __init__(self, overhead, cfg, fonts):
        self.overhead = overhead
        self.cfg = cfg
        self.fonts = fonts

    def has_data(self) -> bool:
        return bool(getattr(self.overhead, "data", None))

    def draw(self, screen, t: float) -> None:
        flights = self.overhead.data
        primary = flights[0] if flights else None

        # -- Header --------------------------------------------------------
        callsign = primary.callsign if primary else None
        header.draw(screen.surface, self.fonts, "ACTIVE CONTACT", callsign)

        # -- Data card ----------------------------------------------------
        if primary:
            self._draw_route(screen.surface, primary)
            self._draw_aircraft(screen.surface, primary)
            self._draw_telemetry(screen.surface, primary)

        # -- Radar --------------------------------------------------------
        self._draw_radar(screen.surface, flights, t)

        # -- Ticker -------------------------------------------------------
        n_contacts = len(flights)
        source = self._data_source_label()
        message = (
            f"{n_contacts} contact{'s' if n_contacts != 1 else ''} in range "
            f"|  source: {source}  |  press Q/ESC to quit"
        )
        ticker.draw(screen.surface, self.fonts, 1080 - ticker.HEIGHT, message)

    # -- data card sections ---------------------------------------------

    def _draw_route(self, surface, flight) -> None:
        # BIG origin / arrow / destination header near the top of the card.
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

        # Sub-line: full airport names
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
        y = CONTENT_TOP + 220
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
        y = CONTENT_TOP + 320
        row_h = 92
        col_w = (CARD_RIGHT - CARD_LEFT) // 3

        # ATC readouts are ft/kts by convention; ignore the user's LED-panel
        # unit preferences here to keep the aesthetic on-theme.
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
        radar_h = CONTENT_BOT - CONTENT_TOP
        cx = RADAR_LEFT + radar_w // 2
        cy = CONTENT_TOP + radar_h // 2
        outer_r = min(radar_w, radar_h) // 2 - 40

        # Faked positions: fan by heading, range by sort index.
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

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

import math
import time

import pygame

from hdmi_rich import theme
from hdmi_rich.chrome import SceneChrome
from hdmi_rich.geo import bearing_and_distance, eta_closest_approach_seconds
from hdmi_rich.scenes.scene_base import RichScene
from hdmi_rich.screen import VIRTUAL_H, VIRTUAL_W, s
from hdmi_rich.widgets import block, field, header, lock_icon, radar, ticker

CONTENT_TOP = header.HEIGHT + s(24)
CONTENT_BOT = VIRTUAL_H - ticker.HEIGHT - s(24)
CARD_LEFT = s(32)
CARD_RIGHT = s(1000)
RADAR_LEFT = s(1040)
RADAR_RIGHT = s(1888)

# Full-width contacts strip along the bottom - split into 2 columns of 3
# rows for a total of 6 visible flights.  The two columns share the same
# block chrome; a vertical divider separates them.
CONTACTS_LEFT = s(32)
CONTACTS_RIGHT = s(1888)
CONTACTS_HEIGHT = s(260)
CONTACTS_TOP = CONTENT_BOT - CONTACTS_HEIGHT
CONTACTS_ROW_H = s(60)
CONTACTS_COLUMNS = 2
CONTACTS_ROWS_PER_COL = 3
CONTACTS_MAX_ROWS = CONTACTS_COLUMNS * CONTACTS_ROWS_PER_COL  # 6
CONTACTS_COL_GAP = s(40)

# Main content (data card + radar) ends above the contacts panel.
MAIN_BOT = CONTACTS_TOP - s(20)
RADAR_BOT = MAIN_BOT

CYCLE_SECONDS = 5.0
# How long to stay on the flight scene after the last non-empty overhead
# refresh.  Prevents flapping to STANDBY every time a single aircraft
# briefly leaves the zone between fetches.
HAS_DATA_GRACE_S = 60.0
# Hit-test tolerance for a radar blip (virtual pixels).
BLIP_HIT_R = s(24)


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
        self._last_had_data_at: float | None = None
        # Cached copy of the last non-empty sorted flights list.  During
        # the grace window (see HAS_DATA_GRACE_S) we render this so the
        # scene doesn't blank out mid-refresh.
        self._last_flights: list = []
        # Tap-driven override: pins the featured flight for OVERRIDE_HOLD_S
        # seconds so the auto-cycle stops walking off the aircraft the
        # operator just tapped.
        self._override_flight_id: str | None = None
        self._override_at: float = 0.0

    def has_data(self) -> bool:
        """True while there are flights overhead, plus a grace window after
        the last non-empty refresh so we don't flap to STANDBY the moment
        a single aircraft briefly leaves the zone between fetches."""
        raw = getattr(self.overhead, "data", None) or []
        if raw:
            self._last_had_data_at = time.monotonic()
            return True
        if self._last_had_data_at is None:
            return False
        return time.monotonic() - self._last_had_data_at < HAS_DATA_GRACE_S

    def on_enter(self) -> None:
        self._cycle_index = 0
        self._cycle_last = time.monotonic()

    def draw(self, screen, t: float) -> None:
        # One-blit background with all the static chrome (radar rings +
        # contacts block outline + column headers + aircraft separator).
        screen.surface.blit(
            self._chrome.get(screen.surface, self._render_static), (0, 0)
        )

        raw = self._sorted_flights(self.overhead.data)
        if raw:
            self._last_flights = raw
            flights = raw
        else:
            # Grace window: fall back to the last non-empty snapshot so the
            # scene doesn't blank out between overhead refreshes.  Values
            # (ALT/SPD/HDG/positions) are up to HAS_DATA_GRACE_S stale.
            flights = self._last_flights
        primary_index = self._pick_primary_index(flights, t)
        primary = flights[primary_index] if flights else None

        callsign = primary.callsign if primary else None
        is_locked = (
            primary is not None
            and self._override_flight_id is not None
            and primary.flight_id == self._override_flight_id
        )
        header.draw(
            screen.surface, self.fonts, "ACTIVE CONTACT", callsign,
            is_locked=is_locked,
        )

        if primary:
            self._draw_route(screen.surface, primary)
            self._draw_aircraft(screen.surface, primary)
            self._draw_telemetry(screen.surface, primary)

        self._draw_radar_dynamic(screen.surface, flights, t, primary_index)
        self._draw_contacts_dynamic(screen.surface, flights, primary_index)

        # Handle touch/tap AFTER drawing so the next frame picks up the
        # new override.  Using the current frame's primary_index for the
        # contacts-panel hit-test keeps the windowed row layout in sync
        # with what the user tapped.
        touch = getattr(screen, "consume_touch", lambda: None)()
        if touch is not None:
            self._handle_touch(touch, flights, primary_index)

        n_contacts = len(flights)
        source = self._data_source_label()
        interaction = (
            "tap empty area to unpin"
            if is_locked
            else "tap a blip / row to pin"
        )
        message = (
            f"{n_contacts} contact{'s' if n_contacts != 1 else ''} in range "
            f"|  source: {source}  |  {interaction}  |  Q/ESC quit"
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

        # Contacts block chrome, vertical divider between the two columns,
        # and column headers rendered in both columns.
        contacts_rect = self._contacts_rect()
        inner = block.chrome(bg, self.fonts, contacts_rect, "CONTACTS")
        col_a, col_b = self._contacts_col_rects(inner)
        div_x = (col_a.right + col_b.x) // 2
        pygame.draw.line(bg, theme.DIM, (div_x, inner.y + s(8)),
                         (div_x, inner.bottom - s(8)), 1)
        for col_rect in (col_a, col_b):
            for label, x in self._contacts_column_layout(col_rect):
                hdr = self.fonts.tiny.render(label, True, theme.FAINT)
                bg.blit(hdr, (x, col_rect.y))

        # Aircraft separator line - shifted down so the FLT <callsign>
        # sub-line in the route section clears it.
        sep_y = CONTENT_TOP + s(280)
        pygame.draw.line(
            bg, theme.DIM, (CARD_LEFT, sep_y), (CARD_RIGHT, sep_y), 1
        )

    # -- touch handling ------------------------------------------------

    def _handle_touch(
        self, touch: tuple[int, int], flights, current_primary_index: int
    ) -> None:
        """Resolve a tap to a flight index and pin it as the featured
        flight.  Falls through to clearing the override when the tap
        lands on empty space, so a second tap outside anything resumes
        the auto-cycle immediately."""
        if not flights:
            return
        hit = self._hit_test_blip(touch, flights)
        if hit is None:
            hit = self._hit_test_contact_row(
                touch, flights, current_primary_index
            )
        if hit is None:
            # Tap outside a target - drop any active override.
            self._override_flight_id = None
            return
        self._override_flight_id = flights[hit].flight_id
        self._override_at = time.monotonic()

    def _hit_test_blip(self, touch, flights) -> int | None:
        cx, cy, outer_r = self._radar_geometry()
        # Skip cheaply if tap is nowhere near the radar area.
        if (
            not (RADAR_LEFT <= touch[0] <= RADAR_RIGHT)
            or not (CONTENT_TOP <= touch[1] <= RADAR_BOT)
        ):
            return None
        radius_km = max(1.0, float(self.cfg.flight_radius))
        best_idx: int | None = None
        best_dist_sq = float("inf")
        for i, f in enumerate(flights):
            if f.lat is None or f.lng is None:
                bearing = float(int(f.heading or 0) % 360)
                range_norm = 0.5
            else:
                bearing, dist_km = bearing_and_distance(
                    self.cfg.flight_lat, self.cfg.flight_lng, f.lat, f.lng
                )
                range_norm = min(1.0, dist_km / radius_km)
            rng = max(0.0, min(1.0, range_norm)) * outer_r
            ang = math.radians(bearing - 90)
            bx = cx + math.cos(ang) * rng
            by = cy + math.sin(ang) * rng
            dsq = (touch[0] - bx) ** 2 + (touch[1] - by) ** 2
            if dsq < BLIP_HIT_R ** 2 and dsq < best_dist_sq:
                best_dist_sq = dsq
                best_idx = i
        return best_idx

    def _hit_test_contact_row(
        self, touch, flights, current_primary_index: int
    ) -> int | None:
        rect = self._contacts_rect()
        if not rect.collidepoint(*touch):
            return None
        inner = block.inner(rect)
        col_a, col_b = self._contacts_col_rects(inner)
        if col_a.collidepoint(*touch):
            col_offset = 0
            col_rect = col_a
        elif col_b.collidepoint(*touch):
            col_offset = CONTACTS_ROWS_PER_COL
            col_rect = col_b
        else:
            return None

        # Recompute the same window_start used by _draw_contacts_dynamic
        # so we translate the tapped row back to a real flight index.
        if current_primary_index < CONTACTS_MAX_ROWS:
            window_start = 0
        else:
            window_start = current_primary_index - CONTACTS_MAX_ROWS + 1
        window_start = min(
            window_start, max(0, len(flights) - CONTACTS_MAX_ROWS)
        )

        row_h = CONTACTS_ROW_H
        base_y = col_rect.y + s(40)
        row_i = (touch[1] - base_y) // row_h
        if row_i < 0 or row_i >= CONTACTS_ROWS_PER_COL:
            return None
        idx = window_start + col_offset + row_i
        if idx >= len(flights):
            return None
        return idx

    # -- ordering -------------------------------------------------------

    def _sorted_flights(self, flights):
        """Return *flights* ordered by great-circle distance from observer.

        Contacts with no reported position fall to the back of the list.
        """
        if not flights:
            return flights
        obs_lat = self.cfg.flight_lat
        obs_lng = self.cfg.flight_lng

        def key(f):
            if f.lat is None or f.lng is None:
                return float("inf")
            _bearing, dist = bearing_and_distance(obs_lat, obs_lng, f.lat, f.lng)
            return dist

        return sorted(flights, key=key)

    # -- cycling --------------------------------------------------------

    def _pick_primary_index(self, flights, _t: float) -> int:
        """Advance the featured-flight cycle when multiple contacts are in
        range.  A tap-driven pin sticks until the operator taps elsewhere
        or the pinned flight leaves the zone - no time-based expiry, so
        a mid-cycle overhead refresh doesn't un-pin the aircraft.

        Uses ``time.monotonic()`` directly rather than the animation clock
        so the cycle timing is unaffected by scene transitions.
        """
        n = len(flights)
        now = time.monotonic()
        if n == 0:
            self._cycle_index = 0
            return 0

        # Manual pin wins while the pinned flight is still in the list.
        if self._override_flight_id is not None:
            for i, f in enumerate(flights):
                if f.flight_id == self._override_flight_id:
                    self._cycle_index = i
                    self._cycle_last = now
                    self._last_flight_id = f.flight_id
                    return i
            # Pinned flight left the zone - drop the pin.
            self._override_flight_id = None

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
            y2 += sub_surf.get_height() + s(4)

        # Flight number just under the route - a static reference next to
        # the origin/destination.  Amber label + green value keeps it
        # visually distinct from the airport codes above.
        if flight.callsign:
            cs_label_surf = self.fonts.small.render("FLT", True, theme.ACCENT)
            cs_value_surf = self.fonts.small.render(
                flight.callsign.upper(), True, theme.PRIMARY
            )
            gap_lv = s(12)
            total_w = cs_label_surf.get_width() + gap_lv + cs_value_surf.get_width()
            cs_x = CARD_LEFT + ((CARD_RIGHT - CARD_LEFT) - total_w) // 2
            surface.blit(cs_label_surf, (cs_x, y2))
            surface.blit(
                cs_value_surf,
                (cs_x + cs_label_surf.get_width() + gap_lv, y2),
            )

    def _subline_for_route(self, flight) -> str:
        origin = flight.origin_municipality or flight.origin_name or ""
        dest = flight.destination_municipality or flight.destination_name or ""
        if origin and dest:
            return f"{origin.upper()}  ->  {dest.upper()}"
        return ""

    def _draw_aircraft(self, surface, flight) -> None:
        # Separator line above the title is part of static chrome now.
        # Sits under the FLT <callsign> sub-line of the route section.
        y = CONTENT_TOP + s(280)
        plane = flight.plane or "UNKNOWN TYPE"
        reg = flight.registration or ""
        title = plane.upper()
        if reg:
            title = f"{title}   |   REG {reg.upper()}"
        title_surf = self.fonts.large.render(title, True, theme.ACCENT)
        surface.blit(title_surf, (CARD_LEFT, y + s(8)))

    def _draw_telemetry(self, surface, flight) -> None:
        y = CONTENT_TOP + s(380)
        row_h = s(100)
        col_w = (CARD_RIGHT - CARD_LEFT) // 3

        dist_km = self._distance_km(flight)
        eta_s = self._eta_seconds(flight, dist_km)

        rows = [
            [
                ("ALT", self._fmt_altitude(flight.altitude), "FT"),
                ("SPD", self._fmt_speed(flight.ground_speed), "KTS"),
                ("HDG", f"{int(flight.heading) % 360:03d}", "DEG"),
            ],
            [
                ("VS", self._fmt_vertical_speed(flight.vertical_speed), "FPM"),
                # "CPA" = closest point of approach: MM:SS until the aircraft
                # is at its nearest point to the observer given current
                # heading + ground speed.  --:-- when it's already receding.
                ("CPA", self._fmt_eta(eta_s), "MM:SS"),
                ("DIST", self._fmt_distance(dist_km), "KM"),
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

    def _draw_radar_dynamic(
        self, surface, flights, t: float, current_index: int
    ) -> None:
        cx, cy, outer_r = self._radar_geometry()
        radius_km = max(1.0, float(self.cfg.flight_radius))
        contacts = []
        for f in flights:
            if f.lat is None or f.lng is None:
                # Fall back to a faux bearing/range if the data source didn't
                # give us a position.  Better than dropping the contact.
                bearing = float(int(f.heading or 0) % 360)
                range_norm = 0.5
            else:
                bearing, dist_km = bearing_and_distance(
                    self.cfg.flight_lat, self.cfg.flight_lng, f.lat, f.lng
                )
                range_norm = min(1.0, dist_km / radius_km)
            contacts.append((bearing, range_norm, f.callsign))
        radar.draw_animation(
            surface, self.fonts, cx, cy, outer_r, contacts, t,
            current_index=current_index,
        )

    # -- contacts panel (dynamic) ---------------------------------------

    def _contacts_rect(self) -> pygame.Rect:
        return pygame.Rect(
            CONTACTS_LEFT,
            CONTACTS_TOP,
            CONTACTS_RIGHT - CONTACTS_LEFT,
            CONTACTS_HEIGHT,
        )

    def _contacts_col_rects(self, inner):
        """Return the two per-column sub-rects inside the contacts inner area."""
        col_w = (inner.width - CONTACTS_COL_GAP) // 2
        left = pygame.Rect(inner.x, inner.y, col_w, inner.height)
        right = pygame.Rect(
            inner.x + col_w + CONTACTS_COL_GAP, inner.y, col_w, inner.height
        )
        return left, right

    def _contacts_column_layout(self, col_rect):
        """Header/data column positions within a single contacts column.

        Anchors mostly follow their original positions.  DIST is nudged
        left just enough to leave a small tail on the right for the
        pinned-row padlock icon; other columns keep the same spread they
        had before pin-mode existed.
        """
        w = col_rect.width
        return [
            ("CALLSIGN", col_rect.x + s(20)),
            ("HDG", col_rect.x + int(w * 0.28)),
            ("ALT", col_rect.x + int(w * 0.46)),
            ("SPD", col_rect.x + int(w * 0.66)),
            ("DIST", col_rect.x + int(w * 0.78)),
        ]

    def _lock_icon_center(self, col_rect, y: int, text_h: int) -> tuple[int, int]:
        """Where to centre the padlock icon on a pinned row.

        Sits inside col_rect at the right, with padding on all four
        sides between the icon and the outline rectangle - the icon is
        deliberately smaller than the row height so its body doesn't
        touch the outline's bottom stroke.
        """
        cx = col_rect.right - self._lock_icon_size(text_h) // 2 - s(10)
        cy = y + text_h // 2
        return cx, cy

    @staticmethod
    def _lock_icon_size(text_h: int) -> int:
        """Slightly smaller than a text row so top and bottom both get a
        sliver of clearance from the amber outline rectangle."""
        return int(text_h * 0.8)

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

        # Window the visible slice so the currently-featured flight is
        # always on screen when we cycle past the first CONTACTS_MAX_ROWS.
        if current_index < CONTACTS_MAX_ROWS:
            window_start = 0
        else:
            window_start = current_index - CONTACTS_MAX_ROWS + 1
        window_start = min(
            window_start, max(0, len(flights) - CONTACTS_MAX_ROWS)
        )

        col_a, col_b = self._contacts_col_rects(inner)
        for col_index, col_rect in enumerate((col_a, col_b)):
            base_idx = window_start + col_index * CONTACTS_ROWS_PER_COL
            self._draw_contacts_column(
                surface, col_rect, flights, base_idx, current_index
            )

    def _draw_contacts_column(
        self,
        surface,
        col_rect,
        flights,
        base_idx: int,
        current_index: int,
    ) -> None:
        row_h = CONTACTS_ROW_H
        cols = self._contacts_column_layout(col_rect)
        col_x = {
            "chev": col_rect.x - s(6),
            "callsign": cols[0][1],
            "hdg": cols[1][1],
            "alt": cols[2][1],
            "spd": cols[3][1],
            "dist": cols[4][1],
        }
        text_h = self.fonts.small.get_height()
        for i in range(CONTACTS_ROWS_PER_COL):
            idx = base_idx + i
            if idx >= len(flights):
                break
            f = flights[idx]
            y = col_rect.y + s(40) + i * row_h
            is_current = idx == current_index
            pin_active = (
                is_current
                and self._override_flight_id is not None
                and f.flight_id == self._override_flight_id
            )

            # Amber outlined bracket around the entire pinned row.  Big
            # unambiguous "this one is locked" signal that reads even on
            # small physical displays.  Drawn BEFORE text so the outline
            # sits behind the values.
            if pin_active:
                pad_x = s(8)
                pad_y = s(6)
                highlight = pygame.Rect(
                    col_rect.x - pad_x,
                    y - pad_y,
                    col_rect.width + pad_x * 2,
                    text_h + pad_y * 2,
                )
                pygame.draw.rect(surface, theme.ACCENT, highlight, 2)

            colour = theme.PRIMARY if is_current else theme.ACCENT
            if is_current and not pin_active:
                # Auto-cycle: chevron in the marker slot.  For pinned rows
                # the amber outline + the right-side padlock icon are the
                # signal, so no chevron.
                chev = self.fonts.small.render(">", True, theme.PRIMARY)
                surface.blit(chev, (col_x["chev"], y - s(2)))
            call = self.fonts.small.render(
                (f.callsign or "?").upper(), True, colour
            )
            hdg = self.fonts.small.render(
                f"{int(f.heading or 0) % 360:03d}", True, colour
            )
            alt = self.fonts.small.render(
                self._fmt_altitude(f.altitude), True, colour
            )
            spd = self.fonts.small.render(
                self._fmt_speed(f.ground_speed), True, colour
            )
            dist = self.fonts.small.render(
                self._fmt_distance(self._distance_km(f)), True, colour
            )
            surface.blit(call, (col_x["callsign"], y))
            surface.blit(hdg, (col_x["hdg"], y))
            surface.blit(alt, (col_x["alt"], y))
            surface.blit(spd, (col_x["spd"], y))
            surface.blit(dist, (col_x["dist"], y))

            # Padlock icon at the right end of the pinned row, in the
            # small tail past DIST reserved by _contacts_column_layout.
            if pin_active:
                icx, icy = self._lock_icon_center(col_rect, y, text_h)
                lock_icon.draw(
                    surface, icx, icy, self._lock_icon_size(text_h), theme.ACCENT
                )

    # -- geo helpers ----------------------------------------------------

    def _distance_km(self, flight) -> float | None:
        if flight.lat is None or flight.lng is None:
            return None
        _bearing, dist_km = bearing_and_distance(
            self.cfg.flight_lat, self.cfg.flight_lng, flight.lat, flight.lng
        )
        return dist_km

    def _eta_seconds(self, flight, dist_km: float | None) -> float | None:
        if flight.lat is None or flight.lng is None:
            return None
        try:
            gs = float(flight.ground_speed or 0)
        except (TypeError, ValueError):
            return None
        return eta_closest_approach_seconds(
            self.cfg.flight_lat,
            self.cfg.flight_lng,
            flight.lat,
            flight.lng,
            float(flight.heading or 0),
            gs,
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

    @staticmethod
    def _fmt_distance(dist_km) -> str:
        if dist_km is None:
            return "--"
        if dist_km >= 100:
            return f"{int(round(dist_km))}"
        return f"{dist_km:.1f}"

    @staticmethod
    def _fmt_eta(eta_s) -> str:
        """Format an ETA in seconds as MM:SS (or --:-- when unknown/receding)."""
        if eta_s is None:
            return "--:--"
        eta_s = int(round(eta_s))
        m, sec = divmod(eta_s, 60)
        if m >= 100:
            return "99+"
        return f"{m:02d}:{sec:02d}"

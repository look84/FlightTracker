"""
Rich idle scene - 2x2 dashboard shown when no aircraft is overhead.

Quadrants:
    TL: LOCAL TIME     (big HH:MM:SS + date + day)
    TR: CONDITIONS     (temp, description, humidity, wind)
    BL: FORECAST       (3-day highs/lows)
    BR: ASTRO          (sunrise, sunset, moon phase)

Weather comes from the shared WeatherService singleton (same source the
classic idle scene uses); missing / offline weather degrades to placeholder
dashes rather than blanking the block.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pygame

from hdmi_rich import theme
from hdmi_rich.chrome import SceneChrome
from hdmi_rich.scenes.scene_base import RichScene
from hdmi_rich.screen import VIRTUAL_H, VIRTUAL_W, s
from hdmi_rich.widgets import block, header, ticker


class RichIdleScene(RichScene):
    priority = 0

    def __init__(self, cfg, fonts):
        self.cfg = cfg
        self.fonts = fonts
        self._weather_service = None
        self._chrome = SceneChrome()

    def has_data(self) -> bool:
        # Fallback scene - manager picks us when no other scene has data.
        return False

    def _weather(self):
        import logging

        log = logging.getLogger("rich-idle")
        if self._weather_service is None:
            try:
                from scenes.idle.themes.theme_utilities import WeatherService

                self._weather_service = WeatherService.instance()
                log.info("WeatherService instantiated")
            except Exception:
                log.exception("WeatherService instantiation failed")
                return None
        try:
            data = self._weather_service.get()
            # Log the transition None <-> has-data exactly once each way so
            # we don't spam the log at 20fps.
            if data is None:
                if not getattr(self, "_weather_reported_none", False):
                    log.warning(
                        "WeatherService.get() returned None - check API key + network"
                    )
                    self._weather_reported_none = True
            else:
                if not getattr(self, "_weather_reported_data", False):
                    from setup.configuration import Config

                    cfg = Config.instance()
                    log.info(
                        "WeatherService.get() returned dict with %d keys; "
                        "daily length=%d; api_key set=%s",
                        len(data),
                        len(data.get("daily") or []),
                        bool(cfg.weatherapi_key),
                    )
                    self._weather_reported_data = True
            return data
        except Exception:
            log.exception("WeatherService.get() failed")
            return None

    def _quadrants(self):
        """Return the four (name, rect) quadrants; layout is fixed."""
        top = header.HEIGHT + s(24)
        bot = VIRTUAL_H - ticker.HEIGHT - s(24)
        gap = s(16)
        pad = s(24)
        w_avail = VIRTUAL_W - pad * 2 - gap
        h_avail = bot - top - gap
        qw = w_avail // 2
        qh = h_avail // 2
        return [
            ("LOCAL TIME", pygame.Rect(pad, top, qw, qh)),
            ("CONDITIONS", pygame.Rect(pad + qw + gap, top, qw, qh)),
            ("FORECAST", pygame.Rect(pad, top + qh + gap, qw, qh)),
            ("ASTRO", pygame.Rect(pad + qw + gap, top + qh + gap, qw, qh)),
        ]

    def _render_static(self, bg) -> None:
        # The four block outlines + chip labels never change; render once.
        for label, rect in self._quadrants():
            block.chrome(bg, self.fonts, rect, label)

    def draw(self, screen, t: float) -> None:
        surface = screen.surface
        surface.blit(self._chrome.get(surface, self._render_static), (0, 0))
        header.draw(surface, self.fonts, "STANDBY", None)

        weather = self._weather()
        quads = self._quadrants()
        self._draw_clock(surface, quads[0][1])
        self._draw_conditions(surface, quads[1][1], weather)
        self._draw_forecast(surface, quads[2][1], weather)
        self._draw_astro(surface, quads[3][1], weather)

        ticker.draw(
            surface,
            self.fonts,
            VIRTUAL_H - ticker.HEIGHT,
            "WAITING FOR OVERHEAD AIRCRAFT  |  PRESS Q/ESC TO QUIT",
        )

    # ---- quadrants ----

    def _draw_clock(self, surface, rect):
        inner = block.inner(rect)
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%A").upper()
        sub_str = now.strftime("%d %b %Y").upper()

        big = self.fonts.xxlarge
        time_surf = big.render(time_str, True, theme.PRIMARY)
        surface.blit(
            time_surf,
            (inner.centerx - time_surf.get_width() // 2, inner.y + s(20)),
        )
        date_surf = self.fonts.medium.render(date_str, True, theme.ACCENT)
        surface.blit(
            date_surf,
            (inner.centerx - date_surf.get_width() // 2, inner.y + s(220)),
        )
        sub_surf = self.fonts.small.render(sub_str, True, theme.FAINT)
        surface.blit(
            sub_surf,
            (inner.centerx - sub_surf.get_width() // 2, inner.y + s(290)),
        )

    def _draw_conditions(self, surface, rect, weather):
        inner = block.inner(rect)
        if not weather:
            self._draw_dash(surface, inner, "WEATHER UNAVAILABLE")
            return

        temp = self._temperature(weather.get("temp_c"))
        desc = (weather.get("description") or "").upper()
        humidity = weather.get("humidity")
        wind_kph = weather.get("wind_kph")
        wind_dir = (weather.get("wind_dir") or "").upper()

        big = self.fonts.xxlarge
        temp_surf = big.render(temp, True, theme.PRIMARY)
        surface.blit(temp_surf, (inner.x, inner.y + s(10)))

        if desc:
            desc_surf = self.fonts.medium.render(desc, True, theme.ACCENT)
            surface.blit(desc_surf, (inner.x, inner.y + s(220)))

        # Wind + humidity as a mini-table
        rows = [
            ("HUMIDITY", f"{humidity}%" if humidity is not None else "--"),
            (
                "WIND",
                f"{int(wind_kph)} KM/H {wind_dir}" if wind_kph is not None else "--",
            ),
        ]
        base_y = inner.y + s(300)
        row_gap = s(60)
        for i, (label, value) in enumerate(rows):
            l_surf = self.fonts.small.render(label, True, theme.ACCENT)
            v_surf = self.fonts.small.render(value, True, theme.PRIMARY)
            surface.blit(l_surf, (inner.x, base_y + i * row_gap))
            surface.blit(
                v_surf,
                (inner.right - v_surf.get_width(), base_y + i * row_gap),
            )

    def _draw_forecast(self, surface, rect, weather):
        inner = block.inner(rect)
        daily = (weather or {}).get("daily") or []
        if not daily:
            self._draw_dash(surface, inner, "NO FORECAST DATA")
            return

        days_to_show = min(3, len(daily))
        col_w = inner.width // days_to_show
        today = datetime.now()

        for i, day in enumerate(daily[:days_to_show]):
            col_x = inner.x + i * col_w
            label = (today + timedelta(days=i)).strftime("%a").upper()
            hi = self._temperature(day.get("maxtemp_c"))
            lo = self._temperature(day.get("mintemp_c"))
            rain = day.get("daily_chance_of_rain")

            day_surf = self.fonts.medium.render(label, True, theme.ACCENT)
            surface.blit(
                day_surf,
                (col_x + (col_w - day_surf.get_width()) // 2, inner.y + s(20)),
            )
            hi_surf = self.fonts.large.render(hi, True, theme.PRIMARY)
            surface.blit(
                hi_surf,
                (col_x + (col_w - hi_surf.get_width()) // 2, inner.y + s(90)),
            )
            lo_surf = self.fonts.medium.render(lo, True, theme.FAINT)
            surface.blit(
                lo_surf,
                (col_x + (col_w - lo_surf.get_width()) // 2, inner.y + s(190)),
            )
            if rain is not None:
                r_surf = self.fonts.small.render(
                    f"RAIN {int(rain)}%", True, theme.ACCENT
                )
                surface.blit(
                    r_surf,
                    (col_x + (col_w - r_surf.get_width()) // 2, inner.y + s(260)),
                )

    def _draw_astro(self, surface, rect, weather):
        inner = block.inner(rect)

        sunrise = sunset = None
        moon = illum = None
        if weather and weather.get("astro"):
            astro = weather["astro"]
            sunrise = astro.get("sunrise")
            sunset = astro.get("sunset")
            moon = astro.get("moon_phase")
            illum = astro.get("moon_illumination")

        # Fallback: compute sunrise/sunset from lat/lng.
        if not sunrise or not sunset:
            try:
                from utilities.sun_times import approx_sunrise_sunset

                sr_t, ss_t = approx_sunrise_sunset(
                    self.cfg.flight_lat, self.cfg.flight_lng
                )
                sunrise = sunrise or sr_t.strftime("%H:%M")
                sunset = sunset or ss_t.strftime("%H:%M")
            except Exception:
                pass

        # Fallback: compute moon phase + illumination locally so the ASTRO
        # block still says something meaningful when weather is offline or
        # the API plan doesn't include the moon fields.
        if not moon or illum is None:
            try:
                from hdmi_rich.moon import moon_phase_illumination

                local_name, local_illum = moon_phase_illumination()
                if not moon:
                    moon = local_name
                if illum is None:
                    illum = local_illum
            except Exception:
                pass

        rows = [
            ("SUNRISE", (sunrise or "--").upper()),
            ("SUNSET", (sunset or "--").upper()),
            ("MOON", (moon or "--").upper()),
            ("ILLUM", f"{illum}%" if illum is not None else "--"),
        ]
        row_h = s(60)
        for i, (label, value) in enumerate(rows):
            y = inner.y + s(20) + i * row_h
            l_surf = self.fonts.medium.render(label, True, theme.ACCENT)
            v_surf = self.fonts.medium.render(value, True, theme.PRIMARY)
            surface.blit(l_surf, (inner.x, y))
            surface.blit(v_surf, (inner.right - v_surf.get_width(), y))

    # ---- helpers ----

    def _draw_dash(self, surface, inner, message):
        s = self.fonts.medium.render(message, True, theme.FAINT)
        surface.blit(
            s, (inner.centerx - s.get_width() // 2, inner.centery - s.get_height() // 2)
        )

    def _temperature(self, temp_c) -> str:
        if temp_c is None:
            return "--"
        unit = getattr(self.cfg, "temperature_unit", "c")
        if unit == "f":
            val = temp_c * 9 / 5 + 32
            suffix = "F"
        elif unit == "k":
            val = temp_c + 273.15
            suffix = "K"
        else:
            val = temp_c
            suffix = "C"
        return f"{int(round(val))}{chr(176)}{suffix}"

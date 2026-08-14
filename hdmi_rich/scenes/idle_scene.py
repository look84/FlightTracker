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
from hdmi_rich.scenes.scene_base import RichScene
from hdmi_rich.widgets import block, header, ticker


class RichIdleScene(RichScene):
    priority = 0

    def __init__(self, cfg, fonts):
        self.cfg = cfg
        self.fonts = fonts
        self._weather_service = None

    def has_data(self) -> bool:
        # Fallback scene - manager picks us when no other scene has data.
        return False

    def _weather(self):
        if self._weather_service is None:
            try:
                from scenes.idle.themes.theme_utilities import WeatherService

                self._weather_service = WeatherService.instance()
            except Exception:
                return None
        try:
            return self._weather_service.get()
        except Exception:
            return None

    def draw(self, screen, t: float) -> None:
        surface = screen.surface
        header.draw(surface, self.fonts, "STANDBY", None)

        weather = self._weather()

        # Quadrant grid geometry
        top = header.HEIGHT + 24
        bot = 1080 - ticker.HEIGHT - 24
        gap = 16
        pad = 24
        w_avail = 1920 - pad * 2 - gap
        h_avail = bot - top - gap
        qw = w_avail // 2
        qh = h_avail // 2

        tl = pygame.Rect(pad, top, qw, qh)
        tr = pygame.Rect(pad + qw + gap, top, qw, qh)
        bl = pygame.Rect(pad, top + qh + gap, qw, qh)
        br = pygame.Rect(pad + qw + gap, top + qh + gap, qw, qh)

        self._draw_clock(surface, tl)
        self._draw_conditions(surface, tr, weather)
        self._draw_forecast(surface, bl, weather)
        self._draw_astro(surface, br, weather)

        ticker.draw(
            surface,
            self.fonts,
            1080 - ticker.HEIGHT,
            "WAITING FOR OVERHEAD AIRCRAFT  |  PRESS Q/ESC TO QUIT",
        )

    # ---- quadrants ----

    def _draw_clock(self, surface, rect):
        inner = block.draw(surface, self.fonts, rect, "LOCAL TIME")
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%A").upper()
        sub_str = now.strftime("%d %b %Y").upper()

        big = self.fonts.at(220)
        time_surf = big.render(time_str, True, theme.PRIMARY)
        surface.blit(
            time_surf,
            (inner.centerx - time_surf.get_width() // 2, inner.y + 20),
        )
        date_surf = self.fonts.medium.render(date_str, True, theme.ACCENT)
        surface.blit(
            date_surf,
            (inner.centerx - date_surf.get_width() // 2, inner.y + 220),
        )
        sub_surf = self.fonts.small.render(sub_str, True, theme.FAINT)
        surface.blit(
            sub_surf,
            (inner.centerx - sub_surf.get_width() // 2, inner.y + 290),
        )

    def _draw_conditions(self, surface, rect, weather):
        inner = block.draw(surface, self.fonts, rect, "CONDITIONS")
        if not weather:
            self._draw_dash(surface, inner, "WEATHER UNAVAILABLE")
            return

        temp = self._temperature(weather.get("temp_c"))
        desc = (weather.get("description") or "").upper()
        humidity = weather.get("humidity")
        wind_kph = weather.get("wind_kph")
        wind_dir = (weather.get("wind_dir") or "").upper()

        big = self.fonts.at(240)
        temp_surf = big.render(temp, True, theme.PRIMARY)
        surface.blit(temp_surf, (inner.x, inner.y + 10))

        if desc:
            desc_surf = self.fonts.medium.render(desc, True, theme.ACCENT)
            surface.blit(desc_surf, (inner.x, inner.y + 220))

        # Wind + humidity as a mini-table
        rows = [
            ("HUMIDITY", f"{humidity}%" if humidity is not None else "--"),
            (
                "WIND",
                f"{int(wind_kph)} KM/H {wind_dir}" if wind_kph is not None else "--",
            ),
        ]
        base_y = inner.y + 300
        for i, (label, value) in enumerate(rows):
            l_surf = self.fonts.small.render(label, True, theme.ACCENT)
            v_surf = self.fonts.small.render(value, True, theme.PRIMARY)
            surface.blit(l_surf, (inner.x, base_y + i * 40))
            surface.blit(
                v_surf,
                (inner.right - v_surf.get_width(), base_y + i * 40),
            )

    def _draw_forecast(self, surface, rect, weather):
        inner = block.draw(surface, self.fonts, rect, "FORECAST")
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
                (col_x + (col_w - day_surf.get_width()) // 2, inner.y + 20),
            )
            hi_surf = self.fonts.at(100).render(hi, True, theme.PRIMARY)
            surface.blit(
                hi_surf,
                (col_x + (col_w - hi_surf.get_width()) // 2, inner.y + 90),
            )
            lo_surf = self.fonts.medium.render(lo, True, theme.FAINT)
            surface.blit(
                lo_surf,
                (col_x + (col_w - lo_surf.get_width()) // 2, inner.y + 190),
            )
            if rain is not None:
                r_surf = self.fonts.small.render(
                    f"RAIN {int(rain)}%", True, theme.ACCENT
                )
                surface.blit(
                    r_surf,
                    (col_x + (col_w - r_surf.get_width()) // 2, inner.y + 260),
                )

    def _draw_astro(self, surface, rect, weather):
        inner = block.draw(surface, self.fonts, rect, "ASTRO")

        sunrise = sunset = None
        moon = illum = None
        if weather and weather.get("astro"):
            astro = weather["astro"]
            sunrise = astro.get("sunrise")
            sunset = astro.get("sunset")
            moon = astro.get("moon_phase")
            illum = astro.get("moon_illumination")

        # Fallback: compute sunrise/sunset from lat/lng
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

        rows = [
            ("SUNRISE", (sunrise or "--").upper()),
            ("SUNSET", (sunset or "--").upper()),
            ("MOON", (moon or "--").upper()),
            ("ILLUM", f"{illum}%" if illum is not None else "--"),
        ]
        row_h = 60
        for i, (label, value) in enumerate(rows):
            y = inner.y + 20 + i * row_h
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

"""
Rich boot / splash screen.

Not a RichScene proper - rendered inline by RichDisplay during the boot
phase (before the main scene loop starts).  Reads its state from a dict
that the boot thread mutates as checks complete.
"""

from __future__ import annotations

import pygame

from hdmi_rich import theme
from hdmi_rich.widgets import block, header, qr, ticker
from version import VERSION


class RichLoadingScene:
    def __init__(self, cfg, fonts):
        self.cfg = cfg
        self.fonts = fonts

    def draw(self, screen, state: dict) -> None:
        surface = screen.surface
        header.draw(surface, self.fonts, "FLIGHTTRACKER", None)

        # Boot banner
        title_font = self.fonts.at(180)
        title_surf = title_font.render("FLIGHT TRACKER", True, theme.PRIMARY)
        surface.blit(
            title_surf,
            (1920 // 2 - title_surf.get_width() // 2, 140),
        )
        subtitle = "ATC-STYLE HDMI OUTPUT"
        sub_surf = self.fonts.medium.render(subtitle, True, theme.ACCENT)
        surface.blit(
            sub_surf,
            (1920 // 2 - sub_surf.get_width() // 2, 320),
        )

        # System status (left)
        status_rect = pygame.Rect(64, 420, 900, 460)
        inner = block.draw(surface, self.fonts, status_rect, "SYSTEM STATUS")

        rows = [
            (self._source_label(), state.get("data_source", "...")),
            ("TLE", state.get("tle", "...")),
            ("ROUTE", state.get("route", "...")),
            ("IP", state.get("ip", "...")),
        ]
        row_h = 80
        for i, (label, value) in enumerate(rows):
            y = inner.y + 20 + i * row_h
            l_surf = self.fonts.medium.render(label, True, theme.ACCENT)
            v_surf = self.fonts.medium.render(
                str(value).upper(), True, self._value_colour(str(value))
            )
            surface.blit(l_surf, (inner.x, y))
            surface.blit(v_surf, (inner.right - v_surf.get_width(), y))

        # Configuration QR (right)
        qr_rect = pygame.Rect(1920 - 964, 420, 900, 460)
        inner = block.draw(surface, self.fonts, qr_rect, "CONFIGURATION")

        url = state.get("url")
        if url:
            qr_surf = qr.surface(url, module_pixels=8)
            qs = qr_surf.get_width()
            surface.blit(qr_surf, (inner.x + (inner.width - qs) // 2, inner.y + 10))
            url_surf = self.fonts.small.render(url, True, theme.PRIMARY)
            surface.blit(
                url_surf,
                (
                    inner.centerx - url_surf.get_width() // 2,
                    inner.y + inner.height - 40,
                ),
            )
        elif state.get("web_disabled"):
            msg_surf = self.fonts.medium.render(
                "WEB INTERFACE DISABLED", True, theme.FAINT
            )
            surface.blit(
                msg_surf,
                (
                    inner.centerx - msg_surf.get_width() // 2,
                    inner.centery - msg_surf.get_height() // 2,
                ),
            )
        else:
            wait_surf = self.fonts.medium.render(
                "STARTING WEB SERVER...", True, theme.FAINT
            )
            surface.blit(
                wait_surf,
                (
                    inner.centerx - wait_surf.get_width() // 2,
                    inner.centery - wait_surf.get_height() // 2,
                ),
            )

        version_str = f"v{'.'.join(map(str, VERSION))}"
        message = state.get("message", "INITIALISING...")
        line = f"{version_str}  |  {message}"
        ticker.draw(surface, self.fonts, 1080 - ticker.HEIGHT, line)

    def _source_label(self) -> str:
        return {
            "fr24": "FR24",
            "osn": "OPENSKY",
            "tar1090": "TAR1090",
        }.get(self.cfg.data_source, "SOURCE")

    def _value_colour(self, value: str):
        v = value.upper()
        if v == "OK":
            return theme.PRIMARY
        if v == "FAIL":
            return theme.WARNING
        if v in ("OFF", "N/A", "..."):
            return theme.FAINT
        return theme.PRIMARY

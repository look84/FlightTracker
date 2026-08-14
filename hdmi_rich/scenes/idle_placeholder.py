"""
Minimal idle scene stub for Phase 1.

Shows the clock and a "STANDBY / NO CONTACTS" message when the flight
scene has no data.  Replaced in Phase 2 by the real IdleScene with
weather + forecast blocks.
"""

from __future__ import annotations

from hdmi_rich import theme
from hdmi_rich.scenes.scene_base import RichScene
from hdmi_rich.widgets import clock, header, ticker


class RichIdlePlaceholder(RichScene):
    priority = 0

    def __init__(self, cfg, fonts):
        self.cfg = cfg
        self.fonts = fonts

    def has_data(self) -> bool:
        # Priority-0 fallback - manager picks us when nobody else has data.
        return False

    def draw(self, screen, t: float) -> None:
        header.draw(screen.surface, self.fonts, "STANDBY", None)

        # Big centred clock
        clock.draw(screen.surface, self.fonts, x=520, y=380)

        # Sub-message beneath the clock
        message = "NO CONTACTS IN RANGE"
        m_surf = self.fonts.medium.render(message, True, theme.FAINT)
        screen.surface.blit(
            m_surf, (1920 // 2 - m_surf.get_width() // 2, 640)
        )

        ticker.draw(
            screen.surface,
            self.fonts,
            1080 - ticker.HEIGHT,
            "WAITING FOR OVERHEAD AIRCRAFT  |  PRESS Q/ESC TO QUIT",
        )

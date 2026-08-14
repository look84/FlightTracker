"""
RichDisplay - main loop for the ATC-style HDMI UI.

Owns the pygame screen, fonts, scene manager, and the Overhead data
provider.  Refreshes overhead data at the same cadence as the classic
Display (tar1090=10s / OSN=22s / FR24=30s) on a background thread so the
render loop stays at 30fps regardless of network latency.
"""

from __future__ import annotations

import logging
import threading
import time

from hdmi_rich import theme
from hdmi_rich.fonts import Fonts
from hdmi_rich.scenes.flight_scene import RichFlightScene
from hdmi_rich.scenes.idle_placeholder import RichIdlePlaceholder
from hdmi_rich.scenes.scene_base import RichSceneManager
from hdmi_rich.screen import RichScreen

TARGET_FPS = 30


class RichDisplay:
    def __init__(self, cfg, fullscreen: bool = True):
        self.cfg = cfg
        self.fullscreen = fullscreen
        self.logger = logging.getLogger("rich-display")

    def run(self) -> None:
        import pygame

        self.logger.info("Rich HDMI display starting (fullscreen=%s)", self.fullscreen)

        screen = RichScreen(fullscreen=self.fullscreen)
        fonts = Fonts()

        overhead, refresh_interval = self._build_overhead()

        scenes = [
            RichIdlePlaceholder(self.cfg, fonts),
            RichFlightScene(overhead, self.cfg, fonts),
        ]
        manager = RichSceneManager(scenes)

        # Background refresh thread - keeps the render loop at 30fps even
        # when the data source is slow.
        stop_flag = threading.Event()
        threading.Thread(
            target=self._refresh_loop,
            args=(overhead, refresh_interval, stop_flag),
            daemon=True,
            name="rich-overhead-refresh",
        ).start()

        clock = pygame.time.Clock()
        start = time.monotonic()
        try:
            while True:
                t = time.monotonic() - start
                screen.pump_events()
                screen.clear(theme.BACKGROUND)
                scene = manager.pick()
                scene.draw(screen, t)
                screen.present()
                clock.tick(TARGET_FPS)
        finally:
            stop_flag.set()

    def _build_overhead(self):
        """Return (overhead_instance, refresh_seconds)."""
        if self.cfg.use_tar1090:
            from utilities.overhead_tar1090 import Overhead

            return Overhead(), 10
        if self.cfg.use_osn:
            from utilities.overhead_osn import Overhead

            return Overhead(), 22
        from utilities.overhead_fr24 import Overhead

        return Overhead(), 30

    def _refresh_loop(self, overhead, interval: int, stop_flag: threading.Event) -> None:
        while not stop_flag.is_set():
            try:
                overhead.refresh()
            except Exception:
                self.logger.exception("overhead.refresh() failed")
            if stop_flag.wait(interval):
                break

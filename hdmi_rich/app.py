"""
RichDisplay - main loop for the ATC-style HDMI UI.

Two phases: a boot phase (loading scene while Flask + connectivity
checks come up), then the main scene loop (flight/idle switched by the
scene manager).  Overhead data is refreshed on a background thread at
the same cadence as the classic Display (tar1090=10s / OSN=22s / FR24=30s).
"""

from __future__ import annotations

import logging
import threading
import time

from hdmi_rich import boot, theme
from hdmi_rich.fonts import Fonts
from hdmi_rich.scenes.flight_scene import RichFlightScene
from hdmi_rich.scenes.idle_scene import RichIdleScene
from hdmi_rich.scenes.loading_scene import RichLoadingScene
from hdmi_rich.scenes.satellite_scene import RichSatelliteScene
from hdmi_rich.scenes.scene_base import RichSceneManager
from hdmi_rich.screen import RichScreen

TARGET_FPS = 20
BOOT_MIN_SECONDS = 6      # min time to show the loading scene, so users can scan the QR
BOOT_MAX_SECONDS = 20     # cap in case connectivity checks stall


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
        pyclock = pygame.time.Clock()

        # -- Phase 1: boot / loading ---------------------------------------
        self._run_boot_phase(screen, fonts, pyclock)

        # -- Phase 2: main scene loop --------------------------------------
        overhead, refresh_interval = self._build_overhead()
        scenes = [
            RichIdleScene(self.cfg, fonts),
            RichFlightScene(overhead, self.cfg, fonts),
        ]
        if getattr(self.cfg, "satellite_tracking_enabled", False):
            tle_mgr = self._start_tle_manager()
            scenes.append(RichSatelliteScene(self.cfg, fonts, tle_mgr))
        manager = RichSceneManager(scenes)

        stop_flag = threading.Event()
        threading.Thread(
            target=self._refresh_loop,
            args=(overhead, refresh_interval, stop_flag),
            daemon=True,
            name="rich-overhead-refresh",
        ).start()

        start = time.monotonic()
        try:
            while True:
                t = time.monotonic() - start
                screen.pump_events()
                screen.clear(theme.BACKGROUND)
                scene = manager.pick()
                scene.draw(screen, t)
                screen.present()
                pyclock.tick(TARGET_FPS)
        finally:
            stop_flag.set()

    # -- boot phase --------------------------------------------------------

    def _run_boot_phase(self, screen, fonts, pyclock) -> None:
        loading = RichLoadingScene(self.cfg, fonts)
        state: dict = {}

        # Kick off Flask (optional) + connectivity checks on background threads.
        # The render loop reads state as it evolves.
        flask_thread = None
        if self.cfg.web_interface_enabled:
            flask_ready = threading.Event()
            flask_thread = threading.Thread(
                target=self._flask_boot,
                args=(flask_ready, state),
                daemon=True,
                name="rich-flask-boot",
            )
            flask_thread.start()
        else:
            state["web_disabled"] = True

        threading.Thread(
            target=boot.run_checks,
            args=(self.cfg, state),
            daemon=True,
            name="rich-boot-checks",
        ).start()

        deadline = time.monotonic() + BOOT_MAX_SECONDS
        min_deadline = time.monotonic() + BOOT_MIN_SECONDS
        while True:
            now = time.monotonic()
            screen.pump_events()
            screen.clear(theme.BACKGROUND)
            loading.draw(screen, state)
            screen.present()
            pyclock.tick(TARGET_FPS)

            # Ready condition: checks completed AND either Flask ready or
            # web-disabled, AND minimum splash time has elapsed.
            checks_done = state.get("checks_done", False)
            web_ok = state.get("web_disabled") or state.get("url") is not None
            if checks_done and web_ok and now >= min_deadline:
                break
            if now >= deadline:
                self.logger.warning("Boot deadline exceeded; entering main loop.")
                break

    def _flask_boot(self, ready: threading.Event, state: dict) -> None:
        try:
            from werkzeug.serving import make_server

            from web.app import FLASK_PORT, app

            logging.getLogger("werkzeug").setLevel(logging.ERROR)
            server = make_server("0.0.0.0", FLASK_PORT, app, threaded=True)
            server.socket.set_inheritable(False)
            self.logger.info("Flask config server bound on port %d", FLASK_PORT)
            ready.set()

            # Publish URL so the loading scene renders the QR
            url = f"http://{boot.local_ip()}:{FLASK_PORT}/settings"
            state["url"] = url
            state["flask_started"] = True

            # Serve forever on this thread; RichDisplay is main-thread
            threading.Thread(
                target=server.serve_forever,
                daemon=True,
                name="rich-flask-serve",
            ).start()

            # Signal any web-side gates.
            try:
                from web.app import app_ready

                app_ready.set()
            except Exception:
                pass
        except Exception as exc:
            self.logger.exception("Flask startup failed: %s", exc)
            state["flask_error"] = str(exc)
            ready.set()

    # -- overhead ---------------------------------------------------------

    def _build_overhead(self):
        if self.cfg.use_tar1090:
            from utilities.overhead_tar1090 import Overhead

            return Overhead(), 10
        if self.cfg.use_osn:
            from utilities.overhead_osn import Overhead

            return Overhead(), 22
        from utilities.overhead_fr24 import Overhead

        return Overhead(), 30

    def _start_tle_manager(self):
        """Instantiate and start the shared TLEManager so pass computation
        can pick up TLE data as soon as the first fetch lands."""
        from utilities.tle_manager import TLEManager

        mgr = TLEManager()
        mgr.start()
        return mgr

    def _refresh_loop(self, overhead, interval: int, stop_flag: threading.Event) -> None:
        while not stop_flag.is_set():
            try:
                overhead.refresh()
            except Exception:
                self.logger.exception("overhead.refresh() failed")
            if stop_flag.wait(interval):
                break

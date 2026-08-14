"""
Fullscreen pygame surface manager for the rich HDMI UI.

Every scene draws onto a 1920x1080 *virtual* surface; at present() the
frame is scaled-to-fit onto whatever native resolution the attached HDMI
display reports.  This keeps every widget's coordinate math a fixed
constant, and lets the UI look sharp on 1080p, 1440p and 4K panels
without per-resolution layouts.

On a headless Pi (no X/Wayland) the SDL video driver is nudged to kmsdrm
so pygame writes straight to the framebuffer from a bare tty.
"""

from __future__ import annotations

import os
import sys


VIRTUAL_W = 1920
VIRTUAL_H = 1080


class RichScreen:
    """Owns the pygame window + virtual drawing surface."""

    def __init__(self, fullscreen: bool = True, window_scale: float = 0.66):
        self.fullscreen = fullscreen
        self.window_scale = window_scale
        self._real = None       # the actual pygame display surface
        self.surface = None     # the 1920x1080 virtual surface scenes draw on
        self._dest_rect = None
        self._init_pygame()

    def _init_pygame(self) -> None:
        if self.fullscreen:
            if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")

        import pygame

        pygame.init()
        if self.fullscreen:
            self._real = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
            caption = "FlightTracker - rich"
        else:
            w = int(VIRTUAL_W * self.window_scale)
            h = int(VIRTUAL_H * self.window_scale)
            self._real = pygame.display.set_mode((w, h), pygame.RESIZABLE)
            caption = "FlightTracker - rich (windowed)"
        pygame.display.set_caption(caption)

        self.surface = pygame.Surface((VIRTUAL_W, VIRTUAL_H))
        self._recompute_dest()

    def _recompute_dest(self) -> None:
        import pygame

        screen_w, screen_h = self._real.get_size()
        # Contain-fit: whichever axis is tighter caps the scale.  Preserves
        # the 16:9 canvas so the ATC layout never distorts.
        scale = min(screen_w / VIRTUAL_W, screen_h / VIRTUAL_H)
        dest_w = int(VIRTUAL_W * scale)
        dest_h = int(VIRTUAL_H * scale)
        dest_x = (screen_w - dest_w) // 2
        dest_y = (screen_h - dest_h) // 2
        self._dest_rect = pygame.Rect(dest_x, dest_y, dest_w, dest_h)

    def pump_events(self) -> None:
        """Drain the event queue; exit cleanly on quit/Q/Esc."""
        import pygame

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.shutdown()
            elif event.type == pygame.VIDEORESIZE:
                self._recompute_dest()
            elif event.type == pygame.KEYDOWN and event.key in (
                pygame.K_q,
                pygame.K_ESCAPE,
            ):
                self.shutdown()

    def clear(self, colour) -> None:
        self.surface.fill(colour)

    def present(self) -> None:
        import pygame

        self._real.fill((0, 0, 0))
        pygame.transform.scale(
            self.surface,
            (self._dest_rect.width, self._dest_rect.height),
            self._real.subsurface(self._dest_rect),
        )
        pygame.display.flip()

    def shutdown(self) -> None:
        import pygame

        pygame.quit()
        sys.exit(0)

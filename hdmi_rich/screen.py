"""
Pygame surface manager for the rich HDMI UI.

Fullscreen mode uses ``pygame.SCALED | pygame.FULLSCREEN`` so pygame's
SDL2 renderer owns the physical output scaling on the GPU.  That means
we can draw straight to the display surface at logical 1920x1080 and
skip the virtual->real memcpy that plain fullscreen requires - a big
win on the Pi where memory bandwidth is the bottleneck.

Windowed dev mode keeps the two-surface model (virtual 1920x1080 plus a
resizable real window scaled via pygame.transform.scale) so window
resize still works and doesn't need SDL2's renderer to cooperate.

On a headless Pi (no X/Wayland) the SDL video driver is nudged to kmsdrm
so pygame writes straight to the framebuffer from a bare tty.
"""

from __future__ import annotations

import os
import sys


# SCALE controls the internal virtual resolution.  All widget/scene layout
# constants are authored in 1080p units and multiplied by SCALE at import,
# so a Pi 2 or slower host can render at a smaller framebuffer while the
# physical output stays fullscreen (SDL2 SCALED handles the physical scale).
#
# For pixel-crisp text on the attached display, pick a SCALE whose product
# with 1080 divides evenly into the physical height (or matches it).
# Common presets:
#   SCALE=0.5     -> 960x540  (integer 2x -> 1080p HDMI, pixel-crisp)
#   SCALE=0.4167  -> 800x450  (matches 800x480 IPS width; 15px letterbox)
#   SCALE=0.333   -> 640x360  (integer 3x -> 1080p HDMI)
#   SCALE=1.0     -> 1920x1080 (Pi 4/5, native)
#
# Override at launch: FLIGHTTRACKER_SCALE=0.4167 ./flight-tracker.py --panel hdmi-rich
SCALE = float(os.environ.get("FLIGHTTRACKER_SCALE", "0.5"))
VIRTUAL_W = int(1920 * SCALE)
VIRTUAL_H = int(1080 * SCALE)


def s(px: float) -> int:
    """Scale a 1080p-authored pixel value to the current virtual resolution."""
    return int(px * SCALE)


class RichScreen:
    """Owns the pygame display + logical drawing surface."""

    def __init__(self, fullscreen: bool = True, window_scale: float = 0.66):
        self.fullscreen = fullscreen
        self.window_scale = window_scale
        self._real = None
        # `surface` is what scenes draw on.  Fullscreen: aliases the display
        # surface (single-buffer, GPU-scaled by SDL2).  Windowed: a separate
        # 1920x1080 virtual surface that we CPU-scale into the resizable window.
        self.surface = None
        self._dest_rect = None
        self._direct_draw = False
        self._init_pygame()

    def _init_pygame(self) -> None:
        if self.fullscreen:
            if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")

        # Force nearest-neighbour scaling on the SDL2 renderer so
        # pixel-art text (VT323) stays crisp even at non-integer scale
        # factors like 800/960 = 0.833.  "0" = nearest, "1" = linear.
        os.environ.setdefault("SDL_HINT_RENDER_SCALE_QUALITY", "0")

        import pygame

        pygame.init()
        if self.fullscreen:
            # SCALED lets SDL2 handle the physical output scaling in hardware,
            # so scenes can draw straight to the display surface at logical
            # 1920x1080.  Falls back gracefully to plain FULLSCREEN on SDL
            # builds that don't support SCALED.
            try:
                self._real = pygame.display.set_mode(
                    (VIRTUAL_W, VIRTUAL_H),
                    pygame.FULLSCREEN | pygame.SCALED,
                    vsync=1,
                )
                self.surface = self._real
                self._direct_draw = True
            except pygame.error:
                self._real = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                self.surface = pygame.Surface((VIRTUAL_W, VIRTUAL_H))
                self._direct_draw = False
            pygame.mouse.set_visible(False)
            caption = "FlightTracker - rich"
        else:
            w = int(VIRTUAL_W * self.window_scale)
            h = int(VIRTUAL_H * self.window_scale)
            self._real = pygame.display.set_mode((w, h), pygame.RESIZABLE)
            self.surface = pygame.Surface((VIRTUAL_W, VIRTUAL_H))
            self._direct_draw = False
            caption = "FlightTracker - rich (windowed)"
        pygame.display.set_caption(caption)

        self._recompute_dest()

    def _recompute_dest(self) -> None:
        import pygame

        screen_w, screen_h = self._real.get_size()
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

        if self._direct_draw:
            # Scenes drew straight to the display surface; nothing to copy.
            pygame.display.flip()
            return

        # Windowed / fallback path: CPU-scale virtual into real.
        real_w, real_h = self._real.get_size()
        if (
            self._dest_rect.width == VIRTUAL_W
            and self._dest_rect.height == VIRTUAL_H
            and self._dest_rect.x == 0
            and self._dest_rect.y == 0
            and real_w == VIRTUAL_W
            and real_h == VIRTUAL_H
        ):
            self._real.blit(self.surface, (0, 0))
        else:
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

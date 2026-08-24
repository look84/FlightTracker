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


# --- one-time SDL setup that must happen before pygame's video subsystem
# initialises anywhere in the app --------------------------------------

# Force nearest-neighbour scaling on the SDL2 renderer so pixel-art text
# (VT323) stays crisp even when the physical/virtual ratio isn't integer.
os.environ.setdefault("SDL_HINT_RENDER_SCALE_QUALITY", "0")

# Nudge SDL to kmsdrm on a headless Pi so display.init() succeeds from a
# bare tty.  Desktop / X / Wayland sessions leave this untouched.
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")


# --- virtual-resolution detection -------------------------------------
#
# All widget/scene layout constants are authored in 1080p units and
# multiplied by SCALE at import.  For pixel-crisp text the virtual
# framebuffer must map cleanly to physical pixels - either 1:1
# (virtual matches physical width) or as an integer 1:N downscale.
#
# We pick SCALE automatically by querying the physical display at import
# time and finding the largest 1:N mapping that stays at or below the
# Pi-2 performance ceiling (SCALE <= 0.5).  Sample outputs:
#
#     Physical 1920x1080   -> virtual  960x540   (N=2, SCALE=0.5)
#     Physical 1280x720    -> virtual  640x360   (N=2, SCALE=0.333)
#     Physical  800x480    -> virtual  800x450   (N=1, SCALE=0.4167)
#     Physical  640x480    -> virtual  640x360   (N=1, SCALE=0.333)
#
# FLIGHTTRACKER_SCALE=<float> overrides the detection if you know better.

_PERF_CAP_SCALE = 0.5   # keeps Pi 2 rendering at ~20 fps


def _detect_dimensions() -> tuple[int, int, float]:
    """Return ``(virtual_w, virtual_h, scale)`` for the attached display."""
    env = os.environ.get("FLIGHTTRACKER_SCALE")
    if env:
        try:
            scale = float(env)
            return int(1920 * scale), int(1080 * scale), scale
        except ValueError:
            pass

    try:
        import pygame

        pygame.display.init()
        sizes = pygame.display.get_desktop_sizes()
        if not sizes:
            raise RuntimeError("no display sizes reported")
        phys_w, _phys_h = sizes[0]
        # Try 1:1, 1:2, 1:3, 1:4 physical-to-virtual mappings.  First scale
        # at or below the perf cap wins - that's the sharpest option this
        # host can afford.
        for divisor in (1, 2, 3, 4):
            virtual_w = phys_w // divisor
            scale = virtual_w / 1920.0
            if scale <= _PERF_CAP_SCALE + 1e-9:
                virtual_h = int(1080 * scale)
                return virtual_w, virtual_h, scale
    except Exception:
        pass

    # Safe fallback: 960x540 (2x scale to 1080p HDMI).
    return 960, 540, 0.5


VIRTUAL_W, VIRTUAL_H, SCALE = _detect_dimensions()


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
        # Most recent tap in virtual-surface coords (drained by consume_touch).
        self._pending_touch: tuple[int, int] | None = None
        self._init_pygame()

    def _init_pygame(self) -> None:
        # SDL_VIDEODRIVER + SDL_HINT_RENDER_SCALE_QUALITY were set at module
        # load, before pygame's video subsystem was initialised.
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
        """Drain the event queue; exit cleanly on quit/Q/Esc.

        Also captures the most recent left-click / touch tap so scenes
        can consume it via ``consume_touch()`` and react to interaction.
        """
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
            elif (
                event.type == pygame.MOUSEBUTTONDOWN
                and getattr(event, "button", 1) == 1
            ):
                pos = self._translate_touch(event.pos[0], event.pos[1])
                if pos is not None:
                    self._pending_touch = pos

    def _translate_touch(self, mx: int, my: int) -> tuple[int, int] | None:
        """Map a raw window-space mouse coord to virtual-surface coord.

        Under ``pygame.SCALED`` (fullscreen) pygame already reports
        coordinates in the internal-surface space, so no translation is
        needed.  In the resizable windowed dev mode we undo the CPU-scale
        applied in ``present()``.  Returns None if the tap fell in the
        letterbox / outside the drawable area.
        """
        if self._direct_draw:
            # pygame.SCALED already maps to virtual coords.
            return int(mx), int(my)
        if self._dest_rect is None or not self._dest_rect.collidepoint(mx, my):
            return None
        rel_x = mx - self._dest_rect.x
        rel_y = my - self._dest_rect.y
        vx = rel_x * VIRTUAL_W / self._dest_rect.width
        vy = rel_y * VIRTUAL_H / self._dest_rect.height
        return int(vx), int(vy)

    def consume_touch(self) -> tuple[int, int] | None:
        """Return the pending tap (in virtual coords) and clear it, or
        ``None`` if there wasn't one this frame."""
        touch = self._pending_touch
        self._pending_touch = None
        return touch

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

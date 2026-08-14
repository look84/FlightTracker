"""
HDMIPanel - RGBPanel implementation for full-screen HDMI LCD output.

Renders the 64x32 canvas onto whatever HDMI display is attached, scaled
up with nearest-neighbour to preserve pixel-art crispness.  Uses pygame
in fullscreen mode; on a headless Pi (no X server) SDL is nudged into
kmsdrm mode so it writes straight to the framebuffer.

Opted in via ``FLIGHTTRACKER_PANEL=hdmi`` or ``--panel hdmi``.  Sits
alongside the piomatter (Pi 5), rgbmatrix (Pi 3/4) and pygame LED
simulator drivers.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import numpy as np

from display.bdf_font import BDFFont
from display.bdf_font import draw_text as bdf_draw_text
from display.pixel_canvas import PixelCanvas, draw_circle, draw_line, draw_square
from display.rgbpanel import Colour, RGBPanel

_CAPTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
)


_WINDOW_DEFAULT_SCALE = 20  # 20x -> 1280x640 window for local dev


class HDMIPanel(RGBPanel):
    """HDMI panel driver: 64x32 canvas scaled to fullscreen via pygame.

    ``fullscreen=False`` opens a resizable window instead - useful for
    iterating on a desktop machine without pygame taking over the whole
    display.  Selected via ``FLIGHTTRACKER_PANEL=hdmi-window``.
    """

    def __init__(self, fullscreen: bool = True, window_scale: int = _WINDOW_DEFAULT_SCALE):
        self._width = 64
        self._height = 32
        self._brightness = 50
        self._rotation = 0
        self._fullscreen = fullscreen
        self._window_scale = window_scale
        self._screen = None
        self._small_buf = None
        self._pygame_ready = False
        self._dest_rect = None  # centred canvas rect inside the window/screen

    @property
    def is_pi5(self):
        return False

    # -- RGBPanel interface ------------------------------------------------

    def init_matrix(
        self,
        width=64,
        height=32,
        brightness=50,
        rotation=0,
        hat_pwm=True,
        gpio_slowdown=1,
    ):
        self._width = width
        self._height = height
        self._brightness = brightness
        self._rotation = rotation

    def create_canvas(self):
        canvas = PixelCanvas(self._width, self._height)
        canvas.clear()
        return canvas

    def load_font(self, path):
        return BDFFont(path)

    def draw_text(self, canvas, font, x, y, colour, text):
        y = y - 1
        return bdf_draw_text(canvas, font, x, y, colour, text)

    def draw_line(self, canvas, x0, y0, x1, y1, colour):
        draw_line(canvas, x0, y0, x1, y1, colour)

    def draw_circle(self, canvas, cx, cy, radius, colour):
        draw_circle(canvas, cx, cy, radius, colour)

    def set_pixel(self, canvas, x, y, r, g, b):
        canvas.set_pixel(x, y, r, g, b)

    def fill(self, canvas, r, g, b):
        canvas.fill(r, g, b)

    def clear(self, canvas):
        canvas.clear()

    def swap(self, canvas):
        self._render(canvas)
        return canvas

    def set_brightness(self, percent):
        self._brightness = max(0, min(100, percent))

    def draw_square(self, canvas, x0, y0, x1, y1, colour):
        draw_square(canvas, x0, y0, x1, y1, colour)

    def draw_image(self, canvas, x, y, image):
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        rgb = image.convert("RGB")
        alpha = image.split()[3]
        for py in range(image.height):
            for px in range(image.width):
                if alpha.getpixel((px, py)) > 0:
                    r, g, b = rgb.getpixel((px, py))
                    canvas.set_pixel(x + px, y + py, r, g, b)

    def make_colour(self, r, g, b):
        return Colour(r, g, b)

    # -- pygame renderer ---------------------------------------------------

    def _ensure_pygame(self) -> None:
        if self._pygame_ready:
            return

        if self._fullscreen:
            # On a headless Pi (no X/Wayland session) push SDL to write directly
            # to the KMS/DRM framebuffer so the app runs from a bare tty.
            if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")

        import pygame

        pygame.init()
        if self._fullscreen:
            self._screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
            caption = "FlightTracker - HDMI"
        else:
            w = self._width * self._window_scale
            h = self._height * self._window_scale
            self._screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
            caption = "FlightTracker - HDMI (windowed)"
        pygame.display.set_caption(caption)
        self._pygame_ready = True

        # Rendering surface at native canvas size, upscaled per frame.
        self._small_buf = pygame.Surface((self._width, self._height))
        self._recompute_dest_rect()

        mode = "fullscreen" if self._fullscreen else "windowed"
        print(
            "\n"
            "┌--------------------------------------------------┐\n"
            f"│  HDMI panel - {mode:<35}│\n"
            "│                                                  │\n"
            "│  P       - save a photo to captures/             │\n"
            "│  Q / ESC - quit                                  │\n"
            "└--------------------------------------------------┘\n",
            flush=True,
        )

    def _recompute_dest_rect(self) -> None:
        """Compute the centred canvas rect (contain-fit, integer scale)."""
        import pygame

        screen_w, screen_h = self._screen.get_size()
        # Contain-fit: prefer filling the height, but clamp so the canvas
        # never clips off the sides on 16:9+ screens.  Ends up as fit-to-height
        # on 2:1-or-wider aspect (letterbox top/bottom), fit-to-width otherwise
        # (pillar-boxed).
        scale = min(screen_h // self._height, screen_w // self._width)
        scale = max(1, scale)
        dest_w = self._width * scale
        dest_h = self._height * scale
        dest_x = (screen_w - dest_w) // 2
        dest_y = (screen_h - dest_h) // 2
        self._dest_rect = pygame.Rect(dest_x, dest_y, dest_w, dest_h)

    def _render(self, canvas: PixelCanvas) -> None:
        import pygame

        self._ensure_pygame()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            elif event.type == pygame.VIDEORESIZE:
                self._recompute_dest_rect()
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    pygame.quit()
                    sys.exit(0)
                elif event.key == pygame.K_p:
                    self._save_photo()

        # Brightness scale vectorised via numpy so the render loop is
        # dominated by the blit / scale, not per-pixel Python arithmetic.
        scale = self._brightness / 100.0
        arr = np.array(canvas.buf, dtype=np.uint16).reshape(
            (canvas.rows, canvas.cols, 3)
        )
        if scale < 1.0:
            arr = (arr * scale).astype(np.uint8)
        else:
            arr = arr.astype(np.uint8)

        # pygame surfaces are addressed (width, height); numpy is (rows, cols),
        # so transpose axes 0 and 1 before handing off to blit_array.
        pygame.surfarray.blit_array(self._small_buf, arr.swapaxes(0, 1))

        self._screen.fill((0, 0, 0))
        pygame.transform.scale(
            self._small_buf,
            (self._dest_rect.width, self._dest_rect.height),
            self._screen.subsurface(self._dest_rect),
        )
        pygame.display.flip()

    # -- Captures ----------------------------------------------------------

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d_%H%M%S")

    def _save_photo(self) -> None:
        import pygame

        if self._screen is None:
            return
        os.makedirs(_CAPTURE_DIR, exist_ok=True)
        path = os.path.join(_CAPTURE_DIR, f"{self._timestamp()}.png")
        pygame.image.save(self._screen, path)
        print(f"📷  Photo saved: {path}", flush=True)

"""
Shared in-memory pixel buffer and drawing primitives.

Used by any RGBPanel driver that renders in software (the desktop LED
simulator and the HDMI LCD driver) so canvas allocation and primitive
drawing routines aren't duplicated per backend.
"""

from __future__ import annotations

from display.rgbpanel import Colour


class PixelCanvas:
    """Flat pixel buffer matching the LED grid."""

    __slots__ = ("cols", "rows", "buf")

    def __init__(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows
        self.buf: list[tuple[int, int, int]] = [(0, 0, 0)] * (cols * rows)

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        if 0 <= x < self.cols and 0 <= y < self.rows:
            self.buf[y * self.cols + x] = (
                max(0, min(255, int(r))),
                max(0, min(255, int(g))),
                max(0, min(255, int(b))),
            )

    def clear(self) -> None:
        self.buf = [(0, 0, 0)] * (self.cols * self.rows)

    def fill(self, r: int, g: int, b: int) -> None:
        self.buf = [(r, g, b)] * (self.cols * self.rows)


def draw_line(canvas, x0: int, y0: int, x1: int, y1: int, colour) -> None:
    r, g, b = colour.red, colour.green, colour.blue
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        canvas.set_pixel(x0, y0, r, g, b)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def draw_circle(canvas, cx: int, cy: int, radius: int, colour) -> None:
    r, g, b = colour.red, colour.green, colour.blue

    def _plot8(dx, dy):
        canvas.set_pixel(cx + dx, cy + dy, r, g, b)
        canvas.set_pixel(cx - dx, cy + dy, r, g, b)
        canvas.set_pixel(cx + dx, cy - dy, r, g, b)
        canvas.set_pixel(cx - dx, cy - dy, r, g, b)
        canvas.set_pixel(cx + dy, cy + dx, r, g, b)
        canvas.set_pixel(cx - dy, cy + dx, r, g, b)
        canvas.set_pixel(cx + dy, cy - dx, r, g, b)
        canvas.set_pixel(cx - dy, cy - dx, r, g, b)

    x, y = 0, radius
    d = 3 - 2 * radius
    while x <= y:
        _plot8(x, y)
        if d < 0:
            d += 4 * x + 6
        else:
            d += 4 * (x - y) + 10
            y -= 1
        x += 1


def draw_square(canvas, x0: int, y0: int, x1: int, y1: int, colour) -> None:
    r, g, b = colour.red, colour.green, colour.blue
    left, right = (x0, x1) if x0 <= x1 else (x1, x0)
    top, bottom = (y0, y1) if y0 <= y1 else (y1, y0)
    for x in range(left, right):
        draw_line(canvas, x, top, x, bottom, Colour(r, g, b))

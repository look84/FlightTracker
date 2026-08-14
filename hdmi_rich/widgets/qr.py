"""
QR-code widget - render a URL as a pygame surface.

Cached per (URL, module_size) so we don't rebuild the qrcode/pygame
surface every frame.  Draws with amber "quiet zone" chrome around the
code so it lands on-theme even against a black background.
"""

from __future__ import annotations

_cache: dict[tuple[str, int], "pygame.Surface"] = {}


def surface(url: str, module_pixels: int = 10):
    """Return a pygame.Surface with the QR code for *url*, cached."""
    import pygame
    import qrcode
    from qrcode.constants import ERROR_CORRECT_L

    key = (url, module_pixels)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_L,
        box_size=module_pixels,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    size = cols * module_pixels

    surf = pygame.Surface((size, size))
    surf.fill((255, 255, 255))
    for r, row in enumerate(matrix):
        for c, cell in enumerate(row):
            if cell:
                pygame.draw.rect(
                    surf,
                    (0, 0, 0),
                    (c * module_pixels, r * module_pixels, module_pixels, module_pixels),
                )
    _cache[key] = surf
    return surf

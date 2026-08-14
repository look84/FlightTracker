"""
Cached scene chrome.

Every scene has a lot of static content per frame - block outlines,
chip labels, radar grid rings, az-el ticks, table column headers.
Rendering those anew each frame is the biggest single per-frame
cost after clearing the surface.

``SceneChrome`` renders the static bits into a background surface
exactly once and blits it every frame afterwards.  Scenes only pay
the render cost the first time each scene draws; from then on it's
one full-surface blit + the dynamic (per-frame) draws on top.

Cache is intentionally never invalidated by ``on_enter()`` - the
chrome doesn't depend on scene visit state.  Only recreate a scene
instance to force a rebuild.
"""

from __future__ import annotations


class SceneChrome:
    """Lazily-rendered static background for one scene."""

    def __init__(self):
        self._surface = None

    def get(self, target_surface, render_fn):
        """Return the cached chrome surface (rendered on first call)."""
        import pygame

        if self._surface is None:
            size = target_surface.get_size()
            bg = pygame.Surface(size)
            bg.fill((0, 0, 0))
            render_fn(bg)
            # Convert to display pixel format so per-frame blits are fast.
            try:
                self._surface = bg.convert()
            except Exception:
                self._surface = bg
        return self._surface

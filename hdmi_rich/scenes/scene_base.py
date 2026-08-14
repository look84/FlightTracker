"""
Shared base for rich scenes.

Modelled on the existing SceneManager contract in utilities/scene_manager.py:
scenes expose has_data() so the manager can pick the highest-priority
scene with something to show; draw(screen, t) is called every frame.
"""

from __future__ import annotations


class RichScene:
    """Abstract scene.  Subclasses set priority + implement has_data/draw."""

    priority: int = 0

    def has_data(self) -> bool:
        return False

    def on_enter(self) -> None:
        """Called once when the manager transitions into this scene."""

    def draw(self, screen, t: float) -> None:  # noqa: ARG002
        raise NotImplementedError


class RichSceneManager:
    """Picks the highest-priority scene with data each frame; falls back
    to scenes[0] when nobody has data (typical idle behaviour)."""

    def __init__(self, scenes: list[RichScene]):
        self.scenes = sorted(scenes, key=lambda s: s.priority)
        self._current: RichScene | None = None

    def pick(self) -> RichScene:
        winner = None
        for scene in self.scenes:
            if scene.has_data():
                if winner is None or scene.priority > winner.priority:
                    winner = scene
        if winner is None:
            winner = self.scenes[0]
        if winner is not self._current:
            self._current = winner
            winner.on_enter()
        return winner

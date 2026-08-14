"""
Rich HDMI UI - parallel to display/ for physical LED-matrix panels.

Booted via ``FLIGHTTRACKER_PANEL=hdmi-rich`` (fullscreen) or
``hdmi-rich-window`` (dev).  Reuses ``utilities/*`` data providers and
``setup.configuration.Config`` verbatim; renders at a fixed 1920x1080
virtual resolution scaled to native at present time.

Public surface: ``run_rich(cfg, fullscreen=True)`` - main entry called
from ``flight-tracker.py`` when the panel selector is rich mode.
"""

from __future__ import annotations


def run_rich(cfg, fullscreen: bool = True) -> None:
    from hdmi_rich.app import RichDisplay

    RichDisplay(cfg, fullscreen=fullscreen).run()

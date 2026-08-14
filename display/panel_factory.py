"""
Panel factory - selects the appropriate RGBPanel driver at runtime.

Tries to import the piomatter (Pi 5) driver first; if unavailable, falls back
to the rgbmatrix (Pi 3/4) driver. The selected panel is cached as a singleton.

On desktop machines where neither hardware driver is available, the pygame
simulator is used as a final fallback so the app always runs.

Setting ``FLIGHTTRACKER_PANEL=hdmi`` opts in to the HDMI LCD driver instead,
bypassing the auto-detected LED matrix drivers.
"""

import importlib
import os

_panel = None


def get_panel():
    """Return the singleton RGBPanel instance, creating it if needed."""
    global _panel
    if _panel is not None:
        return _panel

    # Explicit HDMI opt-in - bypass the LED matrix drivers entirely.
    # 'hdmi'        -> fullscreen (kiosk / real HDMI monitor)
    # 'hdmi-window' -> resizable window (desktop dev)
    panel_type = os.environ.get("FLIGHTTRACKER_PANEL", "").lower()
    if panel_type in ("hdmi", "hdmi-window"):
        mod = importlib.import_module("display.rgbpanel_hdmi")
        _panel = mod.HDMIPanel(fullscreen=(panel_type == "hdmi"))
        return _panel

    # Try Pi 5 driver first
    try:
        mod = importlib.import_module("display.rgbpanel_piomatter")
        _panel = mod.PiomatterPanel()
        return _panel
    except ImportError:
        pass

    # Fall back to Pi 3/4 driver
    try:
        mod = importlib.import_module("display.rgbpanel_rgbmatrix")
        _panel = mod.RGBMatrixPanel()
        return _panel
    except ImportError:
        pass

    # Final fallback: desktop pygame simulator
    try:
        mod = importlib.import_module("display.rgbpanel_simulator")
        _panel = mod.SimulatorPanel()
        return _panel
    except ImportError:
        pass

    raise ImportError(
        "No RGB panel driver available. "
        "Install adafruit-blinka-raspberry-pi5-piomatter (Pi 5), "
        "rgbmatrix (Pi 3/4), or pygame (desktop simulator). "
        "See platforms/ for platform-specific requirements files."
    )


def reset_panel():
    """Clear the cached panel (used for testing)."""
    global _panel
    _panel = None

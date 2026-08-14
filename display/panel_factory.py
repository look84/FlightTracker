"""
Panel factory - selects the appropriate RGBPanel driver at runtime.

Tries to import the piomatter (Pi 5) driver first; if unavailable, falls back
to the rgbmatrix (Pi 3/4) driver. The selected panel is cached as a singleton.

On desktop machines where neither hardware driver is available, the pygame
simulator is used as a final fallback so the app always runs.

Setting ``FLIGHTTRACKER_PANEL=hdmi`` opts in to the HDMI LCD driver instead,
bypassing the auto-detected LED matrix drivers.  ``hdmi-rich`` and
``hdmi-rich-window`` don't return a panel at all - ``is_rich_mode()`` lets
callers branch into the parallel ``hdmi_rich`` UI instead.
"""

import importlib
import os

_panel = None


def is_rich_mode() -> bool:
    """True when the CLI/env has opted into the parallel rich HDMI UI."""
    return os.environ.get("FLIGHTTRACKER_PANEL", "").lower() in (
        "hdmi-rich",
        "hdmi-rich-window",
    )


def rich_fullscreen() -> bool:
    """True when rich mode should boot fullscreen (vs a resizable dev window)."""
    return os.environ.get("FLIGHTTRACKER_PANEL", "").lower() == "hdmi-rich"


def get_panel():
    """Return the singleton RGBPanel instance, creating it if needed."""
    global _panel
    if _panel is not None:
        return _panel

    if is_rich_mode():
        raise RuntimeError(
            "Rich HDMI mode has no RGBPanel - callers should check "
            "panel_factory.is_rich_mode() and branch into hdmi_rich.run_rich() instead."
        )

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

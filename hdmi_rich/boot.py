"""
Boot-phase helpers for the rich HDMI display.

Runs the same connectivity checks as the classic boot sequence, writing
their results into a shared *state* dict that the loading scene reads on
each frame.  This lets the render loop stay smooth while checks run in
the background.
"""

from __future__ import annotations

import socket


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def check_data_source(cfg) -> bool:
    import requests

    try:
        if cfg.data_source == "fr24":
            requests.get(
                "https://data-cloud.flightradar24.com/zones/fcgi/feed.js", timeout=5
            )
        elif cfg.data_source == "osn":
            requests.get("https://opensky-network.org/api/states/all", timeout=5)
        elif cfg.data_source == "tar1090":
            if not cfg.tar1090_url:
                return False
            requests.get(cfg.tar1090_url, timeout=5)
        else:
            return False
        return True
    except Exception:
        return False


def check_celestrack() -> bool:
    import requests

    try:
        requests.get("https://celestrak.org/NORAD/elements/gp.php", timeout=5)
        return True
    except Exception:
        return False


def check_routing_reachable(cfg) -> bool:
    from utilities import route_providers

    route_providers.set_aerodatabox_key(cfg.aerodatabox_api_key)
    return route_providers.check_routing()


def check_weather(cfg) -> bool:
    """Verify the WeatherAPI endpoint is reachable with the configured key.

    Returns True on HTTP 200, False on any other status or on network / URL
    error.  When no key is configured the caller should short-circuit to
    the "OFF" state without calling this.
    """
    import requests

    try:
        resp = requests.get(
            "http://api.weatherapi.com/v1/current.json",
            params={"key": cfg.weatherapi_key, "q": f"{cfg.observer_lat},{cfg.observer_lng}"},
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


def run_checks(cfg, state: dict) -> None:
    """Populate *state* with the results of each connectivity check.

    Called from a background thread so the render loop stays responsive.
    Each check writes to state as it completes.
    """
    state["message"] = "CHECKING LOCAL NETWORK..."
    state["ip"] = local_ip()

    state["message"] = "CHECKING DATA SOURCE..."
    state["data_source"] = "OK" if check_data_source(cfg) else "FAIL"

    if getattr(cfg, "satellite_tracking_enabled", False):
        state["message"] = "CHECKING TLE SOURCE..."
        state["tle"] = "OK" if check_celestrack() else "FAIL"
    else:
        state["tle"] = "OFF"

    if cfg.data_source == "fr24":
        state["route"] = "N/A"
    else:
        state["message"] = "CHECKING ROUTE PROVIDERS..."
        try:
            state["route"] = "OK" if check_routing_reachable(cfg) else "FAIL"
        except Exception:
            state["route"] = "FAIL"

    if not getattr(cfg, "weatherapi_key", ""):
        state["weather"] = "OFF"
    else:
        state["message"] = "CHECKING WEATHER SOURCE..."
        try:
            state["weather"] = "OK" if check_weather(cfg) else "FAIL"
        except Exception:
            state["weather"] = "FAIL"

    state["message"] = "READY"
    state["checks_done"] = True

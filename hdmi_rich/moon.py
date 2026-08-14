"""
Local moon-phase computation.

WeatherAPI's astro block populates ``moon_phase`` + ``moon_illumination``
on paid plans; on the free plan those fields sometimes come back empty.
Compute them locally so the idle scene's ASTRO block always has
something to show.

Uses a simple mean-lunation approximation from a known new-moon epoch.
Accuracy is +/- a few hours which is fine for a display readout.
"""

from __future__ import annotations

import datetime as _dt

# 2000-01-06 18:14:00 UTC was a new moon; synodic month = 29.530588853 days.
_NEW_MOON_EPOCH = _dt.datetime(2000, 1, 6, 18, 14, 0)
_SYNODIC_DAYS = 29.530588853


def moon_phase_illumination(when: _dt.datetime | None = None) -> tuple[str, int]:
    """Return ``(phase_name, illumination_percent)`` for *when* (UTC).

    Defaults to now.  ``illumination_percent`` is 0 at new moon, 100 at
    full moon, and back to 0 at the next new moon.
    """
    if when is None:
        when = _dt.datetime.utcnow()

    days = (when - _NEW_MOON_EPOCH).total_seconds() / 86400.0
    phase_frac = (days % _SYNODIC_DAYS) / _SYNODIC_DAYS

    # Illumination goes 0 -> 100 -> 0 across the cycle.
    if phase_frac <= 0.5:
        illum = int(round(phase_frac * 2 * 100))
    else:
        illum = int(round((1 - phase_frac) * 2 * 100))

    # 8-phase name buckets.
    if phase_frac < 0.03 or phase_frac >= 0.97:
        name = "New Moon"
    elif phase_frac < 0.22:
        name = "Waxing Crescent"
    elif phase_frac < 0.28:
        name = "First Quarter"
    elif phase_frac < 0.47:
        name = "Waxing Gibbous"
    elif phase_frac < 0.53:
        name = "Full Moon"
    elif phase_frac < 0.72:
        name = "Waning Gibbous"
    elif phase_frac < 0.78:
        name = "Last Quarter"
    else:
        name = "Waning Crescent"

    return name, illum

"""
Geographic helpers for the rich flight scene.

Compact great-circle bearing + distance and a closest-approach ETA
computation for radar and telemetry.  All angles in degrees, distances
in kilometres, speeds in knots.
"""

from __future__ import annotations

import math

EARTH_R_KM = 6371.0


def bearing_and_distance(
    obs_lat: float,
    obs_lng: float,
    tgt_lat: float,
    tgt_lng: float,
) -> tuple[float, float]:
    """Return (bearing_deg_from_observer, distance_km).

    Bearing measured clockwise from true north.  Uses the initial-bearing
    formula and the haversine great-circle distance.
    """
    lat1 = math.radians(obs_lat)
    lat2 = math.radians(tgt_lat)
    dlng = math.radians(tgt_lng - obs_lng)

    # Initial bearing
    y = math.sin(dlng) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlng)
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

    # Haversine distance
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    c = 2 * math.asin(min(1.0, math.sqrt(a)))
    dist_km = EARTH_R_KM * c

    return bearing, dist_km


def eta_closest_approach_seconds(
    obs_lat: float,
    obs_lng: float,
    ac_lat: float,
    ac_lng: float,
    heading_deg: float,
    ground_speed_kts: float,
) -> float | None:
    """Time (seconds) until the aircraft is at its closest point to the observer.

    Returns None if the aircraft is receding (t < 0), stationary, or the
    inputs don't make sense.

    Uses a flat-earth approximation (equirectangular projection centred
    at the observer) - accurate at the ~20 km ranges the flight scene
    cares about, and cheap enough to run per frame.
    """
    if ground_speed_kts is None or ground_speed_kts <= 0:
        return None

    # Convert positions to local ENU-like metres.  1 deg lat ~= 111 km.
    cos_lat = math.cos(math.radians(obs_lat))
    ac_x = (ac_lng - obs_lng) * 111_000.0 * cos_lat
    ac_y = (ac_lat - obs_lat) * 111_000.0
    # Aircraft velocity in the same frame - heading measured from north,
    # clockwise; sin -> east/x, cos -> north/y.
    h = math.radians(heading_deg)
    v = ground_speed_kts * 0.514444  # kt -> m/s
    vx = v * math.sin(h)
    vy = v * math.cos(h)

    # Observer is at (0, 0) in this frame; closest approach when the
    # observer-to-aircraft vector is perpendicular to velocity.
    # t = -(pos . vel) / |vel|^2
    v_sq = vx * vx + vy * vy
    if v_sq <= 0:
        return None
    dot = ac_x * vx + ac_y * vy
    t = -dot / v_sq
    if t < 0:
        return None  # already past closest approach
    return t

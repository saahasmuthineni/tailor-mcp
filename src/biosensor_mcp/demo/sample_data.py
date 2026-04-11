"""
Synthetic run data for demo mode.

Generates a realistic 60-minute, ~7-mile run with:
  - HR drifting from ~148 to ~164 with noise (aerobic drift pattern)
  - Velocity ~3.0 m/s with mild fade and variation
  - Grade oscillating +/- 3% (rolling hills)
  - GPS tracing a loop from a real-looking start point
  - Distance accumulating from velocity
  - Altitude tracking grade changes

All generated with stdlib math — no numpy or external deps.
"""

import math
import random

SAMPLE_ACTIVITY_ID = 99_999_999

# Seed for reproducibility across demo runs
_RNG = random.Random(42)


def _generate_hr(n: int) -> list[int]:
    """HR starting ~148, drifting to ~164 with mild noise."""
    base = 148
    drift_per_sec = 16.0 / n  # total 16 bpm drift over the run
    hr = []
    for i in range(n):
        target = base + drift_per_sec * i
        noise = _RNG.gauss(0, 2.5)
        hr.append(max(80, min(200, int(round(target + noise)))))
    return hr


def _generate_velocity(n: int) -> list[float]:
    """Velocity ~3.0 m/s with slight fade and per-second variation."""
    vel = []
    for i in range(n):
        base = 3.05 - 0.15 * (i / n)  # slight negative split fade
        noise = _RNG.gauss(0, 0.12)
        vel.append(max(0.0, round(base + noise, 2)))
    return vel


def _generate_grade(n: int) -> list[float]:
    """Rolling hills: sine wave +/- 3%."""
    return [round(3.0 * math.sin(2 * math.pi * i / 600), 1) for i in range(n)]


def _generate_altitude(grade: list[float], start_alt: float = 45.0) -> list[float]:
    """Integrate grade to get altitude profile."""
    alt = [start_alt]
    for g in grade[1:]:
        # grade% over 1 second at ~3 m/s ≈ 0.03 * g meters
        delta = 0.03 * g
        alt.append(round(alt[-1] + delta, 1))
    return alt


def _generate_latlng(n: int) -> list[list[float]]:
    """Trace a rough loop from a starting point."""
    lat, lng = 42.3601, -71.0589  # Boston Common area
    points = []
    radius = 0.012  # ~1.3 km radius loop
    for i in range(n):
        angle = 2 * math.pi * i / n
        noise_lat = _RNG.gauss(0, 0.00005)
        noise_lng = _RNG.gauss(0, 0.00005)
        points.append([
            round(lat + radius * math.sin(angle) + noise_lat, 5),
            round(lng + radius * math.cos(angle) + noise_lng, 5),
        ])
    return points


def generate_sample_streams(duration_seconds: int = 3600) -> dict:
    """Generate all 8 stream types for a synthetic run."""
    n = duration_seconds
    velocity = _generate_velocity(n)
    grade = _generate_grade(n)

    # Distance from cumulative velocity
    distance = [0.0]
    for v in velocity[1:]:
        distance.append(round(distance[-1] + v, 1))

    time_arr = list(range(n))
    moving = [v > 0.5 for v in velocity]

    return {
        "heartrate": _generate_hr(n),
        "velocity_smooth": velocity,
        "latlng": _generate_latlng(n),
        "altitude": _generate_altitude(grade),
        "grade_smooth": grade,
        "distance": distance,
        "time": time_arr,
        "moving": moving,
    }


def generate_sample_activity() -> dict:
    """Generate a Strava-like activity summary dict."""
    return {
        "id": SAMPLE_ACTIVITY_ID,
        "name": "Demo: Thursday Recovery Run",
        "type": "Run",
        "start_date": "2026-04-09T07:30:00Z",
        "distance": 10890.0,  # ~6.77 miles
        "moving_time": 3600,
        "elapsed_time": 3720,
        "average_speed": 3.025,
        "average_heartrate": 156,
        "max_heartrate": 178,
        "total_elevation_gain": 52.0,
        "calories": 680,
        "description": "Easy recovery run, felt smooth.",
    }

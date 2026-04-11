"""
Running Child — Server-Side Analytics
=======================================
All running-specific computations happen here.
Raw per-second data stays on the server; only computed metrics reach Claude.

This is the running domain's Processing class. Other biosensor domains
(CGM, sleep, ECG) would have their own with domain-specific analytics:
  - CGM: time-in-range, glycemic variability, meal response curves
  - Sleep: stage duration, efficiency, latency, fragmentation
  - ECG: rhythm classification, HRV metrics, QT intervals
"""

import math
from typing import Optional

DEFAULT_MAX_HR = 195
DEFAULT_RESTING_HR = 60


class RunningProcessing:
    """
    Running analytics engine. All methods are stateless pure functions.

    Domain-specific: decoupling, efficiency factor, GAP, mile splits,
    HR zones, phase detection, anomaly detection, stop detection.
    """

    # ═══════════════════════════════════════════════════════════
    # PRECISION REDUCTION
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def reduce_precision(streams: dict) -> dict:
        """
        Reduce numeric precision per data type.

        GPS      → 5 decimals  (1.1m accuracy, tighter than GPS hardware)
        velocity → 2 decimals  (loses 0.005 m/s — undetectable)
        altitude → integer     (sub-meter irrelevant for running)
        distance → integer     (sub-meter irrelevant for splits)
        grade    → 1 decimal   (preserved — protects GAP calculations)
        heartrate, time, moving → unchanged (already low-precision)
        """
        reducers = {
            "latlng": lambda vals: [[round(lat, 5), round(lng, 5)] for lat, lng in vals],
            "velocity_smooth": lambda vals: [round(v, 2) for v in vals],
            "altitude": lambda vals: [int(round(v)) for v in vals],
            "distance": lambda vals: [int(round(v)) for v in vals],
            "grade_smooth": lambda vals: [round(v, 1) for v in vals],
        }
        return {
            key: reducers[key](values) if key in reducers else values
            for key, values in streams.items()
        }

    # ═══════════════════════════════════════════════════════════
    # DOWNSAMPLING
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def downsample(streams: dict, interval: int = 10) -> dict:
        """
        Sample every N seconds. For a 15mi run (~8600 points):
          10s → ~860 points
          15s → ~577 points
        Preserves curve fidelity for visualization.
        """
        if "time" not in streams:
            return streams

        time_arr = streams["time"]
        n = len(time_arr)
        if n == 0:
            return streams

        indices = [0]
        last_time = time_arr[0]
        for i in range(1, n):
            if time_arr[i] - last_time >= interval:
                indices.append(i)
                last_time = time_arr[i]
        if indices[-1] != n - 1:
            indices.append(n - 1)

        return {key: [values[i] for i in indices] for key, values in streams.items()}

    # ═══════════════════════════════════════════════════════════
    # STREAM FILTERING
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def filter_streams(streams: dict, requested: Optional[list[str]] = None) -> dict:
        """Only return requested streams. Default: all."""
        if not requested:
            return streams
        return {k: v for k, v in streams.items() if k in requested}

    # ═══════════════════════════════════════════════════════════
    # TOKEN ESTIMATION (cheap, pre-execution)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def estimate_stream_tokens(streams: dict, requested: Optional[list[str]] = None) -> int:
        """
        Estimate tokens for a stream payload WITHOUT serializing.

        Heuristic: count data points x avg chars per value type.
        Much cheaper than building + measuring the full JSON.
        """
        if requested:
            streams = {k: v for k, v in streams.items() if k in requested}

        CHAR_ESTIMATES = {
            "latlng": 24,           # "[42.12345, -71.12345]"
            "heartrate": 5,         # "160"
            "altitude": 5,          # "125"
            "distance": 6,          # "12345"
            "velocity_smooth": 6,   # "3.45"
            "grade_smooth": 5,      # "-2.1"
            "moving": 6,            # "true"
            "time": 6,              # "3600"
        }

        total_chars = sum(
            len(values) * CHAR_ESTIMATES.get(key, 8)
            for key, values in streams.items()
        )

        # JSON structure overhead ~20%
        return int(total_chars * 1.2) // 4

    # ═══════════════════════════════════════════════════════════
    # HR ANALYTICS
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def compute_hr_zones(
        hr_data: list[int], max_hr: int = DEFAULT_MAX_HR, resting_hr: int = DEFAULT_RESTING_HR
    ) -> dict:
        """
        Zone distribution from per-second HR data.

        Uses configurable max_hr — hardcoded 195 doesn't work for everyone.
        Zone boundaries: 60%, 70%, 80%, 90%, 100% of max HR.
        """
        zones = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        boundaries = [0.6, 0.7, 0.8, 0.9, 1.0]

        for hr in hr_data:
            pct = hr / max_hr
            assigned = False
            for z, upper in enumerate(boundaries, 1):
                if pct <= upper:
                    zones[z] += 1
                    assigned = True
                    break
            if not assigned:
                zones[5] += 1

        total = len(hr_data) or 1
        return {
            "zone_seconds": zones,
            "zone_pct": {z: round(s / total * 100, 1) for z, s in zones.items()},
            "avg_hr": round(sum(hr_data) / total) if hr_data else 0,
            "max_hr_observed": max(hr_data) if hr_data else 0,
            "min_hr": min(hr_data) if hr_data else 0,
            "max_hr_setting": max_hr,
        }

    @staticmethod
    def compute_hr_drift(hr_data: list[int]) -> dict:
        """HR drift: compare first-half avg to second-half avg."""
        if len(hr_data) < 60:
            return {"drift_pct": 0, "note": "Activity too short for drift analysis"}

        mid = len(hr_data) // 2
        first_half = sum(hr_data[:mid]) / mid
        second_half = sum(hr_data[mid:]) / (len(hr_data) - mid)
        drift = ((second_half - first_half) / first_half) * 100

        return {
            "first_half_avg": round(first_half),
            "second_half_avg": round(second_half),
            "drift_pct": round(drift, 1),
            "interpretation": (
                "aerobic"
                if drift < 5
                else "moderate drift"
                if drift < 10
                else "significant drift"
            ),
        }

    # ═══════════════════════════════════════════════════════════
    # PACE ANALYTICS
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def compute_mile_splits(
        distance: list, time_arr: list, velocity: Optional[list] = None
    ) -> list[dict]:
        """Mile splits from per-second distance data."""
        MILE_M = 1609.34
        splits = []
        mile_num = 1
        mile_start_idx = 0
        mile_start_time = time_arr[0] if time_arr else 0

        for i in range(1, len(distance)):
            miles_covered = distance[i] / MILE_M
            if miles_covered >= mile_num:
                elapsed = time_arr[i] - mile_start_time
                pace_min = elapsed / 60
                pace_str = f"{int(pace_min)}:{int((pace_min % 1) * 60):02d}"

                split: dict = {
                    "mile": mile_num,
                    "elapsed_seconds": elapsed,
                    "pace": pace_str,
                }
                if velocity:
                    seg_vel = velocity[mile_start_idx : i + 1]
                    split["avg_velocity_ms"] = (
                        round(sum(seg_vel) / len(seg_vel), 2) if seg_vel else 0
                    )

                splits.append(split)
                mile_num += 1
                mile_start_idx = i
                mile_start_time = time_arr[i]

        # Final partial mile
        if distance and distance[-1] / MILE_M > mile_num - 1:
            remaining_dist = distance[-1] - (mile_num - 1) * MILE_M
            elapsed = time_arr[-1] - mile_start_time
            if remaining_dist > 100 and elapsed > 0:
                pace_per_mile = (elapsed / remaining_dist) * MILE_M
                pace_min = pace_per_mile / 60
                splits.append(
                    {
                        "mile": f"{mile_num} (partial, {remaining_dist:.0f}m)",
                        "elapsed_seconds": elapsed,
                        "pace": f"{int(pace_min)}:{int((pace_min % 1) * 60):02d}",
                    }
                )

        return splits

    @staticmethod
    def compute_gap_splits(
        velocity: list, grade: list, distance: list, time_arr: list
    ) -> list[dict]:
        """
        Grade Adjusted Pace mile splits.
        GAP adjustment: cost = 1 + 0.03 * grade%
        This is why grade precision is preserved at 1 decimal.
        """
        if not grade or not velocity:
            return []

        gap_velocity = []
        for v, g in zip(velocity, grade):
            cost = 1 + 0.03 * g
            gap_velocity.append(v / cost if cost != 0 else v)

        return RunningProcessing.compute_mile_splits(distance, time_arr, gap_velocity)

    # ═══════════════════════════════════════════════════════════
    # DECOUPLING & EFFICIENCY
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def compute_decoupling(hr_data: list, velocity: list) -> dict:
        """
        Aerobic decoupling: HR:pace ratio first half vs second half.
        <5% = well coupled, 5-10% = moderate, >10% = decoupled.
        """
        n = min(len(hr_data), len(velocity))
        if n < 120:
            return {
                "decoupling_pct": 0,
                "note": "Too short for decoupling analysis",
            }

        mid = n // 2
        hr1 = sum(hr_data[:mid]) / mid
        hr2 = sum(hr_data[mid:n]) / (n - mid)
        vel1 = sum(velocity[:mid]) / mid
        vel2 = sum(velocity[mid:n]) / (n - mid)

        if vel1 == 0 or vel2 == 0:
            return {"decoupling_pct": 0, "note": "Zero velocity detected"}

        ratio1 = hr1 / vel1
        ratio2 = hr2 / vel2
        decoupling = ((ratio2 - ratio1) / ratio1) * 100

        return {
            "decoupling_pct": round(decoupling, 1),
            "first_half": {"avg_hr": round(hr1), "avg_velocity": round(vel1, 2)},
            "second_half": {"avg_hr": round(hr2), "avg_velocity": round(vel2, 2)},
            "interpretation": (
                "well coupled"
                if abs(decoupling) < 5
                else "moderate"
                if abs(decoupling) < 10
                else "decoupled"
            ),
        }

    @staticmethod
    def compute_efficiency_factor(
        hr_data: list, velocity: list, grade: Optional[list] = None
    ) -> dict:
        """EF = normalized pace / avg HR. Higher = more efficient."""
        if not hr_data or not velocity:
            return {"ef": 0}
        avg_hr = sum(hr_data) / len(hr_data)
        avg_vel = sum(velocity) / len(velocity)
        if avg_hr == 0:
            return {"ef": 0}
        if avg_vel > 0:
            pace_min_mile = (1609.34 / avg_vel) / 60
            ef = pace_min_mile / avg_hr * 1000
        else:
            ef = 0
        return {
            "ef": round(ef, 2),
            "avg_hr": round(avg_hr),
            "avg_velocity_ms": round(avg_vel, 2),
        }

    # ═══════════════════════════════════════════════════════════
    # PHASE DETECTION
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def detect_run_phases(velocity: list, time_arr: list) -> list[dict]:
        """Detect warmup / steady / tempo / cooldown phases from velocity."""
        if not velocity or not time_arr:
            return [{"phase": "no_data", "note": "No velocity or time data available"}]
        if len(velocity) < 120:
            return [
                {"phase": "too_short", "note": "Activity too short for phase detection"}
            ]

        # Smooth velocity with 30s rolling average
        window = 30
        smoothed = []
        for i in range(len(velocity)):
            start = max(0, i - window // 2)
            end = min(len(velocity), i + window // 2)
            smoothed.append(sum(velocity[start:end]) / (end - start))

        avg_vel = sum(smoothed) / len(smoothed)
        phases = []
        current_phase = None
        phase_start = 0

        for i, vel in enumerate(smoothed):
            if vel < avg_vel * 0.8:
                phase = "easy"
            elif vel < avg_vel * 1.05:
                phase = "steady"
            elif vel < avg_vel * 1.15:
                phase = "tempo"
            else:
                phase = "fast"

            if phase != current_phase:
                if current_phase is not None and i - phase_start >= 30:
                    phases.append(
                        {
                            "phase": current_phase,
                            "start_seconds": time_arr[phase_start]
                            if time_arr
                            else phase_start,
                            "end_seconds": time_arr[i] if time_arr else i,
                            "duration_seconds": (time_arr[i] - time_arr[phase_start])
                            if time_arr
                            else (i - phase_start),
                            "avg_velocity": round(
                                sum(velocity[phase_start:i]) / (i - phase_start), 2
                            ),
                        }
                    )
                current_phase = phase
                phase_start = i

        # Final phase
        if current_phase and len(velocity) - phase_start >= 30:
            phases.append(
                {
                    "phase": current_phase,
                    "start_seconds": time_arr[phase_start]
                    if time_arr
                    else phase_start,
                    "end_seconds": time_arr[-1] if time_arr else len(velocity) - 1,
                    "duration_seconds": (time_arr[-1] - time_arr[phase_start])
                    if time_arr
                    else (len(velocity) - phase_start),
                    "avg_velocity": round(
                        sum(velocity[phase_start:]) / (len(velocity) - phase_start), 2
                    ),
                }
            )

        return phases

    # ═══════════════════════════════════════════════════════════
    # ANOMALY DETECTION
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def detect_anomalies(hr_data: list, velocity: list) -> list[dict]:
        """
        Flag suspicious sensor data:
        - HR flatline: same value 60+ consecutive seconds (wrist-lock artifact)
        - HR spike: >30 bpm change in 5 seconds (sensor catchup)
        """
        anomalies = []

        if hr_data:
            # Flatline detection
            run_val = hr_data[0]
            run_len = 1
            for i in range(1, len(hr_data)):
                if hr_data[i] == run_val:
                    run_len += 1
                else:
                    if run_len >= 60:
                        anomalies.append(
                            {
                                "type": "hr_flatline",
                                "value": run_val,
                                "start_second": i - run_len,
                                "duration_seconds": run_len,
                                "note": f"HR locked at {run_val} for {run_len}s — likely sensor artifact",
                            }
                        )
                    run_val = hr_data[i]
                    run_len = 1
            if run_len >= 60:
                anomalies.append(
                    {
                        "type": "hr_flatline",
                        "value": run_val,
                        "start_second": len(hr_data) - run_len,
                        "duration_seconds": run_len,
                        "note": f"HR locked at {run_val} for {run_len}s — likely sensor artifact",
                    }
                )

            # Spike detection — 30-second cooldown prevents one bad sensor
            # burst from generating dozens of overlapping anomaly entries (#11)
            last_spike_second = -30
            for i in range(5, len(hr_data)):
                if i - last_spike_second < 30:
                    continue
                delta = abs(hr_data[i] - hr_data[i - 5])
                if delta > 30:
                    anomalies.append(
                        {
                            "type": "hr_spike",
                            "second": i,
                            "from_hr": hr_data[i - 5],
                            "to_hr": hr_data[i],
                            "delta": delta,
                            "note": "Rapid HR change — sensor catchup or artifact",
                        }
                    )
                    last_spike_second = i

        return anomalies

    # ═══════════════════════════════════════════════════════════
    # STOP DETECTION
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def detect_stops(
        latlng: list,
        velocity: list,
        time_arr: list,
        home_coords: Optional[tuple] = None,
    ) -> list[dict]:
        """Detect stops using GPS + velocity. Optionally flag home-base stops.

        Stop classifications (#10):
          - "brief"      < 30s  — traffic light, quick look at watch
          - "short"     30–120s — fuel/gel, tie laces
          - "extended"  > 120s  — water fountain, bathroom, conversation
        """
        # 0.5 m/s threshold (#9): 0.3 was too aggressive, flagging slow shuffles
        # near the end of hard efforts. 0.5 m/s (~1.8 km/h) is a reliable
        # "completely stopped" signal without false positives.
        VEL_THRESHOLD = 0.5  # m/s

        stops = []
        in_stop = False
        stop_start = 0

        for i in range(len(velocity)):
            if velocity[i] < VEL_THRESHOLD:
                if not in_stop:
                    in_stop = True
                    stop_start = i
            else:
                if in_stop:
                    duration = (
                        time_arr[i] - time_arr[stop_start]
                        if time_arr
                        else i - stop_start
                    )
                    if duration >= 10:  # Minimum 10s to count
                        # Classify by duration
                        if duration < 30:
                            classification = "brief"
                        elif duration < 120:
                            classification = "short"
                        else:
                            classification = "extended"

                        stop: dict = {
                            "stop_number": len(stops) + 1,
                            "start_second": time_arr[stop_start]
                            if time_arr
                            else stop_start,
                            "end_second": time_arr[i] if time_arr else i,
                            "duration_seconds": duration,
                            "classification": classification,
                        }
                        if latlng and stop_start < len(latlng):
                            stop["location"] = latlng[stop_start]
                            if home_coords:
                                dist = haversine(latlng[stop_start], home_coords)
                                stop["distance_from_home_m"] = round(dist)
                                stop["near_home"] = dist < 50
                        stops.append(stop)
                    in_stop = False

        return stops


def haversine(coord1: list, coord2: tuple) -> float:
    """Distance in meters between two [lat, lng] points."""
    R = 6371000
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))

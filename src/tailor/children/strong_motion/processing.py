"""
Stateless analytics for the strong-motion child.

Every method is a ``@staticmethod`` — no instance state, no I/O, no
PRNG, no clock reads. Per ADR 0008. Acceleration is taken in g
(``accel_g``); ``dt`` is the sample interval in seconds. The standard
gravitational acceleration ``G_MS2`` converts g to m/s² for the
engineering quantities (Arias intensity, spectral acceleration), whose
conventional definitions are stated in SI.

The four record-summary quantities:

* **PGA** — peak ground acceleration, ``max|a|`` in g.
* **Arias intensity** — ``Ia = (π / 2g) ∫ a(t)² dt`` (Arias 1970), with
  ``a`` in m/s² and the integral by the trapezoidal rule; result in m/s.
* **Strong-motion duration** — the 5–95 % significant duration: the
  time between the instants the normalized Arias build-up (Husid plot)
  crosses 5 % and 95 %.
* **Sa(T)** — 5 %-damped pseudo-spectral acceleration, one value per
  oscillator period, via the Nigam–Jennings (1969) exact piecewise
  recurrence for the SDOF response. Reported in g.
"""

from __future__ import annotations

import math
from statistics import fmean, stdev

# Standard gravity, m/s². The g→m/s² conversion factor and the ``g`` in
# the Arias π/2g constant.
G_MS2 = 9.81

# Oscillator periods (seconds) for the response-spectrum summary.
SA_PERIODS = (0.1, 0.2, 0.5, 1.0, 2.0)

# Default viscous damping ratio for the response spectrum (5 %).
DEFAULT_DAMPING = 0.05

# Per-record scalar vocabulary for the cohort summary. Each names a
# quantity the per-record analytics already compute.
RECORD_METRICS = (
    "pga_g",
    "arias_intensity",
    "strong_motion_duration_s",
)


class StrongMotionProcessing:
    """Pure-function strong-motion analytics."""

    # ── primitives ──────────────────────────────────────────────

    @staticmethod
    def _trapezoid(y: list[float], dt: float) -> float:
        """Trapezoidal integral of uniformly-spaced samples ``y`` over ``dt``."""
        if len(y) < 2:
            return 0.0
        return dt * (sum(y) - 0.5 * (y[0] + y[-1]))

    # ── Tier-1 record summary quantities ────────────────────────

    @staticmethod
    def peak_acceleration_g(accel_g: list[float]) -> float | None:
        """PGA: the peak absolute acceleration, in g."""
        if not accel_g:
            return None
        return max(abs(v) for v in accel_g)

    @staticmethod
    def arias_intensity(accel_g: list[float], dt: float) -> float:
        """Arias intensity ``Ia = (π / 2g) ∫ a(t)² dt`` in m/s.

        ``a`` is converted from g to m/s²; the integral is trapezoidal.
        """
        if len(accel_g) < 2 or dt <= 0:
            return 0.0
        a2 = [(v * G_MS2) ** 2 for v in accel_g]
        integral = StrongMotionProcessing._trapezoid(a2, dt)
        return (math.pi / (2.0 * G_MS2)) * integral

    @staticmethod
    def strong_motion_duration(
        accel_g: list[float],
        dt: float,
        low: float = 0.05,
        high: float = 0.95,
    ) -> float:
        """5–95 % significant (Arias) duration, in seconds.

        Builds the cumulative Arias integral (Husid curve), normalizes
        it to [0, 1], and returns the time between the ``low`` and
        ``high`` crossings (default 5 % and 95 %).
        """
        if len(accel_g) < 2 or dt <= 0:
            return 0.0
        a2 = [(v * G_MS2) ** 2 for v in accel_g]
        cumulative = [0.0]
        for i in range(1, len(a2)):
            cumulative.append(cumulative[-1] + dt * 0.5 * (a2[i] + a2[i - 1]))
        total = cumulative[-1]
        if total <= 0:
            return 0.0
        normalized = [c / total for c in cumulative]
        t_low = StrongMotionProcessing._crossing_time(normalized, low, dt)
        t_high = StrongMotionProcessing._crossing_time(normalized, high, dt)
        return round(t_high - t_low, 6)

    @staticmethod
    def _crossing_time(normalized: list[float], frac: float, dt: float) -> float:
        """Time at which the monotone ``normalized`` curve first reaches ``frac``.

        Linearly interpolates between the bracketing samples so the
        duration is not quantized to the sample grid.
        """
        for i in range(1, len(normalized)):
            if normalized[i] >= frac:
                prev, curr = normalized[i - 1], normalized[i]
                span = curr - prev
                if span <= 0:
                    return (i - 1) * dt
                f = (frac - prev) / span
                return (i - 1 + f) * dt
        return (len(normalized) - 1) * dt

    @staticmethod
    def response_spectrum_sa(
        accel_g: list[float],
        dt: float,
        periods: tuple[float, ...] = SA_PERIODS,
        damping: float = DEFAULT_DAMPING,
    ) -> dict[str, float]:
        """5 %-damped pseudo-spectral acceleration Sa(T), in g, per period.

        Uses the Nigam–Jennings (1969) exact piecewise recurrence for the
        SDOF relative-displacement response under the ground-acceleration
        record. ``Sa = ωₙ² · max|u|`` (pseudo-acceleration), reported in g.
        """
        result: dict[str, float] = {}
        for period in periods:
            sd = StrongMotionProcessing._sdof_max_relative_disp(
                accel_g, dt, period, damping,
            )
            wn = 2.0 * math.pi / period
            psa_ms2 = wn * wn * sd  # pseudo-acceleration, m/s²
            result[f"T={period}s"] = round(psa_ms2 / G_MS2, 6)  # -> g
        return result

    @staticmethod
    def _sdof_max_relative_disp(
        accel_g: list[float],
        dt: float,
        period: float,
        damping: float,
    ) -> float:
        """Max |relative displacement| of a 5 %-damped SDOF, in metres.

        Nigam–Jennings exact recurrence for a piecewise-linear ground
        acceleration. The forcing is ``p = -üg`` (üg in m/s²).
        """
        if len(accel_g) < 2 or dt <= 0 or period <= 0:
            return 0.0
        wn = 2.0 * math.pi / period
        z = damping
        wd = wn * math.sqrt(1.0 - z * z)
        e = math.exp(-z * wn * dt)
        s = math.sin(wd * dt)
        c = math.cos(wd * dt)
        zsq = math.sqrt(1.0 - z * z)

        # Displacement recurrence coefficients (Chopra, Dynamics of
        # Structures — exact for piecewise-linear excitation).
        a_coef = e * (z / zsq * s + c)
        b_coef = e * (1.0 / wd * s)
        c_coef = (1.0 / (wn * wn)) * (
            2.0 * z / (wn * dt)
            + e * (
                ((1.0 - 2.0 * z * z) / (wd * dt) - z / zsq) * s
                - (1.0 + 2.0 * z / (wn * dt)) * c
            )
        )
        d_coef = (1.0 / (wn * wn)) * (
            1.0 - 2.0 * z / (wn * dt)
            + e * (
                (2.0 * z * z - 1.0) / (wd * dt) * s
                + 2.0 * z / (wn * dt) * c
            )
        )
        # Velocity recurrence coefficients.
        ap = -e * (wn / zsq * s)
        bp = e * (c - z / zsq * s)
        cp = (1.0 / (wn * wn)) * (
            -1.0 / dt
            + e * ((wn / zsq + z / (dt * zsq)) * s + 1.0 / dt * c)
        )
        dp = (1.0 / (wn * wn)) * (
            1.0 / dt - e / dt * (z / zsq * s + c)
        )

        # Forcing per unit mass: p_i = -üg_i, with üg in m/s².
        p = [-(v * G_MS2) for v in accel_g]

        u = 0.0
        v = 0.0
        max_abs = 0.0
        for i in range(len(p) - 1):
            u_next = a_coef * u + b_coef * v + c_coef * p[i] + d_coef * p[i + 1]
            v_next = ap * u + bp * v + cp * p[i] + dp * p[i + 1]
            u, v = u_next, v_next
            au = abs(u)
            if au > max_abs:
                max_abs = au
        return max_abs

    # ── cohort aggregation ──────────────────────────────────────

    @staticmethod
    def cohort_stats(per_record_scalars: list[float]) -> dict:
        """Aggregate per-record scalars into n / mean / std / min / max."""
        finite = [v for v in per_record_scalars if v is not None]
        if not finite:
            return {"n": 0, "mean": None, "std": None, "min": None, "max": None}
        out: dict = {
            "n": len(finite),
            "mean": round(fmean(finite), 6),
            "min": min(finite),
            "max": max(finite),
        }
        out["std"] = round(stdev(finite), 6) if len(finite) > 1 else 0.0
        return out

    # ── Tier-2 / Tier-3 trace shaping ───────────────────────────

    @staticmethod
    def downsample(series: list[float], interval: int) -> list[float]:
        """Return every Nth element of ``series`` (Tier-2 plotting trace)."""
        if interval < 1:
            raise ValueError("interval must be >= 1")
        return series[::interval]

    @staticmethod
    def reduce_precision(values: list[float], places: int) -> list[float]:
        """Round each element to ``places`` decimals (Tier-3 token trim)."""
        if places < 0:
            raise ValueError("places must be >= 0")
        return [round(v, places) for v in values]

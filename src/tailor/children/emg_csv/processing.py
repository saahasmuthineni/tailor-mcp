"""
EMG-CSV Processing — Pure-Function Time-Domain Analytics
========================================================
Pure-function analytics for surface-EMG envelope traces at
~50–500 Hz.  Every method is a ``@staticmethod`` per ADR 0008.

Most analytics are inherited from ``children.csv_dir.processing``
via direct import — peak detection, ``time_to_50pct_drop_s``,
cohort aggregation already live there and the v6.8.1 peak-tie
fix is the load-bearing reason not to duplicate.  This module
adds EMG-domain time-domain helpers:

- ``rms`` — root-mean-square amplitude over a list of envelope
  samples.  The canonical EMG amplitude measure that's robust
  to the alternating sign of raw EMG (envelopes are already
  rectified, but RMS is what the literature reports).
- ``mean_activation`` — simple mean of the envelope; called MAV
  (mean absolute value) in the EMG literature when applied to
  raw rectified EMG.
- ``integrated_emg`` — area under the envelope (∫|env|·dt) over
  the trace duration.  A common fatigue/effort proxy.
- ``envelope_summary`` — bundles peak-window mean, mean activation,
  iEMG, and a fatigue index (peak-window-vs-end-window decline).
  EMG-domain analog of force_summary's combined report.

Spectral analytics (median frequency shift, mean power frequency)
are explicitly **deferred** — see ``__init__.py`` for the rationale
(stdlib-only posture conflicts with FFT-on-large-traces costs).
"""

from __future__ import annotations

import math
from statistics import fmean, stdev

# Shared analytics — see module docstring for rationale.
from ..csv_dir.processing import (  # noqa: F401
    COHORT_METRICS,
    CSVProcessing,
    _last_peak_index,
)


class EmgCsvProcessing:
    """
    EMG-envelope-specific analytics.  Inherits the generic
    cohort / decline / peak math from ``CSVProcessing`` via
    direct import — only EMG-domain helpers live here.
    """

    @staticmethod
    def rms(values: list[float]) -> float | None:
        """
        Root-mean-square amplitude.  Returns ``None`` for empty
        input.

        For an envelope trace (already rectified), this is
        equivalent to the L2 norm divided by sqrt(n) — the
        canonical EMG amplitude measure cited in fatigue
        literature (Hunter & Senefeld 2024 and predecessors).

        Pure function — same inputs, same output.  No PRNG,
        no clock reads.  Per ADR 0008.
        """
        if not values:
            return None
        return round(math.sqrt(sum(v * v for v in values) / len(values)), 4)

    @staticmethod
    def mean_activation(values: list[float]) -> float | None:
        """
        Simple mean of envelope samples.  EMG literature calls
        this MAV (mean absolute value) when applied to raw
        rectified EMG; on an already-rectified envelope it's
        just the arithmetic mean.

        Returns ``None`` for empty input.
        Pure function per ADR 0008.
        """
        if not values:
            return None
        return round(fmean(values), 4)

    @staticmethod
    def integrated_emg(
        values: list[float], sample_rate_hz: float,
    ) -> float | None:
        """
        Integrated EMG: ∫|envelope|·dt over the trace duration,
        approximated by trapezoidal rule.  Common effort /
        fatigue proxy in EMG fatigue studies.

        Units are envelope-units × seconds; dimensional
        consistency is the caller's responsibility (the value
        is meaningful only relative to other iEMG values from
        the same envelope-extraction pipeline).

        Returns ``None`` for empty input or non-positive
        sample rate.
        Pure function per ADR 0008.
        """
        if not values or sample_rate_hz <= 0:
            return None
        if len(values) < 2:
            return 0.0
        dt = 1.0 / sample_rate_hz
        # Trapezoidal: sum of (v[i] + v[i+1]) / 2 * dt.
        total = sum(
            (values[i] + values[i + 1]) / 2.0 * dt
            for i in range(len(values) - 1)
        )
        return round(total, 4)

    @staticmethod
    def envelope_summary(
        values: list[float],
        sample_rate_hz: float,
        peak_window_ms: float = 250.0,
        end_window_ms: float = 1000.0,
    ) -> dict:
        """
        Combined fatigue diagnostic.  Returns a dict with:

        - ``peak_envelope_window_mean`` — mean envelope over a
          ``peak_window_ms`` window centered on the peak sample
          (analog of force_csv's MVC window mean; same Sánchez-
          2015 250 ms shape).
        - ``mean_activation`` — overall mean.
        - ``rms`` — root-mean-square over the full trace.
        - ``integrated_emg`` — trapezoidal integral.
        - ``end_window_mean`` — mean envelope over the trailing
          ``end_window_ms`` window.
        - ``fatigue_index_pct`` — (peak-window − end-window) /
          peak-window × 100.  Positive values indicate amplitude
          decline (which under sustained-contraction protocols
          can mean *recruitment exhaustion* — though in fresh
          / recovered traces the sign can be reversed; the
          literature-canonical interpretation is protocol-
          dependent and surfacing the raw value lets the
          analyst decide).
        - ``duration_s`` — trace duration.
        - ``n_samples`` — sample count.

        Returns ``{"error": ...}`` for empty input or non-
        positive sample rate.
        Pure function per ADR 0008.
        """
        if not values:
            return {"error": "envelope_summary requires non-empty values"}
        if sample_rate_hz <= 0:
            return {"error": "envelope_summary requires positive sample_rate_hz"}

        n = len(values)
        # Peak window — same shape as force_csv mvc_window_mean.
        peak_window_samples = max(
            1, int(round((peak_window_ms / 1000.0) * sample_rate_hz)),
        )
        peak = max(values)
        peak_idx = _last_peak_index(values, peak)
        half = peak_window_samples // 2
        pw_start = max(0, peak_idx - half)
        pw_end = min(n, peak_idx + half + 1)
        peak_window_mean = round(fmean(values[pw_start:pw_end]), 4)

        # End window.
        end_window_samples = max(
            1, int(round((end_window_ms / 1000.0) * sample_rate_hz)),
        )
        ew_start = max(0, n - end_window_samples)
        end_window_mean = round(fmean(values[ew_start:n]), 4)

        if peak_window_mean and peak_window_mean != 0:
            fatigue_index_pct = round(
                (peak_window_mean - end_window_mean)
                / peak_window_mean
                * 100.0,
                2,
            )
        else:
            fatigue_index_pct = None

        return {
            "n_samples": n,
            "duration_s": round((n - 1) / sample_rate_hz, 3),
            "peak_envelope_window_mean": peak_window_mean,
            "end_window_mean": end_window_mean,
            "fatigue_index_pct": fatigue_index_pct,
            "mean_activation": EmgCsvProcessing.mean_activation(values),
            "rms": EmgCsvProcessing.rms(values),
            "integrated_emg": EmgCsvProcessing.integrated_emg(
                values, sample_rate_hz,
            ),
        }

    @staticmethod
    def cohort_dispersion(values: list[float | None]) -> dict:
        """
        Convenience wrapper around stdev for cohort-level
        secondary statistics.  Not used by the eight core EMG
        tools; lives here as a utility for follow-on cohort
        diagnostics that compare within-group dispersion across
        groups.

        Returns ``{"n": k, "stdev": ...}`` for k ≥ 2 numeric
        values; ``{"n": k, "stdev": None}`` otherwise.
        """
        clean = [v for v in values if v is not None]
        if len(clean) < 2:
            return {"n": len(clean), "stdev": None}
        return {"n": len(clean), "stdev": round(stdev(clean), 4)}

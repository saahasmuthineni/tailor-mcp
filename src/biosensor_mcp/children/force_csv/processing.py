"""
Force-CSV Processing — Pure-Function Analytics
==============================================
Pure-function analytics for force-trace CSV files at 20-100 Hz.
Every method is a ``@staticmethod`` per ADR 0008.

Most analytics are inherited from ``children.csv_dir.processing``
via direct import — peak detection, ``time_to_50pct_drop_s``,
cohort aggregation already live there and the v6.8.1 peak-tie
fix is the load-bearing reason not to duplicate.  This module
adds force-domain helpers that don't fit the generic CSV shape:

- ``mvc_window_mean`` — Sánchez-2015 MVC definition (mean over
  250 ms window centered on peak), used by HIP Lab and the
  broader plantarflexor / handgrip dynamometer literature.
- ``bland_altman`` — paired-device agreement analysis.  Returns
  mean difference (bias), 95% limits of agreement, and per-pair
  differences for plotting.  Generalizes to any two paired
  measurements on the same subjects (HUMAC vs custom dyno being
  the canonical example per Wang & Senefeld 2026).

The streaming-reducer methods I'd scaffolded for a 1-2 kHz × 4-
channel data shape are intentionally absent — at actual HIP Lab
rates (20-100 Hz × single channel), files are small enough that
``CSVProcessing``'s load-all pattern works without modification.
"""

from __future__ import annotations

from statistics import fmean, stdev

# Shared analytics — see module docstring for rationale.
from ..csv_dir.processing import (  # noqa: F401
    COHORT_METRICS,
    CSVProcessing,
    _last_peak_index,
)


class ForceCsvProcessing:
    """
    Force-trace-specific analytics.  Inherits the generic
    cohort / decline / peak math from ``CSVProcessing`` via
    direct import — only force-domain helpers live here.
    """

    @staticmethod
    def mvc_window_mean(
        values: list[float],
        sample_rate_hz: float,
        window_ms: float = 250.0,
    ) -> float | None:
        """
        Sánchez-2015 MVC definition: mean force over a 250 ms
        window centered on the peak sample.

        This is the publication-aligned definition the HIP Lab
        literature (Wang & Senefeld 2026; Hunter & Senefeld
        broader work) cites — *not* the instantaneous peak,
        because brief sensor spikes inflate instantaneous peaks
        in ways window-averaging removes.

        Returns ``None`` for empty input or when the window
        cannot fit (file too short).

        Pure function — same inputs, same output.  No PRNG, no
        clock reads.  Per ADR 0008.
        """
        if not values or sample_rate_hz <= 0:
            return None
        window_samples = max(1, int(round((window_ms / 1000.0) * sample_rate_hz)))
        peak = max(values)
        peak_idx = _last_peak_index(values, peak)
        half = window_samples // 2
        start = max(0, peak_idx - half)
        end = min(len(values), peak_idx + half + 1)
        if end - start < 1:
            return None
        return round(fmean(values[start:end]), 3)

    @staticmethod
    def bland_altman(
        device_a_values: list[float],
        device_b_values: list[float],
    ) -> dict:
        """
        Paired-device agreement analysis (Bland & Altman 1986).

        Given two measurements per subject — one from device A,
        one from device B — returns:

        - ``mean_difference`` (bias): A - B averaged across pairs
        - ``sd_difference``: SD of the per-pair differences
        - ``upper_loa``, ``lower_loa``: limits of agreement
          (mean ± 1.96 × SD)
        - ``mean_values``: mean of each pair (x-axis of plot)
        - ``differences``: per-pair A - B (y-axis of plot)
        - ``n_pairs``: pair count

        Mirrors the analysis Chunyu Wang's 2026 thesis applies
        to HUMAC vs custom MR-conditional dyno (Figure 7).
        Generalizes to *any* paired-device validation — not
        specific to that study.

        Returns an error dict for mismatched lengths or empty
        input rather than raising — caller surfaces the error
        to the analyst.

        Pure function per ADR 0008.
        """
        if not device_a_values or not device_b_values:
            return {"error": "both device value lists must be non-empty"}
        if len(device_a_values) != len(device_b_values):
            return {
                "error": (
                    f"paired analysis requires equal-length lists; "
                    f"got {len(device_a_values)} and "
                    f"{len(device_b_values)}"
                ),
            }
        if len(device_a_values) < 2:
            return {
                "error": (
                    "Bland-Altman requires at least 2 pairs to "
                    "compute SD of differences"
                ),
            }
        differences = [
            a - b for a, b in zip(device_a_values, device_b_values, strict=True)
        ]
        means = [
            (a + b) / 2.0
            for a, b in zip(device_a_values, device_b_values, strict=True)
        ]
        bias = fmean(differences)
        sd_diff = stdev(differences)
        return {
            "n_pairs": len(differences),
            "mean_difference": round(bias, 3),
            "sd_difference": round(sd_diff, 3),
            "upper_loa": round(bias + 1.96 * sd_diff, 3),
            "lower_loa": round(bias - 1.96 * sd_diff, 3),
            "mean_values": [round(m, 3) for m in means],
            "differences": [round(d, 3) for d in differences],
        }

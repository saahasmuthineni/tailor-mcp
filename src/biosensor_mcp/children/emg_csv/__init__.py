"""
Surface-EMG CSV Child (rectified-envelope EMG, ~50–500 Hz)
==========================================================
Wraps a local directory of surface-EMG CSV exports — typically the
*rectified envelope* output (low-pass filtered, downsampled to
50–500 Hz from raw 1–2 kHz signal) that's the most common research
deliverable from Delsys Trigno, BIOPAC AcqKnowledge, OpenBCI, or
custom MR-conditional EMG hardware.

This is the **second** node in the planned data-source family — see
``children/force_csv/__init__.py`` for the multimodal-composition
framing.  Sibling pattern, not a fork.  Composition with force_csv
via shared ``subject_id`` (ADR 0009), shared audit log (ADR 0001),
and the existing ``dispatch_internal`` cross-child seam lets an
analyst query *"show me subject S004's EMG fatigue progression
alongside their force decline across this trial"* without further
framework changes.

This child is **NOT registered by ``__main__.py``**.  It ships under
the off-blueprint Senefeld-meeting detour (project memory
``project_off_blueprint_detour_2026_05_04``) and resolves back into
the blueprint after the meeting outcome is known.

Architectural decisions baked in:

- **Time-domain analytics only** (Phase 2 scope).  RMS, mean
  activation (MAV), integrated EMG (∫|envelope|·dt), and a
  peak-window-vs-end-window fatigue index.  The spectral *median
  frequency shift* — the canonical frequency-domain fatigue
  indicator — is **deferred**: implementing it cleanly requires
  either a stdlib pure-Python FFT (O(n²) without numpy) or
  promoting numpy to a runtime dependency, which conflicts with
  the project's stdlib-only install posture.  When the question
  is forced, an ADR amendment + dedicated PR will land it.
- **Path B caching for analyst-authored labels only.**  Mirrors
  ``ForceCsvStorage`` exactly — small SQLite ``emg_event_labels``
  table, preserved on consent revocation per ADR 0013.
- **No biometric-data caching.**  Source CSV files read on demand;
  no derivative envelope cache.
- **CSV-iteration helpers copied from force_csv/child.py** with
  citation comments.  Per project discipline, helper extraction
  to a shared module should happen when the fourth caller
  materializes, not now — premature abstraction is rejected.
- **Default sample-rate assumption: 100 Hz** (typical envelope rate
  after rectification + smoothing of raw 1–2 kHz EMG; matches the
  Wang & Senefeld 2026 lab-hardware-export shape closely enough
  for demo purposes).
- **Bland-Altman is intentionally absent** from this child.  Force
  device-validation has its own clinical literature (HUMAC vs MR-
  conditional dyno per Wang Ch 3.4); EMG device-validation has
  different conventions (cross-talk, electrode-placement
  reproducibility) that don't reduce to the same paired-pairs
  shape.  When that question is forced, a dedicated tool — not
  Bland-Altman parameterisation — is the right answer.
"""

from .child import EmgCsvChild
from .processing import EmgCsvProcessing

__all__ = ["EmgCsvChild", "EmgCsvProcessing"]

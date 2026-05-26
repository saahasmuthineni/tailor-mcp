"""
Force-Trace CSV Child (load-cell force at 20-100 Hz)
=====================================================
Wraps a local directory of force-trace CSV exports from a load
cell (HUMAC, BIOPAC, custom MR-conditional dynamometers per
Wang & Senefeld 2026).  Single-channel force is the typical case
at HIP-Lab-shape rates (20-100 Hz); multi-channel and high-rate
EMG live in a sibling child (``emg_csv``, scoped separately).

This child is one node in a planned family of data-source-specific
children that compose for multimodal physiology research:

- ``force_csv`` (this child) — load-cell force traces
- ``emg_csv`` (planned) — surface EMG envelopes and raw bursts
- ``mrs_csv`` / ``mrs_*`` (planned) — 31P-MRS metabolic time-courses

Composition is enabled by shared ``entity_id`` scoping (ADR 0009),
shared audit log (ADR 0001), and the ``dispatch_internal`` cross-
child seam (vault layer is the existing precedent).  Together they
let an analyst query *"show me subject S004's force decline alongside
their EMG fatigue progression and PCr depletion across this trial"*
once all three children are wired in.

Forked from ``children/template/`` as the canonical scaffold;
shared analytics imported from ``children.csv_dir.processing`` so
the v6.8.1 peak-tie fix and the COHORT_METRICS vocabulary live in
one place.

**This child is NOT registered by ``__main__.py``.**  It ships
under the off-blueprint Senefeld-meeting detour (project memory
``project_off_blueprint_detour_2026_05_04``) and resolves back
into the blueprint after the meeting outcome is known.

Architectural decisions baked in:

- **Path B on caching for analyst-authored labels only** —
  protocol-event labels persist in a small SQLite table mirroring
  RunningChild's ``stop_labels``.  ``purge_cache`` PRESERVES
  labels on consent revocation per ADR 0013 § Decision: they are
  analyst-authored interpretive content, not participant biometric
  data.  This is the IRB-meaningful "your annotations stay,
  biometric cache disappears" demo.
- **No biometric-data caching** — source CSV files are read on
  demand; the framework writes no derivative force-data cache.
  Data lives on the analyst's machine; no remote API to rate-limit
  against, unlike Strava.
- **Single-channel force is the default assumption** (matches
  Wang & Senefeld 2026's 20-100 Hz × 1-channel data shape).
  Multi-channel files are supported via the ``columns`` parameter
  but are not the canonical case.
- **Bland-Altman agreement analysis as a first-class Tier-1 tool**
  — directly mirrors the device-validation work HIP Lab actually
  publishes (Wang 2026 Chapter 3.4); generalizes to any paired-
  device validation, not specific to one study.
"""

from .child import ForceCsvChild
from .processing import ForceCsvProcessing

__all__ = ["ForceCsvChild", "ForceCsvProcessing"]

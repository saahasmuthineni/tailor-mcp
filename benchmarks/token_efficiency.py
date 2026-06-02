"""
Token-efficiency benchmark for Tailor's Tier-1 surface + vault.

Two named measurements, each comparing "raw / stateless" baseline
against "Tailor structured" approach:

A. PER-QUERY EFFICIENCY (data → answer in one session)
   How many tokens does an LLM consume if a researcher
   (a) pastes the raw CSV(s) into the conversation, versus
   (b) calls a Tailor Tier-1 tool and pastes only the structured
       summary?
   Two scenarios: single-subject S004 fatigue diagnostic, and
   16-subject cohort comparison stratified by sex.

B. SESSION PERSISTENCE EFFICIENCY (cost of resuming across sessions)
   How many tokens does an LLM need to be brought to the same
   analytical state on a multi-session thread, if the researcher
   (a) re-feeds the underlying data + accumulated notes from scratch
       (because there is no persistent structured memory), versus
   (b) lets Tailor's vault retrieve only the relevant snapshot +
       moments for the current question (because the data lives on
       disk and is summarized on demand)?
   Uses the real bundled vault state (snapshot.md + the S004 EMG/
   force-decoupling moment) — no estimated transcript content.

The two together back the load-bearing "AI economics" claim from
[ADR 0029](../docs/adr/0029-token-reduction-as-analytical-quality.md):
token reduction is analytical quality (and durable analytical memory),
not only cost optimization.

Reproduce:
    python benchmarks/token_efficiency.py

Requires: tiktoken (one-shot install — not added to pyproject.toml
dependencies because production Tailor does not need it).
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src/ to path so the script runs against the dev tree without
# requiring the wheel to be installed. Reproducible from a fresh
# clone with `pip install tiktoken` and nothing else.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tailor.children.csv_dir.processing import CSVProcessing  # noqa: E402
from tailor.framework.cost import estimate_tokens  # noqa: E402

try:
    import tiktoken
    ENCODER = tiktoken.get_encoding("cl100k_base")
    TIKTOKEN_AVAILABLE = True
except ImportError:
    ENCODER = None
    TIKTOKEN_AVAILABLE = False


FORCE_DIR = REPO_ROOT / "src" / "tailor" / "_fixtures" / "cohort_demo_realistic" / "force"
METADATA_PATH = FORCE_DIR / "metadata.json"
VAULT_DIR = REPO_ROOT / "src" / "tailor" / "_fixtures" / "cohort_demo_realistic" / "vault"
VAULT_SNAPSHOT_PATH = VAULT_DIR / "snapshot.md"
VAULT_MOMENT_PATH = VAULT_DIR / "moments" / "2026-04-20-s004-emg-force-decoupling-suspected.md"


def count_tokens_tiktoken(text: str) -> int:
    if ENCODER is None:
        return -1
    return len(ENCODER.encode(text))


def count_tokens_tailor(text_or_dict) -> int:
    """Tailor's own estimate_tokens (chars/4) — used as a cross-check.

    Per CLAUDE.md v7.3.4 banner, this heuristic is ~2.1× conservative
    against actual wire-measured tokens on bundled fixtures, which
    means actual ratios are LIKELY HIGHER than this estimator reports.
    """
    return estimate_tokens(text_or_dict)


def load_force_csv(path: Path) -> tuple[str, list[float], list[datetime]]:
    """Returns (raw_text, values, timestamps). Timestamps are
    fabricated from t_s offsets against a fixed reference epoch so
    they're deterministic per ADR 0008."""
    raw_text = path.read_text(encoding="utf-8")
    epoch = datetime(2026, 1, 1, 0, 0, 0)
    values: list[float] = []
    timestamps: list[datetime] = []
    reader = csv.DictReader(raw_text.splitlines())
    for row in reader:
        t_s = float(row["t_s"])
        values.append(float(row["force_N"]))
        timestamps.append(epoch + timedelta(seconds=t_s))
    return raw_text, values, timestamps


# ─────────────────────────────────────────────────────────────────────
#  Measurement 1 — single-subject fatigue analysis on S004
# ─────────────────────────────────────────────────────────────────────


def measure_single_subject() -> dict:
    s004_path = FORCE_DIR / "S004_force.csv"
    raw_text, values, timestamps = load_force_csv(s004_path)

    # Baseline: full CSV pasted into LLM context as-is
    baseline_chars = len(raw_text)
    baseline_tiktoken = count_tokens_tiktoken(raw_text)
    baseline_tailor = count_tokens_tailor(raw_text)

    # Tailor: structured summary from Tier-1 tool
    summary = CSVProcessing.force_decline_summary(values, timestamps)
    summary_json = json.dumps(summary, separators=(",", ":"))
    tailor_chars = len(summary_json)
    tailor_tiktoken = count_tokens_tiktoken(summary_json)
    tailor_tailor = count_tokens_tailor(summary_json)

    return {
        "scenario": "single_subject_S004_fatigue",
        "question": (
            "Summarize subject S004's fatigue trajectory: peak force, "
            "decline percentage, time-to-50%-drop, and decline rate "
            "over the 60-second isometric trial."
        ),
        "dataset": {
            "file": "S004_force.csv",
            "samples": len(values),
            "sample_rate_hz": 100,
            "duration_s": 60,
            "size_bytes": baseline_chars,
        },
        "baseline": {
            "chars": baseline_chars,
            "tiktoken_cl100k_base": baseline_tiktoken,
            "tailor_estimate": baseline_tailor,
        },
        "tailor": {
            "tool_called": "CSVProcessing.force_decline_summary",
            "result_payload": summary,
            "chars": tailor_chars,
            "tiktoken_cl100k_base": tailor_tiktoken,
            "tailor_estimate": tailor_tailor,
        },
        "ratio": {
            "tiktoken": (
                round(baseline_tiktoken / tailor_tiktoken, 1)
                if tailor_tiktoken > 0 else None
            ),
            "tailor_estimate": (
                round(baseline_tailor / tailor_tailor, 1)
                if tailor_tailor > 0 else None
            ),
        },
    }


# ─────────────────────────────────────────────────────────────────────
#  Measurement 2 — cohort comparison across all 16 subjects, by sex
# ─────────────────────────────────────────────────────────────────────


def measure_cohort() -> dict:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    metadata_text = METADATA_PATH.read_text(encoding="utf-8")

    # Baseline payload: every CSV preceded by a file-name header line,
    # plus the metadata.json so the LLM knows sex/group. This mirrors
    # what a researcher actually pastes into Claude Desktop when they
    # want a cohort analysis without Tailor.
    baseline_parts: list[str] = []
    baseline_parts.append("=== metadata.json ===\n" + metadata_text + "\n")
    per_subject_values: dict[str, tuple[list[float], list[datetime], str]] = {}
    for filename in sorted(metadata.keys()):
        path = FORCE_DIR / filename
        raw_text, values, timestamps = load_force_csv(path)
        baseline_parts.append(f"=== {filename} ===\n{raw_text}\n")
        per_subject_values[filename] = (values, timestamps, metadata[filename]["sex"])

    baseline_text = "\n".join(baseline_parts)
    baseline_chars = len(baseline_text)
    baseline_tiktoken = count_tokens_tiktoken(baseline_text)
    baseline_tailor = count_tokens_tailor(baseline_text)

    # Tailor: stratify by sex, compute cohort stats per metric per stratum
    metrics = ["max", "time_to_50pct_drop_s"]
    by_sex: dict[str, dict] = {"F": {}, "M": {}}
    for sex in ("F", "M"):
        for metric in metrics:
            per_file_scalars: list[float | None] = []
            for filename, (values, timestamps, subject_sex) in per_subject_values.items():
                if subject_sex != sex:
                    continue
                scalar = CSVProcessing.aggregate_metric(values, timestamps, metric)
                per_file_scalars.append(scalar)
            by_sex[sex][metric] = CSVProcessing.cohort_stats(per_file_scalars)

    # Per-subject decline summaries are also part of the Tailor payload —
    # a researcher comparing sexes wants the per-subject column too, not
    # just the stratified means.
    per_subject_decline: dict[str, dict] = {}
    for filename, (values, timestamps, _sex) in per_subject_values.items():
        entity_id = metadata[filename]["entity_id"]
        decline = CSVProcessing.force_decline_summary(values, timestamps)
        per_subject_decline[entity_id] = {
            "sex": metadata[filename]["sex"],
            "group": metadata[filename]["group"],
            "peak_N": decline.get("peak"),
            "decline_pct_total": decline.get("decline_pct_total"),
            "time_to_50pct_drop_s": decline.get("time_to_50pct_drop_s"),
        }

    tailor_payload = {
        "cohort_summary_by_sex": by_sex,
        "per_subject_decline": per_subject_decline,
    }
    tailor_json = json.dumps(tailor_payload, separators=(",", ":"))
    tailor_chars = len(tailor_json)
    tailor_tiktoken = count_tokens_tiktoken(tailor_json)
    tailor_tailor = count_tokens_tailor(tailor_json)

    return {
        "scenario": "cohort_16_subjects_by_sex",
        "question": (
            "Compare peak force and time-to-50%-drop between male "
            "and female participants across all 16 HIP-Lab subjects; "
            "include per-subject decline percentages."
        ),
        "dataset": {
            "files": 16,
            "subjects": 16,
            "sample_rate_hz": 100,
            "duration_s_each": 60,
            "total_samples": sum(len(v) for v, _, _ in per_subject_values.values()),
            "size_bytes": baseline_chars,
        },
        "baseline": {
            "chars": baseline_chars,
            "tiktoken_cl100k_base": baseline_tiktoken,
            "tailor_estimate": baseline_tailor,
        },
        "tailor": {
            "tools_called": [
                "CSVProcessing.aggregate_metric",
                "CSVProcessing.cohort_stats",
                "CSVProcessing.force_decline_summary",
            ],
            "result_payload_preview": {
                "cohort_summary_by_sex": by_sex,
                "per_subject_decline_count": len(per_subject_decline),
            },
            "chars": tailor_chars,
            "tiktoken_cl100k_base": tailor_tiktoken,
            "tailor_estimate": tailor_tailor,
        },
        "ratio": {
            "tiktoken": (
                round(baseline_tiktoken / tailor_tiktoken, 1)
                if tailor_tiktoken > 0 else None
            ),
            "tailor_estimate": (
                round(baseline_tailor / tailor_tailor, 1)
                if tailor_tailor > 0 else None
            ),
        },
    }


# ─────────────────────────────────────────────────────────────────────
#  Measurement 3 — session persistence cost
#
#  Compares: bringing a fresh LLM session to the analytical state of a
#  multi-session thread on S004, with or without Tailor's vault. The
#  vault artifacts are real (snapshot.md + the S004 EMG/force-decoupling
#  moment); the baseline payload is the underlying data + the same
#  accumulated notes, because the baseline researcher has to communicate
#  that knowledge somehow (we don't penalize the baseline by adding
#  hypothetical chat-transcript content on top — that would make the
#  ratio larger but the methodology less defensible).
# ─────────────────────────────────────────────────────────────────────


def measure_session_persistence() -> dict:
    snapshot_text = VAULT_SNAPSHOT_PATH.read_text(encoding="utf-8")
    moment_text = VAULT_MOMENT_PATH.read_text(encoding="utf-8")

    # Tailor side: what `vault_get_snapshot` + `vault_search_notes(query=
    # "subject four")` literally return on session resume. This is the
    # real, measured wire payload — not modeled.
    tailor_payload = snapshot_text + "\n\n---\n\n" + moment_text
    tailor_chars = len(tailor_payload)
    tailor_tiktoken = count_tokens_tiktoken(tailor_payload)
    tailor_tailor = count_tokens_tailor(tailor_payload)

    # Baseline side: to reach the same analytical state without Tailor,
    # the researcher would need to paste BOTH (i) the raw cohort data so
    # the LLM can verify any claim made in pasted-in notes (without
    # source-of-truth data, the LLM is operating on the researcher's
    # word, which isn't science), AND (ii) the equivalent accumulated
    # notes. Using the SAME snapshot+moment content as the "accumulated
    # notes" is charitable to the baseline — a real researcher's
    # informal notes would likely be longer and less structured.
    metadata_text = METADATA_PATH.read_text(encoding="utf-8")
    raw_data_parts = ["=== metadata.json ===\n" + metadata_text + "\n"]
    metadata = json.loads(metadata_text)
    for filename in sorted(metadata.keys()):
        path = FORCE_DIR / filename
        raw_data_parts.append(
            f"=== {filename} ===\n{path.read_text(encoding='utf-8')}\n"
        )
    raw_data_text = "\n".join(raw_data_parts)

    baseline_payload = (
        raw_data_text
        + "\n\n=== accumulated researcher notes ===\n"
        + snapshot_text
        + "\n\n"
        + moment_text
    )
    baseline_chars = len(baseline_payload)
    baseline_tiktoken = count_tokens_tiktoken(baseline_payload)
    baseline_tailor = count_tokens_tailor(baseline_payload)

    # Cumulative cost across N sessions. The structural point: baseline
    # cost grows linearly because the LLM has no persistent memory and
    # the researcher must re-paste the data every time. Tailor cost is
    # roughly constant per session because the vault index returns only
    # relevant items for the current question, not the whole history.
    # N=5 is illustrative (a typical multi-session research thread);
    # the ratio is N-invariant.
    n_sessions = 5
    cumulative_baseline_tiktoken = n_sessions * baseline_tiktoken
    cumulative_tailor_tiktoken = n_sessions * tailor_tiktoken

    return {
        "scenario": "session_resume_S004_cohort_thread",
        "question": (
            "Resume an analytical thread on the HIP-Lab cohort with "
            "particular focus on subject S004's atypical EMG/force "
            "decoupling — what's been observed, what should I look "
            "at next?"
        ),
        "vault_state_recalled": {
            "files": [
                "snapshot.md",
                "moments/2026-04-20-s004-emg-force-decoupling-suspected.md",
            ],
            "snapshot_chars": len(snapshot_text),
            "moment_chars": len(moment_text),
        },
        "baseline": {
            "what_it_includes": (
                "raw cohort data (16 CSVs + metadata.json) + "
                "equivalent accumulated notes (snapshot + moment)"
            ),
            "chars": baseline_chars,
            "tiktoken_cl100k_base": baseline_tiktoken,
            "tailor_estimate": baseline_tailor,
        },
        "tailor": {
            "what_it_includes": (
                "snapshot.md (auto-surfaced by vault_get_snapshot) + "
                "S004 moment (returned by vault_search_notes)"
            ),
            "tools_called": ["vault_get_snapshot", "vault_search_notes"],
            "chars": tailor_chars,
            "tiktoken_cl100k_base": tailor_tiktoken,
            "tailor_estimate": tailor_tailor,
        },
        "ratio": {
            "tiktoken": (
                round(baseline_tiktoken / tailor_tiktoken, 1)
                if tailor_tiktoken > 0 else None
            ),
            "tailor_estimate": (
                round(baseline_tailor / tailor_tailor, 1)
                if tailor_tailor > 0 else None
            ),
        },
        "cumulative_across_sessions": {
            "n_sessions_modeled": n_sessions,
            "baseline_tiktoken_total": cumulative_baseline_tiktoken,
            "tailor_tiktoken_total": cumulative_tailor_tiktoken,
            "note": (
                "Without Tailor the LLM has no persistent memory across "
                "sessions, so the data-paste cost recurs every resume. "
                "With Tailor, the vault returns only items relevant to "
                "the current question; total cost scales linearly in N "
                "with a small per-session constant, not with the size "
                "of accumulated history."
            ),
        },
    }


def main() -> int:
    if not TIKTOKEN_AVAILABLE:
        print(
            "WARNING: tiktoken not installed. Cross-check numbers only.\n"
            "Install with: pip install tiktoken\n",
            file=sys.stderr,
        )

    results = {
        "tokenizer_primary": "tiktoken cl100k_base" if TIKTOKEN_AVAILABLE else "tailor estimate (chars/4)",
        "tokenizer_crosscheck": "tailor framework.cost.estimate_tokens (chars/4)",
        "per_query_efficiency": [
            measure_single_subject(),
            measure_cohort(),
        ],
        "session_persistence_efficiency": [
            measure_session_persistence(),
        ],
    }

    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

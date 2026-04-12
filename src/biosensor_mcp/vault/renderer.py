"""
Vault Renderer — Pure Markdown Generation
==========================================
Converts computed analytics dicts into Obsidian-flavoured markdown notes.

All functions are stateless and I/O-free — safe to unit test without any
filesystem or database setup.

Return value convention: (relative_filename, markdown_content)
  filename is relative to vault_path, e.g. "running/2025-04-10-activity-12345678.md"
"""

from datetime import datetime, timezone
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _parse_date(start_date: str) -> str:
    """Extract YYYY-MM-DD from a Strava start_date (ISO 8601, may include time)."""
    if not start_date:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return start_date[:10]


def _iso_week(date_str: str) -> str:
    """Return ISO week key, e.g. '2025-W15'."""
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return dt.strftime("%Y-W%V")
    except ValueError:
        return "unknown"


def _aerobic_grade(decoupling_pct: float) -> str:
    if abs(decoupling_pct) < 5:
        return "coupled"
    if abs(decoupling_pct) < 8:
        return "borderline"
    return "decoupled"


def _pace_from_velocity(velocity_ms: float) -> str:
    """Convert m/s to min/mile string."""
    if velocity_ms <= 0:
        return "--:--"
    pace_sec = 1609.34 / velocity_ms
    mins = int(pace_sec // 60)
    secs = int(pace_sec % 60)
    return f"{mins}:{secs:02d}"


def _meters_to_miles(m: float) -> float:
    return round(m / 1609.34, 2)


def _seconds_to_minutes(s: float) -> float:
    return round(s / 60, 1)


# ── Generic helpers ─────────────────────────────────────────────

def format_wikilink(target: str, display: Optional[str] = None) -> str:
    """
    Return an Obsidian wikilink string.  Centralises the ad-hoc
    ``[[target|display]]`` pattern that existing renderers used inline.
    """
    target = (target or "").strip()
    if not target:
        return ""
    if display and display.strip() and display.strip() != target:
        return f"[[{target}|{display.strip()}]]"
    return f"[[{target}]]"


def _slug_from_filename(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    if base.endswith(".md"):
        base = base[:-3]
    return base


def _run_wikilink_for_activity(activity_id) -> str:
    """Render the canonical run wikilink target (no .md extension)."""
    return f"activity-{activity_id}"


def _yaml_scalar(value) -> str:
    """Quote a string value for YAML frontmatter; leave scalars bare."""
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace('"', '\\"')
    return f'"{s}"'


def _yaml_string_list(items: list) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(_yaml_scalar(str(x)) for x in items) + "]"


def _yaml_int_list(items: list) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(str(int(x)) for x in items if x is not None) + "]"


# ═══════════════════════════════════════════════════════════════
# RUN REPORT NOTE
# ═══════════════════════════════════════════════════════════════

def render_run_note(
    result: dict,
    activity_data: dict,
    max_hr: int = 195,
) -> tuple[str, str]:
    """
    Render a strava_run_report result as an Obsidian markdown note.

    Args:
        result:        Dict returned by _handle_run_report.
        activity_data: Raw Strava activity dict from RunningStorage.get_activity().
        max_hr:        User's configured max heart rate.

    Returns:
        (relative_filename, markdown_content)
        filename e.g. "running/2025-04-10-activity-12345678.md"
    """
    activity_id = result.get("activity_id") or activity_data.get("id", 0)
    date_str = _parse_date(activity_data.get("start_date", ""))
    week = _iso_week(date_str)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Activity-level metrics
    distance_miles = _meters_to_miles(activity_data.get("distance", 0))
    duration_min = _seconds_to_minutes(activity_data.get("moving_time", 0))
    avg_hr = activity_data.get("average_heartrate")
    max_hr_observed = activity_data.get("max_heartrate")

    # Analytics from result dict
    decoupling = result.get("decoupling", {})
    decoupling_pct = decoupling.get("decoupling_pct", 0.0) if isinstance(decoupling, dict) else 0.0
    aerobic_grade = _aerobic_grade(decoupling_pct)

    ef = result.get("efficiency_factor", {})
    ef_val = ef.get("ef", 0.0) if isinstance(ef, dict) else 0.0

    hr_drift = result.get("hr_drift", {})
    hr_drift_pct = hr_drift.get("drift_pct", 0.0) if isinstance(hr_drift, dict) else 0.0

    anomalies = result.get("anomalies", [])
    anomaly_types = list({a.get("type", "") for a in anomalies if a.get("type")})
    anomaly_count = len(anomalies)

    phases_raw = result.get("phases", [])
    phase_names = [p.get("phase", "") for p in phases_raw if isinstance(p, dict) and p.get("phase")]

    # Tags
    tags = [
        "running",
        f"aerobic/{aerobic_grade}",
        f"week/{week}",
    ]

    # ── YAML frontmatter ──
    def _yaml_list(items: list) -> str:
        if not items:
            return "[]"
        return "[" + ", ".join(f'"{x}"' for x in items) + "]"

    frontmatter_lines = [
        "---",
        "domain: running",
        "note_type: run_report",
        f"activity_id: {activity_id}",
        f'date: "{date_str}"',
        f'week: "{week}"',
        f"distance_miles: {distance_miles}",
        f"duration_min: {duration_min}",
    ]
    if avg_hr is not None:
        frontmatter_lines.append(f"avg_hr: {int(avg_hr)}")
    if max_hr_observed is not None:
        frontmatter_lines.append(f"max_hr_observed: {int(max_hr_observed)}")
    frontmatter_lines += [
        f"decoupling_pct: {decoupling_pct}",
        f"efficiency_factor: {ef_val}",
        f"hr_drift_pct: {hr_drift_pct}",
        f"aerobic_grade: {aerobic_grade}",
        f"anomaly_count: {anomaly_count}",
        f"anomaly_types: {_yaml_list(anomaly_types)}",
        f"phases: {_yaml_list(phase_names)}",
        "has_insight_notes: false",
        f'generated_at: "{now_iso}"',
        f"strava_id: {activity_id}",
        "tags:",
    ] + [f"  - {t}" for t in tags] + ["---"]

    frontmatter = "\n".join(frontmatter_lines)

    # ── Note body ──
    name = activity_data.get("name", f"Run {activity_id}")
    body_parts = [
        f"# {name}",
        "",
        "## Summary",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Date | {date_str} |",
        f"| Distance | {distance_miles} mi |",
        f"| Duration | {duration_min} min |",
    ]
    if avg_hr:
        body_parts.append(f"| Avg HR | {int(avg_hr)} bpm |")
    body_parts += [
        f"| Aerobic Grade | {aerobic_grade} |",
        f"| Decoupling | {decoupling_pct}% |",
        f"| Efficiency Factor | {ef_val} |",
        f"| HR Drift | {hr_drift_pct}% |",
        "",
    ]

    # HR Analysis section
    hr_zones = result.get("hr_zones", {})
    if hr_zones:
        body_parts += [
            "## HR Analysis",
            "",
            f"Avg HR: **{hr_zones.get('avg_hr', '—')} bpm** · "
            f"Max: **{hr_zones.get('max_hr_observed', '—')} bpm** · "
            f"Setting: {hr_zones.get('max_hr_setting', max_hr)} bpm",
            "",
        ]
        zone_pct = hr_zones.get("zone_pct", {})
        zone_sec = hr_zones.get("zone_seconds", {})
        if zone_pct:
            body_parts.append("| Zone | % Time | Seconds |")
            body_parts.append("|------|--------|---------|")
            for z in range(1, 6):
                body_parts.append(
                    f"| Z{z} | {zone_pct.get(z, 0)}% | {zone_sec.get(z, 0)} |"
                )
            body_parts.append("")

        if isinstance(hr_drift, dict) and "drift_pct" in hr_drift:
            body_parts += [
                f"**HR Drift:** {hr_drift.get('drift_pct')}% "
                f"({hr_drift.get('interpretation', '')})",
                f"First half avg: {hr_drift.get('first_half_avg')} bpm · "
                f"Second half avg: {hr_drift.get('second_half_avg')} bpm",
                "",
            ]

    # Mile Splits
    mile_splits = result.get("mile_splits", [])
    if mile_splits:
        body_parts += ["## Mile Splits", ""]
        body_parts.append("| Mile | Pace | Avg Vel (m/s) |")
        body_parts.append("|------|------|---------------|")
        for s in mile_splits:
            vel = s.get("avg_velocity_ms", "—")
            body_parts.append(f"| {s['mile']} | {s['pace']} | {vel} |")
        body_parts.append("")

    # Run Phases
    if phases_raw and not (len(phases_raw) == 1 and phases_raw[0].get("phase") == "too_short"):
        body_parts += ["## Run Phases", ""]
        body_parts.append("| Phase | Start | End | Duration |")
        body_parts.append("|-------|-------|-----|----------|")
        for p in phases_raw:
            if not isinstance(p, dict):
                continue
            start_s = p.get("start_time", 0)
            end_s = p.get("end_time", 0)
            dur_s = p.get("duration_seconds", end_s - start_s)
            body_parts.append(
                f"| {p.get('phase', '')} | {start_s}s | {end_s}s | {dur_s}s |"
            )
        body_parts.append("")

    # GAP Splits
    gap_splits = result.get("gap_splits", [])
    if gap_splits:
        body_parts += ["## GAP Splits", ""]
        body_parts.append("| Mile | GAP Pace |")
        body_parts.append("|------|----------|")
        for s in gap_splits:
            body_parts.append(f"| {s['mile']} | {s['pace']} |")
        body_parts.append("")

    # Anomalies
    if anomalies:
        body_parts += ["## Anomalies", ""]
        for a in anomalies:
            sev = a.get("severity", "")
            sev_label = f" ({sev})" if sev else ""
            body_parts.append(f"- **{a.get('type', 'unknown')}**{sev_label}: {a.get('description', '')}")
        body_parts.append("")

    # Insight notes placeholder
    body_parts += [
        "## Insights",
        "",
        "*(No insight notes yet.)*",
        "",
    ]

    body = "\n".join(body_parts)
    content = frontmatter + "\n" + body

    filename = f"running/{date_str}-activity-{activity_id}.md"
    return filename, content


# ═══════════════════════════════════════════════════════════════
# TREND REPORT NOTE
# ═══════════════════════════════════════════════════════════════

def render_trend_note(result: dict) -> tuple[str, str]:
    """
    Render a strava_trend_report result as a trend note.

    Returns (relative_filename, markdown_content)
    filename e.g. "running/trends/2025-W15.md"
    """
    date_range = result.get("date_range", {})
    start = date_range.get("start", "")
    end = date_range.get("end", "")
    total_runs = result.get("total_runs", 0)
    weeks = result.get("weeks", [])
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Derive a week key from date range (use end date's week as the primary label)
    if weeks:
        week_key = weeks[-1].get("week", _iso_week(end))
    else:
        week_key = _iso_week(end)

    # Aggregate stats
    total_miles = sum(w.get("total_miles", 0) for w in weeks)
    hrs = [w.get("avg_hr") for w in weeks if w.get("avg_hr")]
    overall_avg_hr = round(sum(hrs) / len(hrs)) if hrs else None

    frontmatter_lines = [
        "---",
        "domain: running",
        "note_type: trend_report",
        f'date_start: "{start}"',
        f'date_end: "{end}"',
        f'week: "{week_key}"',
        f"total_runs: {total_runs}",
        f"total_miles: {round(total_miles, 1)}",
        f"weeks_covered: {len(weeks)}",
    ]
    if overall_avg_hr is not None:
        frontmatter_lines.append(f"avg_hr: {overall_avg_hr}")
    frontmatter_lines += [
        "has_insight_notes: false",
        f'generated_at: "{now_iso}"',
        "tags:",
        "  - running",
        "  - trend",
        f"  - week/{week_key}",
        "---",
    ]

    frontmatter = "\n".join(frontmatter_lines)

    body_parts = [
        f"# Trend Report: {start} → {end}",
        "",
        f"**{total_runs} runs** across **{len(weeks)} weeks** · "
        f"Total: **{round(total_miles, 1)} miles**",
        "",
        "## Weekly Summary",
        "",
        "| Week | Runs | Miles | Minutes | Avg HR | Longest |",
        "|------|------|-------|---------|--------|---------|",
    ]

    run_note_links = []
    for w in weeks:
        avg_hr_str = str(w.get("avg_hr", "—")) if w.get("avg_hr") else "—"
        body_parts.append(
            f"| {w.get('week', '')} | {w.get('runs', 0)} | "
            f"{w.get('total_miles', 0)} | {w.get('total_minutes', 0)} | "
            f"{avg_hr_str} | {w.get('longest_run_miles', 0)} mi |"
        )
        run_note_links.append(w.get("week", ""))

    body_parts += ["", "## Insights", "", "*(No insight notes yet.)*", ""]

    body = "\n".join(body_parts)
    content = frontmatter + "\n" + body

    filename = f"running/trends/{week_key}.md"
    return filename, content


# ═══════════════════════════════════════════════════════════════
# COMPARE RUNS NOTE
# ═══════════════════════════════════════════════════════════════

def render_compare_note(result: dict) -> tuple[str, str]:
    """
    Render a strava_compare_runs result as a comparison note.

    Returns (relative_filename, markdown_content)
    filename e.g. "running/compare/20250410-vs-20250414.md"
    """
    comparisons = result.get("comparisons", [])
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    dates = [c.get("date", "")[:10] for c in comparisons if c.get("date")]
    activity_ids = [c.get("activity_id") for c in comparisons]
    date_slug = "-vs-".join(d.replace("-", "") for d in dates[:2]) if len(dates) >= 2 else "unknown"

    frontmatter_lines = [
        "---",
        "domain: running",
        "note_type: compare_runs",
        f"activity_ids: [{', '.join(str(i) for i in activity_ids)}]",
        f"run_count: {len(comparisons)}",
        "has_insight_notes: false",
        f'generated_at: "{now_iso}"',
        "tags:",
        "  - running",
        "  - comparison",
        "---",
    ]

    frontmatter = "\n".join(frontmatter_lines)

    body_parts = [
        f"# Run Comparison",
        "",
        "## Side-by-Side Metrics",
        "",
        "| Activity | Date | Distance | Time | Avg HR | Decoupling | EF | HR Drift |",
        "|----------|------|----------|------|--------|------------|----|---------:|",
    ]

    wikilinks = []
    for c in comparisons:
        aid = c.get("activity_id", "")
        date = c.get("date", "")[:10]
        dist = c.get("distance_miles", 0)
        time_min = c.get("moving_time_min", 0)
        avg_hr = c.get("avg_hr", "—") or "—"

        decoupling = c.get("decoupling", {})
        dec_pct = decoupling.get("decoupling_pct", "—") if isinstance(decoupling, dict) else "—"

        ef_data = c.get("efficiency_factor", {})
        ef = ef_data.get("ef", "—") if isinstance(ef_data, dict) else "—"

        drift = c.get("hr_drift", {})
        drift_pct = drift.get("drift_pct", "—") if isinstance(drift, dict) else "—"

        name = c.get("name", f"Run {aid}")
        link = format_wikilink(f"{date}-activity-{aid}", name) if date else str(aid)
        wikilinks.append(link)

        body_parts.append(
            f"| {link} | {date} | {dist} mi | {time_min} min | {avg_hr} | "
            f"{dec_pct}% | {ef} | {drift_pct}% |"
        )

    body_parts += [
        "",
        "## Referenced Runs",
        "",
    ] + [f"- {lnk}" for lnk in wikilinks] + [
        "",
        "## Insights",
        "",
        "*(No insight notes yet.)*",
        "",
    ]

    body = "\n".join(body_parts)
    content = frontmatter + "\n" + body

    filename = f"running/compare/{date_slug}.md"
    return filename, content


# ═══════════════════════════════════════════════════════════════
# THEME NOTE — persistent hypothesis across runs
# ═══════════════════════════════════════════════════════════════

_THEME_EVIDENCE_HEADER = "## Evidence"
_THEME_RESOLUTION_HEADER = "## Resolution"


def render_theme_note(theme: dict) -> tuple[str, str]:
    """
    Render a theme (persistent hypothesis) as a markdown note.

    Expected ``theme`` fields:
        slug (required):       e.g. "dehydration-drift"
        title (optional):      human title; defaults to slug
        hypothesis (required): short prose statement
        status:                open | resolved | rejected (default: open)
        opened:                YYYY-MM-DD (default: today)
        last_updated:          YYYY-MM-DD (default: today)
        linked_runs:           list of int activity_ids
        linked_themes:         list of theme slugs
        tags:                  list of strings
        confidence:            low | medium | high
        evidence:              initial evidence block (str or list[str])
        resolution:            prose shown under ## Resolution when status != open

    The body is: hypothesis → ## Evidence (append-only log) → ## Resolution.
    """
    slug = str(theme.get("slug") or "").strip()
    if not slug:
        raise ValueError("theme.slug is required")

    title = str(theme.get("title") or slug.replace("-", " ").title())
    hypothesis = str(theme.get("hypothesis") or "").strip()
    status = str(theme.get("status") or "open").strip()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    opened = str(theme.get("opened") or today)
    last_updated = str(theme.get("last_updated") or today)
    confidence = theme.get("confidence")
    linked_runs = [int(x) for x in (theme.get("linked_runs") or []) if x is not None]
    linked_themes = list(theme.get("linked_themes") or [])
    tags = list(theme.get("tags") or [])
    if "theme" not in tags:
        tags = ["theme"] + tags

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Frontmatter ──
    fm_lines = [
        "---",
        "domain: vault",
        "note_type: theme",
        "kind: theme",
        f"slug: {_yaml_scalar(slug)}",
        f"title: {_yaml_scalar(title)}",
        f"status: {_yaml_scalar(status)}",
        f"opened: {_yaml_scalar(opened)}",
        f"last_updated: {_yaml_scalar(last_updated)}",
        f"date: {_yaml_scalar(last_updated)}",
        f"linked_runs: {_yaml_int_list(linked_runs)}",
        f"linked_themes: {_yaml_string_list(linked_themes)}",
    ]
    if confidence:
        fm_lines.append(f"confidence: {_yaml_scalar(confidence)}")
    fm_lines.append(f'generated_at: "{now_iso}"')
    fm_lines.append("tags:")
    fm_lines += [f"  - {t}" for t in tags]
    fm_lines.append("---")

    # ── Body ──
    body_parts = [
        f"# {title}",
        "",
        "## Hypothesis",
        "",
        hypothesis or "*(No hypothesis yet.)*",
        "",
    ]

    # Linked runs section — wikilinks to run notes
    if linked_runs:
        body_parts += ["## Linked Runs", ""]
        body_parts += [
            f"- {format_wikilink(_run_wikilink_for_activity(aid))}"
            for aid in linked_runs
        ]
        body_parts.append("")

    if linked_themes:
        body_parts += ["## Linked Themes", ""]
        body_parts += [f"- {format_wikilink(s)}" for s in linked_themes]
        body_parts.append("")

    # Evidence log
    body_parts += [_THEME_EVIDENCE_HEADER, ""]
    initial_evidence = theme.get("evidence")
    if isinstance(initial_evidence, list):
        for block in initial_evidence:
            body_parts.append(_format_evidence_block(str(block), last_updated))
    elif isinstance(initial_evidence, str) and initial_evidence.strip():
        body_parts.append(_format_evidence_block(initial_evidence, last_updated))
    else:
        body_parts.append("*(No evidence recorded yet.)*")
        body_parts.append("")

    # Resolution section (always present so status flips have a clear home)
    body_parts += [_THEME_RESOLUTION_HEADER, ""]
    resolution = theme.get("resolution")
    if status != "open" and resolution:
        body_parts.append(str(resolution).strip())
    elif status != "open":
        body_parts.append(f"*(Status: {status}. No resolution notes recorded.)*")
    else:
        body_parts.append("*(Open — no resolution yet.)*")
    body_parts.append("")

    content = "\n".join(fm_lines) + "\n" + "\n".join(body_parts)
    filename = f"themes/{slug}.md"
    return filename, content


def _format_evidence_block(evidence: str, date_str: str) -> str:
    """
    Render one evidence entry.  Uses the same ``### Insight — TIMESTAMP``
    header convention as existing insight annotations in writer.py so
    the two logs look consistent in Obsidian.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"### Evidence — {ts}\n\n{evidence.strip()}\n"


# ═══════════════════════════════════════════════════════════════
# MOMENT NOTE — one-shot "aha" observation
# ═══════════════════════════════════════════════════════════════

def render_moment_note(moment: dict) -> tuple[str, str]:
    """
    Render a single "aha" moment note.

    Expected ``moment`` fields:
        title (required):  short human title
        body (required):   1–3 paragraph prose
        date:              YYYY-MM-DD (default: today)
        linked_runs:       list of activity_ids
        linked_themes:     list of theme slugs
        tags:              list of strings
        slug:              explicit slug override (default: derived from title)
    """
    title = str(moment.get("title") or "").strip()
    body = str(moment.get("body") or "").strip()
    if not title:
        raise ValueError("moment.title is required")
    if not body:
        raise ValueError("moment.body is required")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_str = str(moment.get("date") or today)
    slug = str(moment.get("slug") or _slugify_title(title))
    linked_runs = [int(x) for x in (moment.get("linked_runs") or []) if x is not None]
    linked_themes = list(moment.get("linked_themes") or [])
    tags = list(moment.get("tags") or [])
    if "moment" not in tags:
        tags = ["moment"] + tags

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    fm_lines = [
        "---",
        "domain: vault",
        "note_type: moment",
        "kind: moment",
        f"title: {_yaml_scalar(title)}",
        f"slug: {_yaml_scalar(slug)}",
        f"date: {_yaml_scalar(date_str)}",
        f"linked_runs: {_yaml_int_list(linked_runs)}",
        f"linked_themes: {_yaml_string_list(linked_themes)}",
        f'generated_at: "{now_iso}"',
        "tags:",
    ]
    fm_lines += [f"  - {t}" for t in tags]
    fm_lines.append("---")

    body_parts = [
        f"# {title}",
        "",
        body,
        "",
    ]

    if linked_runs:
        body_parts += ["## Linked Runs", ""]
        body_parts += [
            f"- {format_wikilink(_run_wikilink_for_activity(aid))}"
            for aid in linked_runs
        ]
        body_parts.append("")

    if linked_themes:
        body_parts += ["## Linked Themes", ""]
        body_parts += [f"- {format_wikilink(s)}" for s in linked_themes]
        body_parts.append("")

    content = "\n".join(fm_lines) + "\n" + "\n".join(body_parts)
    filename = f"moments/{date_str}-{slug}.md"
    return filename, content


def _slugify_title(title: str) -> str:
    """Minimal slugger — lowercase, alnum + dashes, no unicode transliteration."""
    import re as _re
    s = title.lower().strip()
    s = _re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "moment"

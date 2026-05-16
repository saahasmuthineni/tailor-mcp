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

def format_wikilink(target: str, display: str | None = None) -> str:
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
        "| Field | Value |",
        "|-------|-------|",
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
        "# Run Comparison",
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
    # ADR 0009 — optional set-once subject scoping
    subject_id = theme.get("subject_id")
    subject_id = str(subject_id).strip() if subject_id else None

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
    if subject_id:
        fm_lines.append(f"subject_id: {_yaml_scalar(subject_id)}")
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
            body_parts.append(_format_evidence_block(
                str(block), last_updated, subject_id=subject_id,
            ))
    elif isinstance(initial_evidence, str) and initial_evidence.strip():
        body_parts.append(_format_evidence_block(
            initial_evidence, last_updated, subject_id=subject_id,
        ))
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


def _format_evidence_block(
    evidence: str,
    date_str: str | None = None,
    *,
    source_tier: int | None = None,
    source_tool: str | None = None,
    source_domain: str | None = None,
    verification: str | None = None,
    tag_suffix: str = "",
    timestamp: str | None = None,
    subject_id: str | None = None,
) -> str:
    """
    Render one evidence entry.  Uses the same ``### Insight — TIMESTAMP``
    header convention as existing insight annotations in writer.py so
    the two logs look consistent in Obsidian.

    If any of the provenance kwargs (source_tier/source_tool/source_domain/
    verification) is provided, a blockquote line is added after the header
    recording the origin of the observation.  ``tag_suffix`` appends a
    bracketed tag to the header (e.g. ``[correction]``).

    ``subject_id`` (ADR 0009) renders as a second blockquote line
    (``> Subject: P004``) immediately after the source line — preserves
    the append-only invariant on existing blocks (legacy blocks have no
    subject line, are read as 'subject unspecified').
    """
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    suffix = f" {tag_suffix}" if tag_suffix else ""
    header = f"### Evidence — {ts}{suffix}"

    metadata_lines: list[str] = []
    has_prov = (
        source_tier is not None
        or bool(source_tool)
        or bool(source_domain)
        or bool(verification)
    )
    if has_prov:
        prov_line = _format_provenance_line(
            source_tier=source_tier,
            source_tool=source_tool,
            source_domain=source_domain,
            verification=verification,
        )
        if prov_line:
            metadata_lines.append(prov_line)
    if subject_id:
        metadata_lines.append(f"> Subject: {subject_id}")

    if metadata_lines:
        meta_block = "\n".join(metadata_lines)
        return f"{header}\n{meta_block}\n\n{evidence.strip()}\n"
    return f"{header}\n\n{evidence.strip()}\n"


def _format_provenance_line(
    *,
    source_tier: int | None = None,
    source_tool: str | None = None,
    source_domain: str | None = None,
    verification: str | None = None,
) -> str:
    """Compose a ``> Source: …`` blockquote line from whatever is provided."""
    parts: list[str] = []
    if source_domain and source_tool:
        src_label = f"{source_domain}/{source_tool}"
    elif source_tool:
        src_label = source_tool
    elif source_domain:
        src_label = source_domain
    else:
        src_label = ""

    if src_label and source_tier is not None:
        parts.append(f"Source: {src_label} (Tier {source_tier})")
    elif src_label:
        parts.append(f"Source: {src_label}")
    elif source_tier is not None:
        parts.append(f"Source: Tier {source_tier}")

    if verification:
        parts.append(f"Verification: {verification}")

    if not parts:
        return ""
    return "> " + " · ".join(parts)


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
        divergence:        optional prose — what the analytical goal was
                           versus what actually happened.  Rendered as a
                           ``## Divergence`` section and stored in
                           frontmatter so it's searchable.
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
    divergence = moment.get("divergence")
    divergence = str(divergence).strip() if divergence else ""
    # ADR 0009 — optional subject scoping
    subject_id = moment.get("subject_id")
    subject_id = str(subject_id).strip() if subject_id else None

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
    ]
    if subject_id:
        fm_lines.append(f"subject_id: {_yaml_scalar(subject_id)}")
    if divergence:
        fm_lines.append(f"divergence: {_yaml_scalar(divergence)}")
    fm_lines.append(f'generated_at: "{now_iso}"')
    fm_lines.append("tags:")
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

    if divergence:
        body_parts += ["## Divergence", "", divergence, ""]

    content = "\n".join(fm_lines) + "\n" + "\n".join(body_parts)
    filename = f"moments/{date_str}-{slug}.md"
    return filename, content


def render_snapshot_note(snapshot: dict) -> tuple[str, str]:
    """
    Render a compressed vault snapshot as ``snapshot.md`` in the vault root.

    Expected ``snapshot`` fields (all optional, rendered when present):
        open_themes:         list[dict] with slug/status/confidence/evidence_count
        recent_moments:      list[dict] with date/title/linked_themes
        weekly_summary:      list[dict] with week/runs/total_miles/avg_hr
        vault_health:        dict: notes_indexed, themes_open, themes_resolved,
                             moments, stale_themes (list[str]), inbox_items
        warnings:            list[str]
        written_by:          optional session identifier
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    written_by = str(snapshot.get("written_by") or "claude-session")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    fm_lines = [
        "---",
        "domain: vault",
        "note_type: snapshot",
        f"last_written: {_yaml_scalar(today)}",
        f"written_by: {_yaml_scalar(written_by)}",
        f'generated_at: "{now_iso}"',
        "tags:",
        "  - snapshot",
        "---",
    ]

    body_parts = ["# Vault Snapshot", ""]

    # Open themes
    body_parts += ["## Open Themes", ""]
    open_themes = snapshot.get("open_themes") or []
    if open_themes:
        for t in open_themes:
            slug = t.get("slug", "")
            status = t.get("status", "open")
            conf = t.get("confidence") or "—"
            ev_count = t.get("evidence_count")
            ev_part = f", {ev_count} evidence block{'s' if ev_count != 1 else ''}" if ev_count is not None else ""
            body_parts.append(
                f"- **{slug}** ({status}, {conf} confidence{ev_part})"
            )
    else:
        body_parts.append("*(No open themes.)*")
    body_parts.append("")

    # Recent moments
    body_parts += ["## Recent Moments (last 14 days)", ""]
    recent_moments = snapshot.get("recent_moments") or []
    if recent_moments:
        for m in recent_moments:
            date = m.get("date", "")
            title = m.get("title", "")
            linked = m.get("linked_themes") or []
            link_part = f" → linked to {', '.join(linked)}" if linked else ""
            body_parts.append(f'- {date}: "{title}"{link_part}')
    else:
        body_parts.append("*(No recent moments.)*")
    body_parts.append("")

    # Weekly summary — only render when we actually have run data.
    # v7.3.4: a HIP-Lab / cohort-CSV / REDCap deployment has no running
    # child registered and no `run_report` notes; surfacing an empty
    # weekly-runs table would Strava-shape the orientation surface and
    # mislead a recipient on a non-running demo (per ADR 0027 / 0029
    # + the v7.3.4 mcp-protocol-auditor + integration-auditor F3
    # finding that the regenerator was overwriting hand-written
    # orientation prose with a no-run-data table). v7.4.0 closes the
    # broader vault-layer Strava purge per ADR 0038 (Proposed).
    weekly = snapshot.get("weekly_summary") or []
    if weekly:
        body_parts += ["## Weekly Summary (last 4 weeks)", ""]
        body_parts.append("| Week | Runs | Miles | Avg HR |")
        body_parts.append("|------|------|-------|--------|")
        for w in weekly:
            week = w.get("week", "—")
            runs = w.get("runs", 0)
            miles = w.get("total_miles", 0)
            avg_hr = w.get("avg_hr", "—") or "—"
            body_parts.append(f"| {week} | {runs} | {miles} | {avg_hr} |")
        body_parts.append("")

    # Vault health
    body_parts += ["## Vault Health", ""]
    health = snapshot.get("vault_health") or {}
    body_parts.append(f"- Notes indexed: {health.get('notes_indexed', 0)}")
    themes_open = health.get("themes_open", 0)
    themes_resolved = health.get("themes_resolved", 0)
    body_parts.append(f"- Themes: {themes_open} open, {themes_resolved} resolved")
    body_parts.append(f"- Moments: {health.get('moments', 0)}")
    stale = health.get("stale_themes") or []
    stale_label = ", ".join(stale) if stale else "none"
    body_parts.append(f"- Stale themes (>30d no evidence): {stale_label}")
    body_parts.append(f"- Inbox items: {health.get('inbox_items', 0)}")
    body_parts.append("")

    # Warnings
    warnings = snapshot.get("warnings") or []
    body_parts += ["## Warnings", ""]
    if warnings:
        for w in warnings:
            body_parts.append(f"- {w}")
    else:
        body_parts.append("*(No warnings.)*")
    body_parts.append("")

    content = "\n".join(fm_lines) + "\n" + "\n".join(body_parts)
    return "snapshot.md", content


def _slugify_title(title: str) -> str:
    """Minimal slugger — lowercase, alnum + dashes, no unicode transliteration."""
    import re as _re
    s = title.lower().strip()
    s = _re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "moment"


# ═══════════════════════════════════════════════════════════════
# FAILURE-MODE NOTE — durable record of "we got this wrong"
# ═══════════════════════════════════════════════════════════════

# Allowed status values for a failure-mode note.
_FAILURE_MODE_STATUSES = ("active", "mitigated", "superseded")


def render_failure_mode_note(failure_mode: dict) -> tuple[str, str]:
    """
    Render a failure-mode note — a durable record of an analytical
    pattern the study has gotten wrong before, with diagnosis,
    mitigation, and an append-only evidence log.

    Expected ``failure_mode`` fields:
        slug (required):       lowercase-dashed identifier
        title (required):      short human title
        symptom (required):    1–3 sentences — what the failure looks like
        diagnosis (required):  why it happened (what went wrong upstream)
        mitigation (required): how to avoid recurrence
        status:                active | mitigated | superseded (default: active)
        opened:                YYYY-MM-DD (default: today)
        last_updated:          YYYY-MM-DD (default: today)
        related_themes:        list of theme slugs implicated by this failure
        related_subjects:      list of subject_ids it has affected
        tags:                  list of strings (always merged with ['failure_mode'])
        evidence:              optional initial evidence block (str)

    Body shape:
        # Title
        ## Symptom
        ## Diagnosis
        ## Mitigation
        ## Related (optional — only when related_themes / related_subjects)
        ## Evidence (append-only log)
    """
    slug = str(failure_mode.get("slug") or "").strip()
    if not slug:
        raise ValueError("failure_mode.slug is required")

    title = str(failure_mode.get("title") or slug.replace("-", " ").title())
    symptom = str(failure_mode.get("symptom") or "").strip()
    diagnosis = str(failure_mode.get("diagnosis") or "").strip()
    mitigation = str(failure_mode.get("mitigation") or "").strip()
    if not symptom:
        raise ValueError("failure_mode.symptom is required")
    if not diagnosis:
        raise ValueError("failure_mode.diagnosis is required")
    if not mitigation:
        raise ValueError("failure_mode.mitigation is required")

    status = str(failure_mode.get("status") or "active").strip()
    if status not in _FAILURE_MODE_STATUSES:
        raise ValueError(
            f"failure_mode.status must be one of {_FAILURE_MODE_STATUSES}, got {status!r}"
        )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    opened = str(failure_mode.get("opened") or today)
    last_updated = str(failure_mode.get("last_updated") or today)
    related_themes = list(failure_mode.get("related_themes") or [])
    related_subjects = [str(s) for s in (failure_mode.get("related_subjects") or []) if s]
    tags = list(failure_mode.get("tags") or [])
    if "failure_mode" not in tags:
        tags = ["failure_mode"] + tags

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    fm_lines = [
        "---",
        "domain: vault",
        "note_type: failure_mode",
        "kind: failure_mode",
        f"slug: {_yaml_scalar(slug)}",
        f"title: {_yaml_scalar(title)}",
        f"status: {_yaml_scalar(status)}",
        f"opened: {_yaml_scalar(opened)}",
        f"last_updated: {_yaml_scalar(last_updated)}",
        f"date: {_yaml_scalar(last_updated)}",
        f"related_themes: {_yaml_string_list(related_themes)}",
        f"related_subjects: {_yaml_string_list(related_subjects)}",
        f'generated_at: "{now_iso}"',
        "tags:",
    ] + [f"  - {t}" for t in tags] + ["---"]

    body_parts = [
        f"# {title}",
        "",
        "## Symptom",
        "",
        symptom,
        "",
        "## Diagnosis",
        "",
        diagnosis,
        "",
        "## Mitigation",
        "",
        mitigation,
        "",
    ]

    if related_themes or related_subjects:
        body_parts += ["## Related", ""]
        if related_themes:
            body_parts.append("**Themes:**")
            body_parts += [f"- {format_wikilink(s)}" for s in related_themes]
            body_parts.append("")
        if related_subjects:
            body_parts.append("**Subjects:** " + ", ".join(related_subjects))
            body_parts.append("")

    body_parts += ["## Evidence", ""]
    initial_evidence = failure_mode.get("evidence")
    if isinstance(initial_evidence, str) and initial_evidence.strip():
        body_parts.append(_format_evidence_block(initial_evidence, last_updated))
    else:
        body_parts.append("*(No evidence recorded yet.)*")
        body_parts.append("")

    content = "\n".join(fm_lines) + "\n" + "\n".join(body_parts)
    filename = f"failure-modes/{slug}.md"
    return filename, content


# ═══════════════════════════════════════════════════════════════
# DASHBOARD NOTE — dual-output materialised view (ADR 0007)
# ═══════════════════════════════════════════════════════════════

def render_dashboard_note(
    *,
    name: str,
    title: str,
    description: str,
    columns: list[str],
    rows: list[list],
    dataview_query: str | None = None,
    dataview_note: str | None = None,
    last_updated: str | None = None,
) -> tuple[str, str]:
    """
    Render a dashboard note implementing the ADR 0007 dual-output
    pattern: the framework writes a plain-markdown snapshot table
    (the source-of-truth view that any reader and the LLM see),
    optionally accompanied by a Dataview live-query block (an
    additive view rendered for analysts using Obsidian + Dataview).

    Both views are materialised from the same SQLite vault index,
    so they cannot disagree about anything except freshness.

    Args:
        name:            slug-like dashboard identifier (e.g. ``"open-themes"``).
        title:           Human title rendered as the H1 heading.
        description:     1–2 sentences explaining what the dashboard shows.
        columns:         Snapshot table column headers.
        rows:            List of rows; each row is a list aligned with ``columns``.
        dataview_query:  Optional Dataview DQL. When provided, an extra
                         ```` ```dataview ```` fence is emitted above the
                         snapshot. Renders only for users with the plugin;
                         degrades gracefully (the snapshot is always present).
        dataview_note:   Optional one-line note printed above the Dataview
                         block (e.g. "Requires Obsidian + Dataview plugin").
        last_updated:    UTC ISO timestamp; defaults to ``datetime.now(utc)``.

    Returns:
        (filename, markdown). Filename is ``dashboards/{name}.md``.
    """
    if not name or not name.strip():
        raise ValueError("dashboard name is required")
    name = name.strip()
    last_updated = last_updated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    fm_lines = [
        "---",
        "domain: vault",
        "note_type: dashboard",
        "kind: dashboard",
        f"slug: {_yaml_scalar(name)}",
        f"title: {_yaml_scalar(title)}",
        f'last_updated: "{last_updated}"',
        "tags:",
        "  - dashboard",
        "---",
    ]

    body_parts = [
        f"# {title}",
        "",
        description.strip(),
        "",
        f"_Snapshot last updated: {last_updated}._",
        "",
    ]

    if dataview_query:
        body_parts += [
            "## Live view",
            "",
        ]
        if dataview_note:
            body_parts += [f"_{dataview_note}_", ""]
        else:
            body_parts += [
                "_Requires Obsidian + Dataview plugin. Falls back to the "
                "snapshot table below for any reader without the plugin._",
                "",
            ]
        body_parts += [
            "```dataview",
            dataview_query.strip(),
            "```",
            "",
        ]

    body_parts += [
        "## Snapshot",
        "",
    ]
    if not rows:
        body_parts += ["*(No rows.)*", ""]
    else:
        body_parts.append("| " + " | ".join(columns) + " |")
        body_parts.append("|" + "|".join(["---"] * len(columns)) + "|")
        for row in rows:
            cells = [str(c) if c is not None else "—" for c in row]
            body_parts.append("| " + " | ".join(cells) + " |")
        body_parts.append("")

    content = "\n".join(fm_lines) + "\n" + "\n".join(body_parts)
    filename = f"dashboards/{name}.md"
    return filename, content

"""
Running Child MCP — ChildMCP Implementation
=============================================
Wires together Strava API, running storage, and running analytics
into a complete child that registers with the parent router.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ...framework.interfaces import (
    ChildMCP,
    ConsentInfo,
    ConsentScope,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from ...framework.middleware import _dumps, _loads
from ...framework.storage import BaseStorage
from .processing import RunningProcessing
from .strava_api import StravaAPI

log = logging.getLogger("biosensor-mcp.running")

STREAM_CACHE_TTL_DAYS = int(os.environ.get("STRAVA_STREAM_CACHE_TTL_DAYS", "7"))

ALL_STREAM_TYPES = [
    "heartrate", "velocity_smooth", "latlng", "altitude",
    "grade_smooth", "distance", "time", "moving",
]


# ═══════════════════════════════════════════════════════════════
# RUNNING STORAGE
# ═══════════════════════════════════════════════════════════════

class RunningStorage(BaseStorage):
    """SQLite cache for Strava running data. Extends framework BaseStorage."""

    def _schema_sql(self) -> str:
        return """
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                synced_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS streams (
                activity_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stop_labels (
                activity_id INTEGER NOT NULL,
                stop_number INTEGER NOT NULL,
                label TEXT NOT NULL,
                notes TEXT,
                labeled_at TEXT NOT NULL,
                PRIMARY KEY (activity_id, stop_number)
            );
        """

    def save_activity(self, activity_id: int, data: dict):
        self.execute(
            "INSERT OR REPLACE INTO activities (id, data, synced_at) VALUES (?,?,?)",
            (activity_id, _dumps(data), datetime.now(timezone.utc).isoformat()),
        )
        self.commit()

    def get_activity(self, activity_id: int) -> dict | None:
        row = self.fetchone("SELECT data FROM activities WHERE id=?", (activity_id,))
        return _loads(row[0]) if row else None

    def list_activities(self, limit: int = 20, after: str | None = None) -> list[dict]:
        if after:
            rows = self.fetchall(
                "SELECT data FROM activities"
                " WHERE json_extract(data, '$.start_date') >= ?"
                " ORDER BY json_extract(data, '$.start_date') DESC LIMIT ?",
                (after, limit),
            )
        else:
            rows = self.fetchall(
                "SELECT data FROM activities"
                " ORDER BY json_extract(data, '$.start_date') DESC LIMIT ?",
                (limit,),
            )
        return [_loads(r[0]) for r in rows]

    def save_streams(self, activity_id: int, data: dict):
        self.execute(
            "INSERT OR REPLACE INTO streams (activity_id, data, fetched_at) VALUES (?,?,?)",
            (activity_id, _dumps(data), datetime.now(timezone.utc).isoformat()),
        )
        self.commit()

    def get_streams(self, activity_id: int) -> dict | None:
        """Return cached streams if fresh, None if stale or missing."""
        row = self.fetchone(
            "SELECT data, fetched_at FROM streams WHERE activity_id=?",
            (activity_id,),
        )
        if not row:
            return None
        data_str, fetched_at_str = row[0], row[1]
        try:
            fetched_at = datetime.fromisoformat(fetched_at_str)
            age = datetime.now(timezone.utc) - fetched_at
            if age.days >= STREAM_CACHE_TTL_DAYS:
                log.info(
                    f"Stream cache STALE for activity {activity_id} "
                    f"({age.days}d old, ttl={STREAM_CACHE_TTL_DAYS}d) — evicting"
                )
                self.execute(
                    "DELETE FROM streams WHERE activity_id=?", (activity_id,)
                )
                self.commit()
                return None
        except (ValueError, TypeError):
            pass
        return _loads(data_str)

    def save_stop_label(
        self, activity_id: int, stop_number: int, label: str, notes: str | None = None
    ):
        self.execute(
            "INSERT OR REPLACE INTO stop_labels"
            " (activity_id, stop_number, label, notes, labeled_at)"
            " VALUES (?,?,?,?,?)",
            (activity_id, stop_number, label, notes,
             datetime.now(timezone.utc).isoformat()),
        )
        self.commit()

    def get_stop_labels(self, activity_id: int) -> list[dict]:
        rows = self.fetchall(
            "SELECT stop_number, label, notes FROM stop_labels"
            " WHERE activity_id=? ORDER BY stop_number",
            (activity_id,),
        )
        return [{"stop_number": r[0], "label": r[1], "notes": r[2]} for r in rows]


# ═══════════════════════════════════════════════════════════════
# CHILD IMPLEMENTATION
# ═══════════════════════════════════════════════════════════════

class RunningChild(ChildMCP):
    """
    Strava running data child MCP.

    Owns: Strava API, running-specific storage, running analytics.
    Exposes: 13 tools across 3 tiers.

    User-configurable settings (via ~/.biosensor-mcp/user_config.json):
      - max_hr: Maximum heart rate (default 195)
      - resting_hr: Resting heart rate (default 60)
    """

    def __init__(self, config_dir: Path, data_dir: Path):
        self._config_dir = config_dir
        self._api = StravaAPI(config_dir)
        self._storage = RunningStorage(data_dir / "activities.db")
        self._processing = RunningProcessing()

        # User-configurable HR settings — loaded via child, not the API layer (#16)
        user_config = self._load_user_config()
        self._max_hr = user_config.get("max_hr", 195)
        self._resting_hr = user_config.get("resting_hr", 60)
        log.info(f"Running child initialized (max_hr={self._max_hr})")

    def _load_user_config(self) -> dict:
        """
        Load user-specific settings from ~/.biosensor-mcp/user_config.json.

        Kept here (not in StravaAPI) because user preferences are a child-layer
        concern — the API layer should only handle HTTP transport and tokens.

        Supported keys:
          max_hr      — Maximum heart rate (default 195)
          resting_hr  — Resting heart rate (default 60)
          home_lat    — Home latitude for stop proximity detection
          home_lng    — Home longitude for stop proximity detection
        """
        config_file = self._config_dir / "user_config.json"
        if config_file.exists():
            try:
                return _loads(config_file.read_text())
            except Exception as exc:
                log.warning(f"Could not read user_config.json: {exc}")
        return {}

    @property
    def domain(self) -> str:
        return "running"

    @property
    def display_name(self) -> str:
        return "Running (Strava)"

    @property
    def vaultable_tools(self) -> list[str]:
        """Tools whose results should be archived to the Obsidian vault."""
        return ["strava_run_report", "strava_trend_report", "strava_compare_runs"]

    @property
    def consent_info(self) -> ConsentInfo:
        return ConsentInfo(
            data_types=["heart rate", "GPS location", "pace", "elevation"],
            purpose="training analysis and visualization",
            scope=ConsentScope(
                duration="session",
                duration_human="until this conversation ends",
                covers_future_calls=True,
                revocable=True,
                revoke_instruction="Say 'revoke running consent' at any time.",
            ),
        )

    # ── Stream-type to data-type mapping for dynamic scope ──
    _STREAM_DATA_MAP: dict[str, list[str]] = {
        "heartrate": ["heart rate"],
        "velocity_smooth": ["pace"],
        "latlng": ["GPS location"],
        "altitude": ["elevation"],
        "grade_smooth": ["elevation"],
        "distance": ["pace"],
        "time": [],
        "moving": [],
    }

    def data_types_for_tool(self, tool_name: str, params: dict) -> list[str]:
        """
        Return the data types actually needed for this specific call.

        For downsampled/full streams, narrows scope to only the streams
        the user requested. For other tools, returns full consent scope.
        """
        if tool_name in ("strava_downsampled_streams", "strava_full_streams"):
            requested = params.get("streams")
            if requested:
                types: set[str] = set()
                for stream in requested:
                    types.update(self._STREAM_DATA_MAP.get(stream, []))
                if types:
                    return sorted(types)
        # Default: full domain scope
        return self.consent_info.data_types

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            # ── Tier 1: Free (server-computed reports) ──
            ToolDefinition(
                "strava_sync", 1,
                "Sync recent activities from Strava into local cache.",
                {"days_back": {"type": "integer", "description": "Days back to sync (default 60)", "required": False}},
            ),
            ToolDefinition(
                "strava_list_runs", 1,
                "List recent running activities with summary stats.",
                {
                    "limit": {"type": "integer", "description": "Max results (default 20)", "required": False},
                    "after": {"type": "string", "description": "Only runs after this date (YYYY-MM-DD)", "required": False},
                },
            ),
            ToolDefinition(
                "strava_activity_detail", 1,
                "Get full details for a specific activity.",
                {"activity_id": {"type": "integer", "description": "Strava activity ID", "required": True}},
            ),
            ToolDefinition(
                "strava_hr_analysis", 1,
                "Server-computed HR zones, drift, anomalies. Raw data stays on server. ~200-500 tokens.",
                {"activity_id": {"type": "integer", "description": "Strava activity ID", "required": True}},
            ),
            ToolDefinition(
                "strava_pace_analysis", 1,
                "Server-computed mile splits and run/walk classification. ~200-500 tokens.",
                {"activity_id": {"type": "integer", "description": "Strava activity ID", "required": True}},
            ),
            ToolDefinition(
                "strava_stop_analysis", 1,
                "Detect pauses/stops using GPS + velocity. Returns locations, durations, and saved labels.",
                {"activity_id": {"type": "integer", "description": "Strava activity ID", "required": True}},
            ),
            ToolDefinition(
                "strava_label_stop", 1,
                "Save what happened at a stop (e.g. 'Gel 1/3', 'electrolytes', 'bathroom'). Persists across sessions.",
                {
                    "activity_id": {"type": "integer", "description": "Strava activity ID", "required": True},
                    "stop_number": {"type": "integer", "description": "Stop number from stop_analysis (1-indexed)", "required": True},
                    "label": {"type": "string", "description": "Short label", "required": True},
                    "notes": {"type": "string", "description": "Optional details", "required": False},
                },
            ),
            ToolDefinition(
                "strava_run_report", 1,
                "Comprehensive single-run report: decoupling, efficiency factor, HR drift, "
                "run phases, GAP splits, anomaly detection. All server-side. ~800 tokens.",
                {"activity_id": {"type": "integer", "description": "Strava activity ID", "required": True}},
            ),
            ToolDefinition(
                "strava_trend_report", 1,
                "Rolling fitness trends: weekly volume, avg pace, avg HR, longest run. ~600 tokens.",
                {
                    "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)", "required": True},
                    "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)", "required": True},
                },
            ),
            ToolDefinition(
                "strava_compare_runs", 1,
                "Side-by-side comparison of 2-5 activities: pace, HR, drift, EF. ~1500 tokens.",
                {"activity_ids": {"type": "array", "description": "List of 2-5 activity IDs", "required": True}},
            ),
            # ── Tier 2: Consent-gated (downsampled streams) ──
            ToolDefinition(
                "strava_downsampled_streams", 2,
                "Downsampled streams at 5-30s intervals for visualization. ~3000-7000 tokens. "
                "Requires biometric consent.",
                {
                    "activity_id": {"type": "integer", "description": "Strava activity ID", "required": True},
                    "interval_seconds": {"type": "integer", "description": "Sample interval: 5-30s (default 10)", "required": False},
                    "streams": {
                        "type": "array",
                        "description": f"Which streams to include: {', '.join(ALL_STREAM_TYPES)}. Default: all.",
                        "required": False,
                    },
                },
            ),
            # ── Tier 3: Cost-gated (full per-second streams) ──
            ToolDefinition(
                "strava_full_streams", 3,
                "Per-second streams with precision reduction and selective filtering. "
                "Specify only needed streams to reduce cost. ~25k-60k tokens. "
                "Requires consent + cost approval if over 35k tokens.",
                {
                    "activity_id": {"type": "integer", "description": "Strava activity ID", "required": True},
                    "streams": {
                        "type": "array",
                        "description": f"Which streams: {', '.join(ALL_STREAM_TYPES)}. Default: all.",
                        "required": False,
                    },
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {
            "strava_sync": {
                "days_back": ValidationSchema(type=int, min=1, max=365, default=60),
            },
            "strava_list_runs": {
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
                "after": ValidationSchema(type=str, pattern=r"^\d{4}-\d{2}-\d{2}$"),
            },
            "strava_activity_detail": {
                "activity_id": ValidationSchema(type=int, min=1, required=True),
            },
            "strava_hr_analysis": {
                "activity_id": ValidationSchema(type=int, min=1, required=True),
            },
            "strava_pace_analysis": {
                "activity_id": ValidationSchema(type=int, min=1, required=True),
            },
            "strava_stop_analysis": {
                "activity_id": ValidationSchema(type=int, min=1, required=True),
            },
            "strava_label_stop": {
                "activity_id": ValidationSchema(type=int, min=1, required=True),
                "stop_number": ValidationSchema(type=int, min=1, required=True),
                "label": ValidationSchema(type=str, required=True),
                "notes": ValidationSchema(type=str),
            },
            "strava_run_report": {
                "activity_id": ValidationSchema(type=int, min=1, required=True),
            },
            "strava_trend_report": {
                "start_date": ValidationSchema(type=str, pattern=r"^\d{4}-\d{2}-\d{2}$", required=True),
                "end_date": ValidationSchema(type=str, pattern=r"^\d{4}-\d{2}-\d{2}$", required=True),
            },
            "strava_compare_runs": {
                "activity_ids": ValidationSchema(type=list, min_len=2, max_len=5, required=True),
            },
            "strava_downsampled_streams": {
                "activity_id": ValidationSchema(type=int, min=1, required=True),
                "interval_seconds": ValidationSchema(type=int, min=5, max=30, default=10),
                "streams": ValidationSchema(type=list, allowed_values=ALL_STREAM_TYPES),
            },
            "strava_full_streams": {
                "activity_id": ValidationSchema(type=int, min=1, required=True),
                "streams": ValidationSchema(type=list, allowed_values=ALL_STREAM_TYPES),
            },
        }

    # ══════════════════════════════════════════════════════════
    # COST ESTIMATION (pre-execution, cheap)
    # ══════════════════════════════════════════════════════════

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        """
        Estimate token cost BEFORE execution.

        Only strava_full_streams can be expensive enough to matter.
        Uses stream metadata (point count * stream count) — no serialization.
        """
        if tool_name != "strava_full_streams":
            return CostEstimate(tokens=0)

        streams = self._load_streams(params["activity_id"])
        if not streams:
            return CostEstimate(tokens=0)

        requested = params.get("streams")

        # Estimate full cost from metadata
        full_tokens = self._processing.estimate_stream_tokens(streams, requested)

        # Estimate downsampled alternative
        ds = self._processing.downsample(streams, interval=10)
        ds_tokens = self._processing.estimate_stream_tokens(ds, requested)

        return CostEstimate(
            tokens=full_tokens,
            has_cheaper_alternative=True,
            alternative_tokens=ds_tokens,
            alternative_description="strava_downsampled_streams (5-30s intervals) — preserves curve shape, ~85% cheaper",
        )

    # ══════════════════════════════════════════════════════════
    # EXECUTION
    # ══════════════════════════════════════════════════════════

    async def execute(self, tool_name: str, params: dict) -> dict:
        """Route to the correct handler."""
        handlers = {
            "strava_sync": self._handle_sync,
            "strava_list_runs": self._handle_list_runs,
            "strava_activity_detail": self._handle_activity_detail,
            "strava_hr_analysis": self._handle_hr_analysis,
            "strava_pace_analysis": self._handle_pace_analysis,
            "strava_stop_analysis": self._handle_stop_analysis,
            "strava_label_stop": self._handle_label_stop,
            "strava_run_report": self._handle_run_report,
            "strava_trend_report": self._handle_trend_report,
            "strava_compare_runs": self._handle_compare_runs,
            "strava_downsampled_streams": self._handle_downsampled_streams,
            "strava_full_streams": self._handle_full_streams,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        return await handler(params)

    # ── Data Loading ──

    def _load_streams(self, activity_id: int) -> dict | None:
        """Load from cache or fetch from Strava API. Raises on API failure."""
        cached = self._storage.get_streams(activity_id)
        if cached:
            return cached
        try:
            raw = self._api.get(
                f"activities/{activity_id}/streams",
                keys=",".join(ALL_STREAM_TYPES),
                key_type="time",
            )
            if not raw:
                return None
            streams = {s["type"]: s["data"] for s in raw}
            self._storage.save_streams(activity_id, streams)
            return streams
        except Exception as e:
            log.error(f"Failed to fetch streams for {activity_id}: {e}")
            raise RuntimeError(f"Could not load stream data: {e}") from e

    # ══════════════════════════════════════════════════════════
    # TIER 1 HANDLERS
    # ══════════════════════════════════════════════════════════

    async def _handle_sync(self, params: dict) -> dict:
        days = params.get("days_back", 60)
        after_epoch = int(
            (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        )
        page, total = 1, 0
        while True:
            activities = self._api.get(
                "athlete/activities", after=after_epoch, per_page=50, page=page
            )
            if not activities:
                break
            for a in activities:
                if a.get("type") == "Run":
                    self._storage.save_activity(a["id"], a)
                    total += 1
            page += 1
            if len(activities) < 50:
                break
        return {"synced": total, "days_back": days}

    async def _handle_list_runs(self, params: dict) -> dict:
        activities = self._storage.list_activities(
            limit=params.get("limit", 20), after=params.get("after")
        )
        return {
            "count": len(activities),
            "runs": [
                {
                    "id": a["id"],
                    "name": a.get("name", ""),
                    "start_date": a.get("start_date", ""),
                    "distance_miles": round(a.get("distance", 0) / 1609.34, 2),
                    "moving_time_minutes": round(a.get("moving_time", 0) / 60, 1),
                    "elapsed_time_minutes": round(a.get("elapsed_time", 0) / 60, 1),
                    "avg_speed_mph": round(a.get("average_speed", 0) * 2.237, 1),
                    "avg_heartrate": a.get("average_heartrate"),
                    "max_heartrate": a.get("max_heartrate"),
                    "total_elevation_gain_ft": round(
                        a.get("total_elevation_gain", 0) * 3.281, 0
                    ),
                }
                for a in activities
            ],
        }

    async def _handle_activity_detail(self, params: dict) -> dict:
        aid = params["activity_id"]
        data = self._storage.get_activity(aid)
        if not data:
            try:
                data = self._api.get(f"activities/{aid}")
                if data:
                    self._storage.save_activity(aid, data)
            except Exception as e:
                return {"error": f"Activity {aid} not found: {e}"}
        if not data:
            return {"error": f"Activity {aid} not found"}
        return {
            "id": data["id"],
            "name": data.get("name", ""),
            "start_date": data.get("start_date", ""),
            "distance_miles": round(data.get("distance", 0) / 1609.34, 2),
            "moving_time_minutes": round(data.get("moving_time", 0) / 60, 1),
            "elapsed_time_minutes": round(data.get("elapsed_time", 0) / 60, 1),
            "avg_heartrate": data.get("average_heartrate"),
            "max_heartrate": data.get("max_heartrate"),
            "avg_speed_mph": round(data.get("average_speed", 0) * 2.237, 1),
            "total_elevation_gain_ft": round(
                data.get("total_elevation_gain", 0) * 3.281, 0
            ),
            "calories": data.get("calories"),
            "description": data.get("description"),
        }

    async def _handle_hr_analysis(self, params: dict) -> dict:
        streams = self._load_streams(params["activity_id"])
        if not streams or "heartrate" not in streams:
            return {"error": "No HR data available for this activity"}
        hr = streams["heartrate"]
        vel = streams.get("velocity_smooth", [])
        return {
            "activity_id": params["activity_id"],
            "zones": self._processing.compute_hr_zones(
                hr, max_hr=self._max_hr, resting_hr=self._resting_hr
            ),
            "drift": self._processing.compute_hr_drift(hr),
            "anomalies": [
                a
                for a in self._processing.detect_anomalies(hr, vel)
                if a["type"].startswith("hr_")
            ],
            "data_points": len(hr),
            "note": "Computed server-side. Raw per-second HR data not transmitted.",
        }

    async def _handle_pace_analysis(self, params: dict) -> dict:
        streams = self._load_streams(params["activity_id"])
        if not streams or "distance" not in streams:
            return {"error": "No distance data available"}
        splits = self._processing.compute_mile_splits(
            streams["distance"],
            streams.get("time", []),
            streams.get("velocity_smooth"),
        )
        vel = streams.get("velocity_smooth", [])
        walking = sum(1 for v in vel if v < 1.5) if vel else 0
        running = len(vel) - walking if vel else 0
        return {
            "activity_id": params["activity_id"],
            "mile_splits": splits,
            "classification": {
                "running_seconds": running,
                "walking_seconds": walking,
                "pct_running": round(running / max(len(vel), 1) * 100, 1),
            },
            "note": "Computed server-side. Raw per-second pace data not transmitted.",
        }

    async def _handle_stop_analysis(self, params: dict) -> dict:
        streams = self._load_streams(params["activity_id"])
        if not streams or "velocity_smooth" not in streams:
            return {"error": "No velocity data available"}
        # Pass home_coords from user config so nearby stops can be flagged (#8)
        user_cfg = self._load_user_config()
        home_lat = user_cfg.get("home_lat")
        home_lng = user_cfg.get("home_lng")
        home_coords = (
            (home_lat, home_lng)
            if home_lat is not None and home_lng is not None
            else None
        )
        stops = self._processing.detect_stops(
            streams.get("latlng", []),
            streams["velocity_smooth"],
            streams.get("time", []),
            home_coords=home_coords,
        )
        labels = self._storage.get_stop_labels(params["activity_id"])
        label_map = {lbl["stop_number"]: lbl for lbl in labels}
        for stop in stops:
            info = label_map.get(stop["stop_number"])
            if info:
                stop["label"] = info["label"]
                stop["notes"] = info["notes"]
        return {
            "activity_id": params["activity_id"],
            "stop_count": len(stops),
            "stops": stops,
        }

    async def _handle_label_stop(self, params: dict) -> dict:
        self._storage.save_stop_label(
            params["activity_id"],
            params["stop_number"],
            params["label"],
            params.get("notes"),
        )
        return {
            "saved": True,
            "activity_id": params["activity_id"],
            "stop_number": params["stop_number"],
            "label": params["label"],
        }

    async def _handle_run_report(self, params: dict) -> dict:
        """Comprehensive report. ~800 tokens. All computed server-side."""
        streams = self._load_streams(params["activity_id"])
        if not streams:
            return {"error": "No stream data available"}

        hr = streams.get("heartrate", [])
        vel = streams.get("velocity_smooth", [])
        grade = streams.get("grade_smooth", [])
        dist = streams.get("distance", [])
        time_arr = streams.get("time", [])
        p = self._processing

        # Include activity metadata so downstream consumers (e.g. VaultWriter)
        # don't need direct access to RunningStorage.
        activity_id = params["activity_id"]
        detail = self._storage.get_activity(activity_id)
        report: dict = {
            "activity_id": activity_id,
            "data_points": max(len(hr), len(vel)),
        }
        if detail:
            report["activity_name"] = detail.get("name")
            report["start_date"] = detail.get("start_date")
            report["distance"] = detail.get("distance")
            report["moving_time"] = detail.get("moving_time")
            report["average_heartrate"] = detail.get("average_heartrate")
            report["max_heartrate"] = detail.get("max_heartrate")
        if hr and vel:
            report["decoupling"] = p.compute_decoupling(hr, vel)
            report["efficiency_factor"] = p.compute_efficiency_factor(hr, vel, grade)
        if hr:
            report["hr_drift"] = p.compute_hr_drift(hr)
            report["hr_zones"] = p.compute_hr_zones(hr, max_hr=self._max_hr)
        if vel and time_arr:
            report["phases"] = p.detect_run_phases(vel, time_arr)
        if dist and time_arr:
            report["mile_splits"] = p.compute_mile_splits(dist, time_arr, vel)
        if grade and vel and dist and time_arr:
            report["gap_splits"] = p.compute_gap_splits(vel, grade, dist, time_arr)
        if hr or vel:
            report["anomalies"] = p.detect_anomalies(hr, vel)
        report["note"] = (
            "Full report computed server-side from per-second data. "
            "Raw streams not transmitted."
        )
        return report

    async def _handle_trend_report(self, params: dict) -> dict:
        activities = self._storage.list_activities(
            limit=200, after=params["start_date"]
        )
        end = params["end_date"]
        activities = [a for a in activities if a.get("start_date", "")[:10] <= end]
        if not activities:
            return {"error": "No activities found in date range"}

        weeks: dict[str, list] = {}
        for a in activities:
            date = a.get("start_date", "")[:10]
            try:
                dt = datetime.strptime(date, "%Y-%m-%d")
                week_key = dt.strftime("%Y-W%V")
            except ValueError:
                continue
            weeks.setdefault(week_key, []).append(a)

        weekly_stats = []
        for week, runs in sorted(weeks.items()):
            total_dist = sum(r.get("distance", 0) for r in runs) / 1609.34
            total_time = sum(r.get("moving_time", 0) for r in runs) / 60
            hrs = [
                r.get("average_heartrate")
                for r in runs
                if r.get("average_heartrate")
            ]
            longest = max((r.get("distance", 0) for r in runs), default=0) / 1609.34
            weekly_stats.append(
                {
                    "week": week,
                    "runs": len(runs),
                    "total_miles": round(total_dist, 1),
                    "total_minutes": round(total_time, 1),
                    "avg_hr": round(sum(hrs) / len(hrs)) if hrs else None,
                    "longest_run_miles": round(longest, 1),
                }
            )

        return {
            "date_range": {"start": params["start_date"], "end": params["end_date"]},
            "total_runs": len(activities),
            "weeks": weekly_stats,
        }

    async def _handle_compare_runs(self, params: dict) -> dict:
        comparisons = []
        for aid in params["activity_ids"]:
            detail = self._storage.get_activity(aid)
            if not detail:
                try:
                    detail = self._api.get(f"activities/{aid}")
                    if detail:
                        self._storage.save_activity(aid, detail)
                except Exception:
                    detail = None

            entry: dict = {
                "activity_id": aid,
                "name": detail.get("name", "") if detail else "",
                "date": detail.get("start_date", "")[:10] if detail else "",
                "distance_miles": round(detail.get("distance", 0) / 1609.34, 2)
                if detail
                else 0,
                "moving_time_min": round(detail.get("moving_time", 0) / 60, 1)
                if detail
                else 0,
                "avg_hr": detail.get("average_heartrate") if detail else None,
                "max_hr": detail.get("max_heartrate") if detail else None,
            }

            try:
                streams = self._load_streams(aid) if detail else None
            except Exception:
                streams = None

            if streams:
                hr = streams.get("heartrate", [])
                vel = streams.get("velocity_smooth", [])
                if hr:
                    entry["hr_drift"] = self._processing.compute_hr_drift(hr)
                if hr and vel:
                    entry["decoupling"] = self._processing.compute_decoupling(hr, vel)
                    entry["efficiency_factor"] = (
                        self._processing.compute_efficiency_factor(hr, vel)
                    )

            comparisons.append(entry)

        return {"comparisons": comparisons}

    # ══════════════════════════════════════════════════════════
    # TIER 2 HANDLER
    # ══════════════════════════════════════════════════════════

    async def _handle_downsampled_streams(self, params: dict) -> dict:
        streams = self._load_streams(params["activity_id"])
        if not streams:
            return {"error": "No stream data available"}
        interval = params.get("interval_seconds", 10)
        requested = params.get("streams")
        downsampled = self._processing.downsample(streams, interval=interval)
        filtered = self._processing.filter_streams(downsampled, requested)
        reduced = self._processing.reduce_precision(filtered)
        original = len(next(iter(streams.values()), []))
        new = len(next(iter(reduced.values()), []))
        return {
            "activity_id": params["activity_id"],
            "interval_seconds": interval,
            "streams_included": list(reduced.keys()),
            "original_points": original,
            "downsampled_points": new,
            "reduction_pct": round((1 - new / max(original, 1)) * 100, 1),
            "streams": reduced,
        }

    # ══════════════════════════════════════════════════════════
    # TIER 3 HANDLER
    # ══════════════════════════════════════════════════════════

    async def _handle_full_streams(self, params: dict) -> dict:
        streams = self._load_streams(params["activity_id"])
        if not streams:
            return {"error": "No stream data available"}
        requested = params.get("streams")
        filtered = self._processing.filter_streams(streams, requested)
        reduced = self._processing.reduce_precision(filtered)
        points = len(next(iter(reduced.values()), []))
        return {
            "activity_id": params["activity_id"],
            "streams_included": list(reduced.keys()),
            "data_points": points,
            "streams": reduced,
        }

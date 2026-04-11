"""
Demo runner — execute analytics against synthetic data and print results.

Usage:
    biosensor-mcp demo
"""

import asyncio
import json
import tempfile
from pathlib import Path

from .sample_data import generate_sample_streams, generate_sample_activity, SAMPLE_ACTIVITY_ID


def run_demo():
    """Run the full analytics pipeline against synthetic data."""
    print("Biosensor MCP — Demo Mode")
    print("=" * 50)
    print("Running analytics on synthetic 60-minute run data.")
    print("No Strava account or OAuth tokens required.\n")

    # Generate synthetic data
    streams = generate_sample_streams()
    activity = generate_sample_activity()

    points = len(streams["heartrate"])
    dist_miles = round(streams["distance"][-1] / 1609.34, 2)
    print(f"Generated: {points} data points, {dist_miles} miles")
    print(f"Activity:  {activity['name']}")
    print()

    # Use a temp directory so we don't pollute user's real config
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "config"
        data_dir = Path(tmpdir) / "data"
        config_dir.mkdir()
        data_dir.mkdir()

        # Write a minimal user config
        (config_dir / "user_config.json").write_text(
            json.dumps({"max_hr": 185, "resting_hr": 52})
        )

        # Write a dummy tokens file so RunningChild can initialize
        (config_dir / "tokens.json").write_text(
            json.dumps({"client_id": "demo", "client_secret": "demo",
                         "access_token": "demo", "refresh_token": "demo",
                         "expires_at": 0})
        )

        from biosensor_mcp.children.running.child import RunningChild

        child = RunningChild(config_dir=config_dir, data_dir=data_dir)

        # Inject synthetic data into the storage layer
        child._storage.save_activity(SAMPLE_ACTIVITY_ID, activity)
        child._storage.save_streams(SAMPLE_ACTIVITY_ID, streams)

        # Run analytics tools
        tools = [
            ("strava_run_report", {"activity_id": SAMPLE_ACTIVITY_ID}),
            ("strava_hr_analysis", {"activity_id": SAMPLE_ACTIVITY_ID}),
            ("strava_pace_analysis", {"activity_id": SAMPLE_ACTIVITY_ID}),
        ]

        for tool_name, params in tools:
            print(f"--- {tool_name} ---")
            result = asyncio.run(child.execute(tool_name, params))
            print(json.dumps(result, indent=2, default=str))
            print()

        # Close SQLite connections to release WAL locks (Windows compatibility)
        conn = getattr(child._storage._local, "conn", None)
        if conn:
            conn.close()

    print("=" * 50)
    print("Demo complete. All analytics computed server-side from synthetic data.")
    print("In production, this data comes from Strava. Run 'biosensor-mcp setup' to connect.")

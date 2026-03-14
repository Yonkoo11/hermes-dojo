#!/usr/bin/env python3
"""
Hermes Dojo — Learning Curve Tracker

Persists performance metrics over time to show improvement trends.
Stores daily snapshots in a JSON file.

Usage:
    python3 tracker.py save              # Save current metrics snapshot
    python3 tracker.py history           # Show learning curve
    python3 tracker.py history --json    # Output history as JSON
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
DATA_DIR = HERMES_HOME / "skills" / "hermes-dojo" / "data"
METRICS_FILE = DATA_DIR / "metrics.json"


def load_metrics() -> list[dict]:
    """Load historical metrics."""
    if METRICS_FILE.exists():
        try:
            with open(METRICS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def save_snapshot(monitor_data: dict, improvements: list[dict] = None):
    """Save a metrics snapshot."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    history = load_metrics()

    snapshot = {
        "timestamp": time.time(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sessions_analyzed": monitor_data.get("sessions_analyzed", 0),
        "total_tool_calls": monitor_data.get("total_tool_calls", 0),
        "overall_success_rate": monitor_data.get("overall_success_rate", 0),
        "total_errors": monitor_data.get("total_errors", 0),
        "user_corrections": monitor_data.get("user_corrections", 0),
        "skill_gaps": len(monitor_data.get("skill_gaps", [])),
        "retry_patterns": len(monitor_data.get("retry_patterns", [])),
        "weakest_tools": [
            {"tool": t["tool"], "success_rate": t["success_rate"], "errors": t["errors"]}
            for t in monitor_data.get("weakest_tools", [])[:5]
        ],
    }

    if improvements:
        snapshot["improvements_made"] = improvements

    history.append(snapshot)

    # Keep last 90 days of snapshots
    cutoff = time.time() - (90 * 86400)
    history = [h for h in history if h.get("timestamp", 0) > cutoff]

    with open(METRICS_FILE, "w") as f:
        json.dump(history, f, indent=2)

    return snapshot


def print_history():
    """Print the learning curve."""
    history = load_metrics()

    if not history:
        print("No metrics history yet. Run '/dojo analyze' first.")
        return

    print("=" * 60)
    print("  HERMES DOJO — LEARNING CURVE")
    print("=" * 60)
    print()
    print(f"  {'Date':<20} {'Success Rate':>12} {'Tool Calls':>11} {'Errors':>7} {'Corrections':>12}")
    print("  " + "-" * 62)

    for snap in history[-30:]:  # Last 30 entries
        date = snap.get("date", "unknown")
        rate = snap.get("overall_success_rate", 0)
        calls = snap.get("total_tool_calls", 0)
        errors = snap.get("total_errors", 0)
        corrections = snap.get("user_corrections", 0)
        print(f"  {date:<20} {rate:>11.1f}% {calls:>11} {errors:>7} {corrections:>12}")

    # Trend
    if len(history) >= 2:
        first = history[0].get("overall_success_rate", 0)
        last = history[-1].get("overall_success_rate", 0)
        delta = last - first
        trend = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
        print()
        print(f"  Trend: {first:.1f}% → {last:.1f}% ({'+' if delta > 0 else ''}{delta:.1f}%) {trend}")

    # Sparkline
    if len(history) >= 3:
        rates = [h.get("overall_success_rate", 0) for h in history[-10:]]
        blocks = " ▁▂▃▄▅▆▇█"
        min_r, max_r = min(rates), max(rates)
        span = max_r - min_r
        if span == 0:
            sparkline = "█" * len(rates)
        else:
            sparkline = "".join(
                blocks[min(8, int((r - min_r) / span * 8))] for r in rates
            )
        print(f"  Sparkline: [{sparkline}]")

    print()
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Dojo Learning Curve Tracker")
    parser.add_argument("action", choices=["save", "history"], help="Action to perform")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.action == "save":
        # Run monitor to get current data
        sys.path.insert(0, str(Path(__file__).parent))
        from monitor import analyze_sessions
        data = analyze_sessions()
        snapshot = save_snapshot(data)
        if args.json:
            print(json.dumps(snapshot, indent=2))
        else:
            print(f"Snapshot saved: {snapshot['date']} — {snapshot['overall_success_rate']}% success rate")

    elif args.action == "history":
        if args.json:
            print(json.dumps(load_metrics(), indent=2))
        else:
            print_history()

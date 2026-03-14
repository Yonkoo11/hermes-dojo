#!/usr/bin/env python3
"""
Hermes Dojo — Demo Runner

Runs the full Dojo pipeline for demo recording:
1. Seeds demo data (realistic failures)
2. Runs monitor analysis
3. Shows weaknesses
4. Applies fixes (creates/patches skills)
5. Shows improvement report
6. Saves snapshot to learning curve

Usage:
    python3 demo.py              # Full demo flow
    python3 demo.py --reset      # Clear all demo data first
    python3 demo.py --telegram   # Show Telegram-formatted report
"""

import json
import os
import sys
import time
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent))

from monitor import analyze_sessions
from analyzer import generate_recommendations, print_recommendations
from fixer import generate_fix_plan, apply_fixes, print_fix_plan
from reporter import generate_report
from tracker import save_snapshot, print_history, load_metrics, METRICS_FILE, DATA_DIR


def seed_learning_curve():
    """Pre-populate metrics history with a realistic multi-day improvement arc.

    Shows what happens when Dojo runs nightly:
    Day 1-2: baseline (bad), Day 3-4: first fixes kick in, Day 5: current run.
    This makes the sparkline and trend line meaningful in the demo.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # The narrative: Dojo has been running nightly for 4 days.
    # Each day it finds failures, creates/patches skills, and success rate climbs.
    # Today's run (Day 5) will add the current snapshot on top.
    # Values are chosen so today's 57.1% seed data fits as "new batch of sessions"
    # but the trend line from Day 1 → Day 5 still shows clear improvement.
    history = [
        {
            "timestamp": time.time() - 5 * 86400,
            "date": "Day 1 (baseline)",
            "sessions_analyzed": 10,
            "total_tool_calls": 38,
            "overall_success_rate": 34.2,
            "total_errors": 25,
            "user_corrections": 12,
            "skill_gaps": 7,
            "weakest_tools": [
                {"tool": "web_extract", "success_rate": 0.0, "errors": 10},
                {"tool": "execute_code", "success_rate": 10.0, "errors": 9},
                {"tool": "terminal_run", "success_rate": 45.0, "errors": 6},
            ],
        },
        {
            "timestamp": time.time() - 4 * 86400,
            "date": "Day 2 (first fixes)",
            "sessions_analyzed": 14,
            "total_tool_calls": 48,
            "overall_success_rate": 41.7,
            "total_errors": 28,
            "user_corrections": 9,
            "skill_gaps": 5,
            "weakest_tools": [
                {"tool": "web_extract", "success_rate": 8.3, "errors": 7},
                {"tool": "execute_code", "success_rate": 25.0, "errors": 6},
            ],
            "improvements_made": [
                {"action": "create", "target": "terminal-run", "description": "Branch check + path validation"},
                {"action": "create", "target": "web-extract", "description": "Timeout handling"},
            ],
        },
        {
            "timestamp": time.time() - 3 * 86400,
            "date": "Day 3 (patching)",
            "sessions_analyzed": 18,
            "total_tool_calls": 55,
            "overall_success_rate": 47.3,
            "total_errors": 29,
            "user_corrections": 7,
            "skill_gaps": 4,
            "weakest_tools": [
                {"tool": "web_extract", "success_rate": 16.7, "errors": 5},
                {"tool": "execute_code", "success_rate": 35.0, "errors": 4},
            ],
            "improvements_made": [
                {"action": "patch", "target": "web-extract", "description": "Added curl fallback"},
                {"action": "create", "target": "csv-parsing", "description": "New skill from gap detection"},
            ],
        },
        {
            "timestamp": time.time() - 2 * 86400,
            "date": "Day 4 (evolution)",
            "sessions_analyzed": 22,
            "total_tool_calls": 62,
            "overall_success_rate": 53.2,
            "total_errors": 29,
            "user_corrections": 5,
            "skill_gaps": 3,
            "weakest_tools": [
                {"tool": "web_extract", "success_rate": 25.0, "errors": 3},
            ],
            "improvements_made": [
                {"action": "patch", "target": "execute-code", "description": "Dependency pre-check"},
                {"action": "evolve", "target": "terminal-run", "description": "GEPA optimization"},
            ],
        },
    ]

    with open(METRICS_FILE, "w") as f:
        json.dump(history, f, indent=2)


def run_demo(reset: bool = False, telegram: bool = False):
    """Run the full Dojo demo pipeline."""

    print("\n" + "=" * 60)
    print("  🥋 HERMES DOJO — DEMO")
    print("=" * 60)

    # Step 0: Optionally reset
    if reset:
        print("\n  Resetting demo data...")
        from seed_demo_data import seed_data
        seed_data(days=7, clear=True)
        time.sleep(0.5)

    # Step 1: Analyze
    print("\n  [1/6] Analyzing recent sessions...")
    time.sleep(0.5)
    data = analyze_sessions()
    print(f"        → {data['sessions_analyzed']} sessions, "
          f"{data['total_tool_calls']} tool calls, "
          f"{data['overall_success_rate']:.1f}% success rate")
    print(f"        → {data['user_corrections']} user corrections detected")
    print(f"        → {len(data['weakest_tools'])} weak tools found")
    print(f"        → {len(data['skill_gaps'])} skill gaps detected")

    # Step 2: Generate recommendations
    print("\n  [2/6] Generating improvement recommendations...")
    time.sleep(0.5)
    recs = generate_recommendations(data)
    patches = [r for r in recs if r["action"] == "patch"]
    creates = [r for r in recs if r["action"] == "create"]
    evolves = [r for r in recs if r["action"] == "evolve"]
    print(f"        → {len(patches)} skills to patch")
    print(f"        → {len(creates)} new skills to create")
    print(f"        → {len(evolves)} skills to evolve")

    # Step 3: Apply fixes
    print("\n  [3/6] Applying fixes...")
    time.sleep(0.5)
    plan = generate_fix_plan(recs, evolve=False, dry_run=False)
    improvements = apply_fixes(plan)
    for imp in improvements:
        action = imp["action"].upper()
        target = imp["target"]
        desc = imp.get("description", "")
        print(f"        → [{action}] {target}: {desc}")

    # Show a sample skill to prove quality
    SKILLS_DIR = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes")) / "skills"
    sample_targets = ["terminal-run", "web-extract", "execute-code"]
    for target in sample_targets:
        sample_path = SKILLS_DIR / target / "SKILL.md"
        if sample_path.exists():
            print(f"\n  Sample created skill ({target}):")
            print("  " + "-" * 56)
            content = sample_path.read_text()
            # Show first 20 lines
            for line in content.split("\n")[:20]:
                print(f"  {line}")
            print(f"  ... ({len(content)} chars total)")
            break

    # Step 4: Save snapshot
    print("\n  [4/6] Saving metrics snapshot...")
    time.sleep(0.3)
    snapshot = save_snapshot(data, improvements)
    print(f"        → Snapshot saved: {snapshot['date']}")

    # Step 5: Generate report
    print("\n  [5/6] Generating report...")
    time.sleep(0.3)
    fmt = "telegram" if telegram else "cli"
    # Load previous snapshot for delta comparison
    prev_history = load_metrics()
    prev = prev_history[-2] if len(prev_history) >= 2 else None
    report = generate_report(data, improvements=improvements, previous_data=prev, fmt=fmt)
    print()
    print(report)

    # Step 6: Show learning curve
    print("\n  [6/6] Learning curve:")
    time.sleep(0.3)
    print_history()

    print("\n  🥋 Dojo cycle complete.")
    print(f"     {len(improvements)} improvements applied.")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Dojo Demo Runner")
    parser.add_argument("--reset", action="store_true", help="Clear demo data first")
    parser.add_argument("--telegram", action="store_true", help="Telegram-formatted report")
    parser.add_argument("--multi-day", action="store_true", help="Simulate multi-day learning curve")
    args = parser.parse_args()

    if args.multi_day or args.reset:
        seed_learning_curve()

    run_demo(reset=args.reset, telegram=args.telegram)

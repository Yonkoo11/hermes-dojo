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
from tracker import save_snapshot, print_history


def run_demo(reset: bool = False, telegram: bool = False):
    """Run the full Dojo demo pipeline."""

    print("\n" + "=" * 60)
    print("  🥋 HERMES DOJO — DEMO")
    print("=" * 60)

    # Step 0: Optionally reset
    if reset:
        print("\n  [0/6] Resetting demo data...")
        from seed_demo_data import seed_data
        seed_data(days=7, clear=True)
        # Save initial snapshot
        data = analyze_sessions()
        save_snapshot(data)
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

    # Step 4: Save snapshot
    print("\n  [4/6] Saving metrics snapshot...")
    time.sleep(0.3)
    snapshot = save_snapshot(data, improvements)
    print(f"        → Snapshot saved: {snapshot['date']}")

    # Step 5: Generate report
    print("\n  [5/6] Generating report...")
    time.sleep(0.3)
    fmt = "telegram" if telegram else "cli"
    report = generate_report(data, improvements=improvements, format=fmt)
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
    args = parser.parse_args()

    run_demo(reset=args.reset, telegram=args.telegram)

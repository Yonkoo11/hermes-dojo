#!/usr/bin/env python3
"""
Hermes Dojo — Report Generator

Generates formatted reports for Telegram/Discord delivery or CLI display.
Combines current analysis with historical trends.

Usage:
    python3 reporter.py                  # Generate report for CLI
    python3 reporter.py --format telegram  # Telegram-formatted
    python3 reporter.py --json           # Raw JSON
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))


def generate_report(
    monitor_data: dict,
    improvements: list[dict] = None,
    previous_data: dict = None,
    format: str = "cli",
) -> str:
    """Generate a formatted improvement report."""

    sessions = monitor_data.get("sessions_analyzed", 0)
    tool_calls = monitor_data.get("total_tool_calls", 0)
    success_rate = monitor_data.get("overall_success_rate", 0)
    corrections = monitor_data.get("user_corrections", 0)
    weakest = monitor_data.get("weakest_tools", [])
    gaps = monitor_data.get("skill_gaps", [])

    # Calculate delta if we have previous data
    prev_rate = previous_data.get("overall_success_rate", 0) if previous_data else None
    delta = success_rate - prev_rate if prev_rate is not None else None

    if format == "telegram":
        return _telegram_report(
            sessions, tool_calls, success_rate, delta,
            corrections, weakest, gaps, improvements,
        )
    else:
        return _cli_report(
            sessions, tool_calls, success_rate, delta,
            corrections, weakest, gaps, improvements,
        )


def _telegram_report(
    sessions, tool_calls, success_rate, delta,
    corrections, weakest, gaps, improvements,
) -> str:
    """Telegram-formatted report (markdown)."""
    lines = [
        "🥋 *Hermes Dojo — Report*",
        "",
        f"📊 Analyzed: {sessions} sessions, {tool_calls} tool calls",
    ]

    if delta is not None:
        direction = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
        lines.append(f"{direction} Overall: {success_rate - delta:.1f}% → {success_rate:.1f}% ({'+' if delta > 0 else ''}{delta:.1f}%)")
    else:
        lines.append(f"📈 Overall success: {success_rate:.1f}%")

    if corrections:
        lines.append(f"⚠️ User corrections: {corrections}")

    if improvements:
        lines.append("")
        patched = [i for i in improvements if i.get("action") == "patch"]
        created = [i for i in improvements if i.get("action") == "create"]
        evolved = [i for i in improvements if i.get("action") == "evolve"]

        if patched:
            lines.append("✅ *Patched:*")
            for p in patched:
                lines.append(f"  • {p['target']}: {p.get('description', 'improved')}")

        if created:
            lines.append("🆕 *New skills:*")
            for c in created:
                lines.append(f"  • {c['target']}: {c.get('description', 'created')}")

        if evolved:
            lines.append("🧬 *Self-evolved:*")
            for e in evolved:
                before = e.get("before_score", "?")
                after = e.get("after_score", "?")
                lines.append(f"  • {e['target']}: {before} → {after}")

    if weakest and not improvements:
        lines.append("")
        lines.append("🔻 *Top weaknesses:*")
        for t in weakest[:3]:
            lines.append(f"  • {t['tool']}: {t['success_rate']}% ({t['errors']} errors)")

    if gaps:
        lines.append("")
        lines.append("💡 *Skill gaps:*")
        for g in gaps[:3]:
            lines.append(f"  • {g['capability']}: requested {g['requests']}x")

    # Load history for sparkline
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from tracker import load_metrics
        history = load_metrics()
        if len(history) >= 3:
            rates = [h.get("overall_success_rate", 0) for h in history[-7:]]
            blocks = " ▁▂▃▄▅▆▇█"
            min_r, max_r = min(rates), max(rates)
            span = max_r - min_r if max_r > min_r else 1
            sparkline = "".join(
                blocks[min(8, int((r - min_r) / span * 8))] for r in rates
            )
            lines.append(f"\n📉 Trend: [{sparkline}]")
    except Exception:
        pass

    lines.append(f"\n_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    return "\n".join(lines)


def _cli_report(
    sessions, tool_calls, success_rate, delta,
    corrections, weakest, gaps, improvements,
) -> str:
    """CLI-formatted report."""
    lines = [
        "=" * 60,
        "  HERMES DOJO — IMPROVEMENT REPORT",
        "=" * 60,
        f"  Sessions: {sessions} | Tool calls: {tool_calls} | Corrections: {corrections}",
    ]

    if delta is not None:
        lines.append(f"  Success rate: {success_rate - delta:.1f}% → {success_rate:.1f}% ({'+' if delta > 0 else ''}{delta:.1f}%)")
    else:
        lines.append(f"  Success rate: {success_rate:.1f}%")

    if improvements:
        lines.append("")
        lines.append("  IMPROVEMENTS MADE:")
        lines.append("  " + "-" * 56)
        for imp in improvements:
            action = imp.get("action", "?").upper()
            target = imp.get("target", "?")
            desc = imp.get("description", "")
            lines.append(f"  [{action}] {target}: {desc}")

    if weakest:
        lines.append("")
        lines.append("  REMAINING WEAKNESSES:")
        for t in weakest[:5]:
            lines.append(f"  • {t['tool']}: {t['success_rate']}% ({t['errors']} failures)")

    if gaps:
        lines.append("")
        lines.append("  SKILL GAPS:")
        for g in gaps[:5]:
            lines.append(f"  • {g['capability']}: requested {g['requests']}x")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Dojo Report Generator")
    parser.add_argument("--format", choices=["cli", "telegram"], default="cli")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--input", type=str, help="Monitor data JSON file")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            data = json.load(f)
    else:
        sys.path.insert(0, str(Path(__file__).parent))
        from monitor import analyze_sessions
        data = analyze_sessions()

    # Try to load previous snapshot for comparison
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from tracker import load_metrics
        history = load_metrics()
        prev = history[-1] if history else None
    except Exception:
        prev = None

    if args.json:
        print(json.dumps({"report": generate_report(data, format=args.format, previous_data=prev)}, indent=2))
    else:
        print(generate_report(data, format=args.format, previous_data=prev))

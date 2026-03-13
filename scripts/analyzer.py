#!/usr/bin/env python3
"""
Hermes Dojo — Weakness Analyzer

Takes raw performance data from monitor.py and produces actionable improvement
recommendations: which skills to patch, which to create, and which to evolve.

Usage:
    python3 analyzer.py                   # Analyze and recommend
    python3 analyzer.py --json            # Output as JSON
    python3 analyzer.py --input data.json # Analyze from saved monitor output
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
SKILLS_DIR = HERMES_HOME / "skills"


def find_existing_skills() -> dict[str, Path]:
    """Scan all installed skills and return name -> path mapping."""
    skills = {}
    if not SKILLS_DIR.exists():
        return skills

    for item in SKILLS_DIR.iterdir():
        if item.is_dir():
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                skills[item.name] = item
            # Check nested category dirs
            for sub in item.iterdir():
                if sub.is_dir():
                    sub_skill = sub / "SKILL.md"
                    if sub_skill.exists():
                        skills[sub.name] = sub

    return skills


def map_tool_to_skill(tool_name: str, existing_skills: dict[str, Path]) -> str | None:
    """Try to find which skill is responsible for a given tool."""
    # Direct name match
    if tool_name in existing_skills:
        return tool_name

    # Fuzzy match: tool_name contains skill name or vice versa
    tool_lower = tool_name.lower().replace("_", "-")
    for skill_name in existing_skills:
        if skill_name in tool_lower or tool_lower in skill_name:
            return skill_name

    return None


def generate_recommendations(monitor_data: dict) -> list[dict[str, Any]]:
    """Generate prioritized improvement recommendations."""
    recommendations = []
    existing_skills = find_existing_skills()

    # 1. Patch recommendations for failing tools
    for tool in monitor_data.get("weakest_tools", []):
        if tool["errors"] < 2:
            continue  # Skip one-off errors

        skill_name = map_tool_to_skill(tool["tool"], existing_skills)
        if skill_name:
            recommendations.append({
                "action": "patch",
                "priority": _priority_score(tool),
                "target": skill_name,
                "skill_path": str(existing_skills[skill_name]),
                "reason": f"{tool['tool']} fails {tool['errors']}/{tool['total']} times "
                          f"({tool['success_rate']}% success)",
                "top_error": tool["top_error"],
                "suggested_fix": _suggest_fix(tool),
            })
        else:
            # Tool has no associated skill — might benefit from one
            recommendations.append({
                "action": "create",
                "priority": _priority_score(tool),
                "target": _tool_to_skill_name(tool["tool"]),
                "reason": f"No skill found for frequently-failing tool '{tool['tool']}' "
                          f"({tool['errors']} errors)",
                "top_error": tool["top_error"],
                "suggested_fix": _suggest_fix(tool),
            })

    # 2. Create recommendations for skill gaps
    for gap in monitor_data.get("skill_gaps", []):
        cap = gap["capability"]
        if cap not in existing_skills:
            recommendations.append({
                "action": "create",
                "priority": gap["requests"] * 10,
                "target": cap,
                "reason": f"Users requested '{cap}' {gap['requests']} times but no skill exists",
                "suggested_fix": f"Create a skill for {cap} based on successful session patterns",
            })

    # 3. Evolve recommendations for skills with moderate failure rates
    for tool in monitor_data.get("weakest_tools", []):
        if tool["success_rate"] < 90 and tool["total"] >= 5:
            skill_name = map_tool_to_skill(tool["tool"], existing_skills)
            if skill_name:
                recommendations.append({
                    "action": "evolve",
                    "priority": (100 - tool["success_rate"]) * tool["total"] / 10,
                    "target": skill_name,
                    "skill_path": str(existing_skills[skill_name]),
                    "reason": f"Skill '{skill_name}' has {tool['success_rate']}% success rate "
                              f"across {tool['total']} calls — good candidate for self-evolution",
                })

    # 4. Flag retry patterns
    for retry in monitor_data.get("retry_patterns", []):
        recommendations.append({
            "action": "investigate",
            "priority": retry["count"] * 5,
            "target": retry["tool"],
            "reason": f"Tool '{retry['tool']}' called {retry['count']}x in rapid succession "
                      f"(retry loop detected)",
        })

    # Sort by priority (highest first), deduplicate by target
    seen = set()
    unique = []
    for rec in sorted(recommendations, key=lambda x: x["priority"], reverse=True):
        if rec["target"] not in seen:
            seen.add(rec["target"])
            unique.append(rec)

    return unique


def _priority_score(tool: dict) -> float:
    """Higher score = more urgent to fix."""
    error_rate = 1 - (tool["success_rate"] / 100)
    return error_rate * tool["total"] * 10


def _tool_to_skill_name(tool_name: str) -> str:
    """Convert a tool name to a valid skill name."""
    return tool_name.lower().replace("_", "-").replace(" ", "-")


def _suggest_fix(tool: dict) -> str:
    """Suggest a fix based on the error type."""
    error = tool.get("top_error", "").lower()

    if "not found" in error or "no such file" in error:
        return "Add path validation and existence checks before operations"
    if "timeout" in error:
        return "Add retry logic with exponential backoff and configurable timeout"
    if "permission" in error or "access denied" in error:
        return "Add permission checks and suggest user fix with clear instructions"
    if "command not found" in error:
        return "Add command existence check (which/command -v) before execution"
    if "syntax error" in error:
        return "Add input validation and proper escaping"
    if "rate limit" in error:
        return "Add rate limiting awareness and backoff strategy"

    return "Review failure patterns and add error handling for the most common case"


def print_recommendations(recs: list[dict]):
    """Print recommendations in human-readable format."""
    if not recs:
        print("No improvement recommendations at this time.")
        return

    print("=" * 60)
    print("  HERMES DOJO — IMPROVEMENT RECOMMENDATIONS")
    print("=" * 60)

    for i, rec in enumerate(recs[:10], 1):
        action_emoji = {"patch": "🔧", "create": "🆕", "evolve": "🧬", "investigate": "🔍"}.get(
            rec["action"], "❓"
        )
        print(f"\n  {i}. [{rec['action'].upper()}] {rec['target']}")
        print(f"     {action_emoji} {rec['reason']}")
        if rec.get("suggested_fix"):
            print(f"     → Fix: {rec['suggested_fix']}")
        if rec.get("skill_path"):
            print(f"     → Skill: {rec['skill_path']}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Dojo Weakness Analyzer")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--input", type=str, help="Read monitor data from JSON file")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            monitor_data = json.load(f)
    else:
        # Run monitor inline
        sys.path.insert(0, str(Path(__file__).parent))
        from monitor import analyze_sessions
        monitor_data = analyze_sessions()

    recs = generate_recommendations(monitor_data)

    if args.json:
        print(json.dumps(recs, indent=2, default=str))
    else:
        print_recommendations(recs)

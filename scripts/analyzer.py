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


def _classify_error_root_cause(top_error: str) -> dict:
    """Classify the root cause of an error. Returns whether it's fixable by a skill."""
    error_lower = (top_error or "").lower()

    # Infrastructure failures — no skill can fix a down service
    if any(kw in error_lower for kw in [
        "cannot connect", "connection refused", "econnrefused",
        "no such host", "dns", "unreachable",
    ]):
        return {"category": "infra", "fixable_by_skill": False, "suggestion": "Service is unreachable. Check daemon status or network connectivity."}

    # Authentication/authorization — needs config fix, not a skill
    if any(kw in error_lower for kw in [
        "unauthorized", "invalid key", "invalid credentials", "auth",
        "authentication failed", "forbidden", "403",
    ]):
        return {"category": "auth", "fixable_by_skill": False, "suggestion": "Check provider API key / authentication settings in ~/.hermes/config.yaml"}

    # Rate limiting — config/network issue
    if any(kw in error_lower for kw in ["rate limit", "429", "throttled", "too many requests"]):
        return {"category": "rate_limit", "fixable_by_skill": False, "suggestion": "Rate limited. Add delays between calls or check provider quota."}

    # Tool not available in context — execution environment restriction
    if any(kw in error_lower for kw in ["not available in this execution context", "not available in context"]):
        return {"category": "context_unavailable", "fixable_by_skill": False, "suggestion": "This tool is restricted in the current execution context (e.g., cron). Avoid calling it in autonomous jobs."}

    # Security scan blocked — policy, not skill
    if "security scan" in error_lower:
        return {"category": "security_policy", "fixable_by_skill": False, "suggestion": "Security scan blocked this operation. Review the tool call for dangerous patterns."}

    # Missing required parameter — skill CAN teach correct usage.
    # Require the phrase to appear near a parameter-like word to avoid
    # matching generic "authentication is required" messages.
    if any(kw in error_lower for kw in ["missing required", "field required"]):
        return {"category": "missing_parameter", "fixable_by_skill": True, "suggestion": f"When using this tool, ensure all required parameters are provided: {top_error[:80] if top_error else 'unknown'}"}
    if "is required" in error_lower:
        # Narrow: require a parameter-like prefix (quote, space-sep word, or bracket)
        # e.g. "'old_text' is required" or "old_text is required"
        import re
        if re.search(r"[\w_\-]+\s+is required", error_lower) or "'" in error_lower or '"' in error_lower:
            return {"category": "missing_parameter", "fixable_by_skill": True, "suggestion": f"When using this tool, ensure all required parameters are provided: {top_error[:80] if top_error else 'unknown'}"}

    return {"category": "unknown", "fixable_by_skill": True, "suggestion": "Review error and add specific handling."}


def _load_skill_descriptions(existing_skills: dict[str, Path]) -> dict[str, str]:
    """
    Pre-load the description line from each SKILL.md for fuzzy matching.
    Uses manual parsing so that there is no dependency on PyYAML.
    """
    descriptions = {}
    for name, path in existing_skills.items():
        desc = ""
        try:
            text = (path / "SKILL.md").read_text(errors="ignore")[:1500]
            lines = text.splitlines()
            in_fm = False
            collecting_block = False
            for line in lines:
                if line.strip() == "---":
                    if not in_fm:
                        in_fm = True
                        continue
                    else:
                        break
                if not in_fm:
                    continue
                if line.strip().startswith("description:"):
                    parts = line.split(":", 1)
                    val = parts[1].strip() if len(parts) > 1 else ""
                    if val.startswith(">") or val.startswith("|"):  # YAML block scalar starts here
                        collecting_block = True
                        desc = ""
                    else:
                        desc = val.lower()
                        break
                elif collecting_block and in_fm:
                    # collect block-scalar content until next key or end of frontmatter
                    stripped = line.strip()
                    if stripped == "":
                        continue
                    if ":" in stripped and not stripped.startswith("- "):
                        # likely another key in frontmatter
                        break
                    desc += " " + stripped
        except Exception:
            pass
        descriptions[name] = desc.strip().lower()
    return descriptions


def search_skills_for_capability(capability: str, existing_skills: dict[str, Path], descriptions: dict[str, str] = None) -> str | None:
    """
    Check whether any installed skill already covers a capability.
    Searches skill names and their SKILL.md descriptions for keyword matches.
    Optional `descriptions` cache avoids re-reading every SKILL.md per call.
    """
    cap_lower = capability.lower().replace("-", " ").replace("_", " ")
    cap_words = set(w for w in cap_lower.split() if len(w) > 2)

    # Direct name / substring match
    match = map_tool_to_skill(capability, existing_skills)
    if match:
        return match

    # Description search with keyword overlap
    if descriptions is None:
        descriptions = _load_skill_descriptions(existing_skills)
    for name, desc in descriptions.items():
        name_lower = name.lower().replace("-", " ").replace("_", " ")
        desc_words = set(w for w in name_lower.split() + desc.split() if len(w) > 2)
        # Overlap: if at least 2 keywords from the capability are present
        common = cap_words.intersection(desc_words)
        if len(common) >= 2:
            return name

    return None


def generate_recommendations(monitor_data: dict) -> list[dict[str, Any]]:
    """Generate prioritized improvement recommendations."""
    recommendations = []
    existing_skills = find_existing_skills()

    # Pre-compute root causes for all weakest_tools to avoid re-classifying
    _tool_root_causes = {}
    for tool in monitor_data.get("weakest_tools", []):
        _tool_root_causes[tool["tool"]] = _classify_error_root_cause(tool.get("top_error", ""))

    # 1. Patch recommendations for failing tools
    for tool in monitor_data.get("weakest_tools", []):
        if tool["errors"] < 2:
            continue  # Skip one-off errors

        # Classify root cause first (cached)
        root_cause = _tool_root_causes[tool["tool"]]
        if not root_cause["fixable_by_skill"]:
            # Log as infra/auth issue but don't recommend skill creation/patch
            continue

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
                "root_cause": root_cause,
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
                "root_cause": root_cause,
            })

    # 2. Create recommendations for skill gaps
    skill_descriptions = _load_skill_descriptions(existing_skills)
    for gap in monitor_data.get("skill_gaps", []):
        cap = gap["capability"]
        # Deep check: skill names AND descriptions via keyword overlap.
        # This avoids recommending a skill when one already exists, e.g.
        #   "docker-management" already covers "docker", "csv-parsing" already covers "csv".
        existing_match = search_skills_for_capability(cap, existing_skills, skill_descriptions)
        if existing_match:
            continue  # Already covered by an installed skill
        recommendations.append({
            "action": "create",
            "priority": gap["requests"] * 10,
            "target": cap,
            "reason": f"Users requested '{cap}' {gap['requests']} times but no skill exists",
            "suggested_fix": f"Create a skill for {cap} based on successful session patterns",
        })

    # 3. Evolve recommendations for skills with moderate failure rates (only skill-fixable ones)
    for tool in monitor_data.get("weakest_tools", []):
        if tool["success_rate"] < 90 and tool["total"] >= 5:
            root_cause = _tool_root_causes[tool["tool"]]
            if not root_cause["fixable_by_skill"]:
                continue
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

    # Add infrastructure/auth issues as separate flagged warnings
    flagged_issues = []
    for tool in monitor_data.get("weakest_tools", []):
        if tool["errors"] < 1:
            continue
        root_cause = _tool_root_causes[tool["tool"]]
        if not root_cause["fixable_by_skill"]:
            flagged_issues.append({
                "tool": tool["tool"],
                "errors": tool["errors"],
                "top_error": tool["top_error"],
                "category": root_cause["category"],
                "suggestion": root_cause["suggestion"],
            })
    monitor_data["flagged_infrastructure_issues"] = flagged_issues

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
    if "is required" in error or "missing required" in error or "field required" in error or "must be provided" in error:
        param = error.split("'")[1] if "'" in error else "the missing parameter"
        return f"When using this tool, ensure '{param}' is included in the tool call"
    if "invalid" in error and ("argument" in error or "parameter" in error or "input" in error):
        return "Add input validation — check parameter types and ranges before calling"

    return "Review failure patterns and add error handling for the most common case"


def print_recommendations(recs: list[dict], monitor_data: dict = None):
    """Print recommendations in human-readable format."""
    if not recs:
        print("No improvement recommendations at this time.")

    flagged = (monitor_data or {}).get("flagged_infrastructure_issues", [])

    print("=" * 60)
    print("  HERMES DOJO — IMPROVEMENT RECOMMENDATIONS")
    print("=" * 60)

    if flagged:
        print("\n  ⚠️  INFRASTRUCTURE / AUTH ISSUES (not fixable by skills):")
        print("  " + "-" * 56)
        for issue in flagged:
            emoji = {"infra": "🔌", "auth": "🔑", "rate_limit": "⏱️", "context_unavailable": "🚫", "security_policy": "🛡️"}.get(
                issue["category"], "⚠️"
            )
            print(f"\n  {emoji} {issue['tool']} ({issue['errors']} errors)")
            print(f"     Error: {issue['top_error'][:100]}")
            print(f"     → {issue['suggestion']}")

    if recs:
        print("\n  🔧 SKILL-FIXABLE ISSUES:")
        print("  " + "-" * 56)
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
    else:
        print("\n  ✅ No skill-fixable issues found.")

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
        print_recommendations(recs, monitor_data)

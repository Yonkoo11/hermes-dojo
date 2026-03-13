#!/usr/bin/env python3
"""
Hermes Dojo — Auto-Fixer

Takes weakness analysis from analyzer.py and applies fixes:
1. Patches existing skills via skill_manage tool instructions
2. Creates new skills for detected gaps
3. Runs self-evolution (GEPA) on weak skills
4. Tracks before/after scores

This script generates the fix instructions that Hermes Agent executes.
It does NOT modify skills directly — it outputs structured commands for
the agent's skill_manage tool or shell commands for self-evolution.

Usage:
    python3 fixer.py                     # Generate fix plan
    python3 fixer.py --apply             # Generate + apply fixes
    python3 fixer.py --evolve            # Also run self-evolution
    python3 fixer.py --json              # Output as JSON
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
SKILLS_DIR = HERMES_HOME / "skills"
EVOLUTION_DIR = HERMES_HOME / "hermes-agent-self-evolution"
EVOLUTION_VENV = EVOLUTION_DIR / ".venv" / "bin" / "python3"

# Reference fix strategies from failure_patterns.md
FIX_STRATEGIES = {
    "path_not_found": {
        "patch": "Add path validation: check if file/directory exists before operations. "
                 "Use `os.path.exists()` or `which` for commands.",
        "skill_addition": "## Pre-flight Checks\n- Before ANY file operation, verify the path exists\n"
                         "- If path not found, search common alternatives (~/, ~/Documents/, ./)\n"
                         "- Ask user to confirm path if ambiguous",
    },
    "timeout": {
        "patch": "Add retry logic with exponential backoff. Start with 5s timeout, "
                 "retry up to 3 times with 2x backoff. Fall back to alternative method.",
        "skill_addition": "## Timeout Handling\n- Set initial timeout to 10 seconds\n"
                         "- Retry up to 3 times with exponential backoff (5s, 10s, 20s)\n"
                         "- After 3 failures, try alternative approach (e.g., web_search instead of web_extract)",
    },
    "permission_denied": {
        "patch": "Check permissions before operations. Suggest chmod/sudo with explanation.",
        "skill_addition": "## Permission Checks\n- Check file permissions before read/write\n"
                         "- If denied, explain the permission issue clearly\n"
                         "- Suggest fix: `chmod` for files, `sudo` only with user confirmation",
    },
    "command_not_found": {
        "patch": "Verify command exists with `which` before execution. Suggest install if missing.",
        "skill_addition": "## Command Verification\n- Run `which <command>` before execution\n"
                         "- If not found, suggest installation method\n"
                         "- Try common alternatives (e.g., `python3` vs `python`)",
    },
    "rate_limit": {
        "patch": "Add rate limit awareness. Parse retry-after header. Use exponential backoff.",
        "skill_addition": "## Rate Limiting\n- Check for 429 status codes and retry-after headers\n"
                         "- Wait the specified time before retrying\n"
                         "- Fall back to alternative data source if rate limited",
    },
    "wrong_context": {
        "patch": "Ask for clarification before acting on ambiguous instructions. "
                 "Check current context (branch, directory, environment) first.",
        "skill_addition": "## Context Awareness\n- Before git operations, check current branch with `git branch --show-current`\n"
                         "- Before file operations, confirm the working directory\n"
                         "- Before deployments, confirm the target environment",
    },
    "missing_dependency": {
        "patch": "Check for required dependencies before importing. Install if missing.",
        "skill_addition": "## Dependency Management\n- Try importing required modules first\n"
                         "- If ImportError, install via pip/npm/etc.\n"
                         "- Verify installation succeeded before retrying",
    },
    "generic": {
        "patch": "Add error handling for the most common failure case. "
                 "Log the error clearly and suggest user action.",
        "skill_addition": "## Error Handling\n- Wrap operations in try/except blocks\n"
                         "- Log clear error messages with context\n"
                         "- Suggest actionable next steps to the user",
    },
}


def classify_error(error_text: str) -> str:
    """Classify an error into a fix strategy category."""
    error_lower = error_text.lower()

    if any(p in error_lower for p in ["not found", "no such file", "enoent"]):
        return "path_not_found"
    if any(p in error_lower for p in ["timeout", "etimedout", "timed out"]):
        return "timeout"
    if any(p in error_lower for p in ["permission", "access denied", "eacces", "403"]):
        return "permission_denied"
    if "command not found" in error_lower:
        return "command_not_found"
    if any(p in error_lower for p in ["rate limit", "429", "throttl"]):
        return "rate_limit"
    if any(p in error_lower for p in ["wrong branch", "wrong file", "no, i meant"]):
        return "wrong_context"
    if any(p in error_lower for p in ["no module", "modulenotfound", "import error"]):
        return "missing_dependency"
    return "generic"


def generate_skill_patch(rec: dict) -> dict:
    """Generate a skill patch instruction for a recommendation."""
    error_type = classify_error(rec.get("top_error", ""))
    strategy = FIX_STRATEGIES.get(error_type, FIX_STRATEGIES["generic"])

    return {
        "action": "patch",
        "target": rec["target"],
        "skill_path": rec.get("skill_path"),
        "error_type": error_type,
        "patch_description": strategy["patch"],
        "skill_addition": strategy["skill_addition"],
        "tool_instruction": {
            "tool": "skill_manage",
            "action": "patch",
            "name": rec["target"],
            "patch": strategy["skill_addition"],
            "reason": rec["reason"],
        },
    }


def generate_skill_creation(rec: dict) -> dict:
    """Generate a new skill creation instruction."""
    error_type = classify_error(rec.get("top_error", ""))
    strategy = FIX_STRATEGIES.get(error_type, FIX_STRATEGIES["generic"])

    skill_name = rec["target"]
    skill_content = f"""---
name: {skill_name}
version: 0.1.0
triggers:
  - "{skill_name.replace('-', ' ')}"
priority: 5
---

# {skill_name.replace('-', ' ').title()}

Auto-generated by Hermes Dojo based on {rec['reason']}.

{strategy['skill_addition']}

## Usage
This skill was created because users frequently requested this capability
but no skill existed to handle it properly.
"""

    return {
        "action": "create",
        "target": skill_name,
        "skill_content": skill_content,
        "tool_instruction": {
            "tool": "skill_manage",
            "action": "create",
            "name": skill_name,
            "content": skill_content,
            "reason": rec["reason"],
        },
    }


def run_evolution(skill_name: str, iterations: int = 5, dry_run: bool = False) -> dict:
    """Run self-evolution on a skill via the hermes-agent-self-evolution CLI."""
    result = {
        "skill": skill_name,
        "iterations": iterations,
        "status": "pending",
        "before_score": None,
        "after_score": None,
    }

    if dry_run:
        result["status"] = "dry_run"
        result["command"] = (
            f"cd {EVOLUTION_DIR} && {EVOLUTION_VENV} -m evolution.skills.evolve_skill "
            f"--skill {skill_name} --iterations {iterations}"
        )
        return result

    if not EVOLUTION_VENV.exists():
        result["status"] = "error"
        result["error"] = "Self-evolution venv not found. Run: cd ~/.hermes/hermes-agent-self-evolution && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        return result

    try:
        cmd = [
            str(EVOLUTION_VENV),
            "-m", "evolution.skills.evolve_skill",
            "--skill", skill_name,
            "--iterations", str(iterations),
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(EVOLUTION_DIR),
        )

        if proc.returncode == 0:
            result["status"] = "completed"
            result["output"] = proc.stdout[-500:] if len(proc.stdout) > 500 else proc.stdout
            # Try to parse scores from output
            for line in proc.stdout.split("\n"):
                if "before" in line.lower() and "score" in line.lower():
                    try:
                        result["before_score"] = float(line.split(":")[-1].strip().rstrip("%"))
                    except (ValueError, IndexError):
                        pass
                if "after" in line.lower() and "score" in line.lower():
                    try:
                        result["after_score"] = float(line.split(":")[-1].strip().rstrip("%"))
                    except (ValueError, IndexError):
                        pass
        else:
            result["status"] = "error"
            result["error"] = proc.stderr[-300:] if len(proc.stderr) > 300 else proc.stderr

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["error"] = "Evolution timed out after 300 seconds"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def generate_fix_plan(recommendations: list[dict], evolve: bool = False, dry_run: bool = True) -> dict:
    """Generate a complete fix plan from analyzer recommendations."""
    plan = {
        "patches": [],
        "creations": [],
        "evolutions": [],
        "summary": {},
    }

    for rec in recommendations:
        if rec["action"] == "patch":
            patch = generate_skill_patch(rec)
            plan["patches"].append(patch)

        elif rec["action"] == "create":
            creation = generate_skill_creation(rec)
            plan["creations"].append(creation)

        elif rec["action"] == "evolve" and evolve:
            evo_result = run_evolution(rec["target"], iterations=5, dry_run=dry_run)
            plan["evolutions"].append(evo_result)

    plan["summary"] = {
        "patches": len(plan["patches"]),
        "creations": len(plan["creations"]),
        "evolutions": len(plan["evolutions"]),
        "total_actions": len(plan["patches"]) + len(plan["creations"]) + len(plan["evolutions"]),
    }

    return plan


def apply_fixes(plan: dict) -> list[dict]:
    """Apply fixes from the plan. Returns list of applied improvements."""
    improvements = []

    for patch in plan["patches"]:
        skill_path = patch.get("skill_path")
        if skill_path and Path(skill_path).exists():
            skill_md = Path(skill_path) / "SKILL.md"
            if skill_md.exists():
                # Append the fix addition to the skill file
                with open(skill_md, "a") as f:
                    f.write("\n\n" + patch["skill_addition"])

                improvements.append({
                    "action": "patch",
                    "target": patch["target"],
                    "description": patch["patch_description"],
                    "error_type": patch["error_type"],
                })

    for creation in plan["creations"]:
        skill_dir = SKILLS_DIR / creation["target"]
        if not skill_dir.exists():
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_md = skill_dir / "SKILL.md"
            with open(skill_md, "w") as f:
                f.write(creation["skill_content"])

            improvements.append({
                "action": "create",
                "target": creation["target"],
                "description": f"Created new skill for {creation['target']}",
            })

    for evo in plan.get("evolutions", []):
        if evo["status"] == "completed":
            improvements.append({
                "action": "evolve",
                "target": evo["skill"],
                "description": f"Self-evolved with {evo['iterations']} iterations",
                "before_score": evo.get("before_score"),
                "after_score": evo.get("after_score"),
            })

    return improvements


def print_fix_plan(plan: dict):
    """Print the fix plan in human-readable format."""
    print("=" * 60)
    print("  HERMES DOJO — FIX PLAN")
    print("=" * 60)

    if plan["patches"]:
        print("\n  PATCHES (existing skills):")
        print("  " + "-" * 56)
        for p in plan["patches"]:
            print(f"\n  Target: {p['target']}")
            print(f"  Error type: {p['error_type']}")
            print(f"  Fix: {p['patch_description']}")

    if plan["creations"]:
        print("\n  NEW SKILLS:")
        print("  " + "-" * 56)
        for c in plan["creations"]:
            print(f"\n  Target: {c['target']}")
            print(f"  Reason: {c['tool_instruction']['reason']}")

    if plan["evolutions"]:
        print("\n  SELF-EVOLUTION:")
        print("  " + "-" * 56)
        for e in plan["evolutions"]:
            status = e["status"]
            print(f"\n  Skill: {e['skill']} — {status}")
            if e.get("command"):
                print(f"  Command: {e['command']}")
            if e.get("before_score") is not None:
                print(f"  Score: {e['before_score']} → {e.get('after_score', '?')}")

    print(f"\n  SUMMARY: {plan['summary']['total_actions']} actions "
          f"({plan['summary']['patches']} patches, "
          f"{plan['summary']['creations']} creations, "
          f"{plan['summary']['evolutions']} evolutions)")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Dojo Auto-Fixer")
    parser.add_argument("--apply", action="store_true", help="Apply fixes (not just plan)")
    parser.add_argument("--evolve", action="store_true", help="Also run self-evolution")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--input", type=str, help="Read recommendations from JSON file")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            recs = json.load(f)
    else:
        sys.path.insert(0, str(Path(__file__).parent))
        from monitor import analyze_sessions
        from analyzer import generate_recommendations
        monitor_data = analyze_sessions()
        recs = generate_recommendations(monitor_data)

    plan = generate_fix_plan(recs, evolve=args.evolve, dry_run=not args.apply)

    if args.apply:
        improvements = apply_fixes(plan)
        plan["applied"] = improvements

    if args.json:
        print(json.dumps(plan, indent=2, default=str))
    else:
        print_fix_plan(plan)

        if args.apply and plan.get("applied"):
            print(f"\n  Applied {len(plan['applied'])} improvements.")

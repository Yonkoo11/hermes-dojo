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
    """Generate a new skill creation with specific, actionable instructions.

    Unlike boilerplate templates, this builds skills with real bash commands,
    step-by-step workflows, and error handling patterns derived from the actual
    failure data in sessions.
    """
    error_type = classify_error(rec.get("top_error", ""))
    skill_name = rec["target"]
    top_error = rec.get("top_error", "unknown error")
    reason = rec.get("reason", "")

    # Build skill content based on what kind of capability this is
    skill_content = _build_skill_content(skill_name, error_type, top_error, reason)

    return {
        "action": "create",
        "target": skill_name,
        "skill_content": skill_content,
        "tool_instruction": {
            "tool": "skill_manage",
            "action": "create",
            "name": skill_name,
            "content": skill_content,
            "reason": reason,
        },
    }


# Skill templates with actual substance — bash commands, step-by-step workflows,
# error handling. These mirror the quality of built-in Hermes skills.
SKILL_TEMPLATES = {
    "web-extract": """---
name: web-extract
description: Reliable web content extraction with timeout handling, retries, and fallback strategies.
version: 0.1.0
metadata:
  hermes:
    tags: [web, scraping, extraction, http]
    generated_by: hermes-dojo
---

# Web Content Extraction

## Before ANY web_extract call

1. Validate the URL format:
```bash
# Check URL is reachable before expensive extraction
curl -sI --max-time 5 "$URL" | head -1
```

2. Set reasonable expectations — large pages and JavaScript-heavy sites often timeout.

## Timeout Strategy

When web_extract times out:
1. **Do NOT immediately retry the same call.** The server is likely slow or blocking.
2. Try with a simpler approach first:
```bash
# Lightweight fetch — just get the HTML, no rendering
curl -sL --max-time 15 "$URL" | head -200
```
3. If curl also fails, fall back to web_search for the same content.
4. If the user specifically needs the page content (not just info about it), explain the timeout and ask if they want to try again.

## Rate Limit Handling

If you get 429 or "rate limit" errors:
- Parse the `Retry-After` header if present
- Wait at least 30 seconds before retrying
- After 2 rate limit hits, switch to web_search as alternative
- Never retry more than 3 times total

## Common Failures

| Error | Do This |
|-------|---------|
| Timeout after 30s | Use curl with --max-time 15, then fall back to web_search |
| 403 Forbidden | Site blocks bots. Use web_search instead. Don't retry. |
| SSL certificate error | Flag to user. Never skip SSL verification. |
| Connection refused | Service is down. Tell user, don't retry. |
""",

    "terminal-run": """---
name: terminal-run
description: Safe terminal command execution with pre-flight checks, context awareness, and error recovery.
version: 0.1.0
metadata:
  hermes:
    tags: [terminal, shell, commands, safety]
    generated_by: hermes-dojo
---

# Terminal Command Execution

## Pre-flight Checks (BEFORE running commands)

### For file operations
```bash
# Always verify path exists before cat/head/tail/rm
test -e "$TARGET" && echo "exists" || echo "not found"

# For directories
test -d "$DIR" && echo "is directory" || echo "not a directory"
```

### For git operations
```bash
# ALWAYS check current branch before commit/push/merge
git branch --show-current

# Check for uncommitted changes
git status --short
```

### For package/tool commands
```bash
# Verify the command exists before running it
command -v docker &>/dev/null && echo "found" || echo "not installed"
```

## Context Awareness

**The #1 source of user corrections is wrong context.** Before acting:
- If user says "commit to feature branch" — CHECK you're on that branch first
- If user says "deploy to production" — CONFIRM the target, don't assume
- If user gives a file path — verify it exists, try common alternatives if not:
  - `~/file` → `~/Documents/file` → `./file` → ask user

## Error Recovery

| Error | Recovery |
|-------|----------|
| "command not found" | Run `command -v <cmd>` to check. Suggest install via brew/apt/pip. |
| "permission denied" | Explain which permission is needed. Suggest `chmod` with specific mode. Never auto-sudo. |
| "no such file or directory" | List parent directory contents. Suggest closest match. |
| "not a git repository" | Check if user is in wrong directory. Run `git rev-parse --show-toplevel`. |

## Dangerous Commands

NEVER run these without explicit user confirmation:
- `rm -rf` anything
- `git push --force`
- `git reset --hard`
- `docker system prune`
- Any command with `sudo`
""",

    "execute-code": """---
name: execute-code
description: Code execution with dependency management, error parsing, and iterative fixing.
version: 0.1.0
metadata:
  hermes:
    tags: [code, execution, python, debugging]
    generated_by: hermes-dojo
---

# Code Execution

## Before Executing Code

1. **Check dependencies first** — don't run code that will ImportError:
```python
# Test import before the real script
try:
    import pandas
except ImportError:
    # Install it first
    import subprocess
    subprocess.run(["pip", "install", "pandas"])
```

2. **Validate input data exists** before processing it.

## Common Failures

### ModuleNotFoundError
- Install the module: `pip install <module>`
- If pip fails (externally managed), use: `pip install --user <module>`
- Verify installation: `python3 -c "import <module>; print(<module>.__version__)"`

### JSONDecodeError
- The input is not valid JSON. Don't just report "invalid JSON"
- Show the user WHERE it's invalid: character position from the error
- Try to fix common issues: trailing commas, single quotes, unquoted keys

### FileNotFoundError in code
- Use `os.path.expanduser()` for `~` paths
- Use `pathlib.Path` for cross-platform paths
- Check existence before opening

## Iterative Fixing

When code fails:
1. Read the FULL error traceback, not just the last line
2. Fix the specific error, don't rewrite everything
3. Re-run to verify the fix worked
4. Maximum 3 fix attempts before asking user for help
""",

    "deployment": """---
name: deployment
description: Deploy applications safely with environment verification, rollback awareness, and multi-target support.
version: 0.1.0
metadata:
  hermes:
    tags: [deploy, devops, ssh, docker, production]
    generated_by: hermes-dojo
---

# Deployment

## Critical: Confirm Target First

**ALWAYS ask which deployment method before starting:**
- SSH/rsync to server?
- Docker push to registry?
- Platform deploy (Vercel, Railway, Fly.io)?
- Local build only?

Never assume Docker when user says "deploy" — this is the #1 correction pattern.

## SSH/Rsync Deploy
```bash
# Verify SSH connectivity first
ssh -o ConnectTimeout=5 user@server "echo ok"

# Deploy with rsync (exclude common cruft)
rsync -avz --exclude node_modules --exclude .git --exclude .env . user@server:/app/
```

## Docker Deploy
```bash
# Verify Docker is running and authenticated
docker info &>/dev/null && echo "Docker running" || echo "Docker not running"

# Build and tag properly (not just :latest)
docker build -t registry/app:$(git rev-parse --short HEAD) .
docker push registry/app:$(git rev-parse --short HEAD)
```

## Platform Deploy
```bash
# Vercel
npx vercel --prod

# Railway
railway up

# Fly.io
fly deploy
```

## Safety Checks
- Never deploy uncommitted changes
- Always verify the target environment
- Keep the previous version available for rollback
""",
}


def _build_skill_content(skill_name: str, error_type: str, top_error: str, reason: str) -> str:
    """Build skill content — use specific template if available, otherwise generate
    a targeted skill based on the error type and failure data."""

    # Check for a specific template first
    if skill_name in SKILL_TEMPLATES:
        return SKILL_TEMPLATES[skill_name]

    # For skill gaps (user requested capability, no errors to analyze),
    # build a minimal but real skill
    strategy = FIX_STRATEGIES.get(error_type, FIX_STRATEGIES["generic"])

    # Generate a skill that's actually useful, not boilerplate
    human_name = skill_name.replace('-', ' ').title()
    content = f"""---
name: {skill_name}
description: Handle {skill_name.replace('-', ' ')} tasks based on observed user request patterns.
version: 0.1.0
metadata:
  hermes:
    tags: [{', '.join(skill_name.split('-'))}]
    generated_by: hermes-dojo
    generated_reason: "{reason}"
---

# {human_name}

## Context

This skill was created by Hermes Dojo after analyzing session logs.
{reason}

## Workflow

1. **Understand the request** — ask clarifying questions if the task is ambiguous
2. **Verify prerequisites** — check that required tools/files/permissions exist
3. **Execute with error handling** — catch failures, don't retry blindly
4. **Verify the result** — confirm the operation succeeded before reporting done

{strategy['skill_addition']}

## When Things Go Wrong

Most common error pattern observed: `{top_error[:100] if top_error else 'unknown'}`

- Parse the error message for actionable information
- Try ONE alternative approach before asking user for help
- Never retry the exact same failing command more than twice
"""
    return content


def _load_openrouter_key() -> str:
    """Load OPENROUTER_API_KEY from Hermes .env file or environment."""
    # Check environment first
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key

    # Fall back to Hermes .env
    env_file = HERMES_HOME / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# Default model for self-evolution — Nous Hermes via OpenRouter
DEFAULT_EVOLUTION_MODEL = "openrouter/nousresearch/hermes-3-llama-3.1-70b"


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
            f"cd {EVOLUTION_DIR} && OPENROUTER_API_KEY=<key> {EVOLUTION_VENV} -m evolution.skills.evolve_skill "
            f"--skill {skill_name} --hermes-repo {HERMES_HOME} --iterations {iterations} "
            f"--optimizer-model {DEFAULT_EVOLUTION_MODEL} --eval-model {DEFAULT_EVOLUTION_MODEL}"
        )
        return result

    if not EVOLUTION_VENV.exists():
        result["status"] = "error"
        result["error"] = "Self-evolution venv not found. Run: cd ~/.hermes/hermes-agent-self-evolution && python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
        return result

    api_key = _load_openrouter_key()
    if not api_key:
        result["status"] = "error"
        result["error"] = "OPENROUTER_API_KEY not set. Add it to ~/.hermes/.env or set as environment variable."
        return result

    try:
        cmd = [
            str(EVOLUTION_VENV),
            "-m", "evolution.skills.evolve_skill",
            "--skill", skill_name,
            "--hermes-repo", str(HERMES_HOME),
            "--iterations", str(iterations),
            "--optimizer-model", DEFAULT_EVOLUTION_MODEL,
            "--eval-model", DEFAULT_EVOLUTION_MODEL,
        ]

        env = os.environ.copy()
        env["OPENROUTER_API_KEY"] = api_key

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(EVOLUTION_DIR),
            env=env,
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

    for p in plan["patches"]:
        skill_path = p.get("skill_path")
        if skill_path and Path(skill_path).exists():
            skill_md = Path(skill_path) / "SKILL.md"
            if skill_md.exists():
                # Append the fix addition to the skill file
                with open(skill_md, "a") as f:
                    f.write("\n\n" + p["skill_addition"])

                improvements.append({
                    "action": "patch",
                    "target": p["target"],
                    "description": p["patch_description"],
                    "error_type": p["error_type"],
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

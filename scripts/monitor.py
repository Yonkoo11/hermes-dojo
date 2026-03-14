#!/usr/bin/env python3
"""
Hermes Dojo — Performance Monitor

Reads ~/.hermes/state.db to analyze agent performance across recent sessions.
Identifies tool failures, user corrections, retry patterns, and skill gaps.

Usage:
    python3 monitor.py                    # Analyze last 7 days
    python3 monitor.py --days 30          # Analyze last 30 days
    python3 monitor.py --json             # Output as JSON
    python3 monitor.py --session-id X     # Analyze specific session
"""

import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
DB_PATH = HERMES_HOME / "state.db"

# Patterns that indicate a tool call failure in tool response content
ERROR_PATTERNS = [
    r"(?i)error[:\s]",
    r"(?i)traceback",
    r"(?i)exception[:\s]",
    r"(?i)failed to",
    r"(?i)command not found",
    r"(?i)permission denied",
    r"(?i)no such file",
    r"(?i)timeout",
    r"(?i)connection refused",
    r"(?i)404 not found",
    r"(?i)500 internal",
    r"(?i)rate limit",
    r"(?i)unauthorized",
    r"(?i)access denied",
    r"(?i)ENOENT",
    r"(?i)EACCES",
    r"(?i)ETIMEDOUT",
    r"(?i)could not",
    r"(?i)unable to",
    r"(?i)syntax error",
]

# Patterns in user messages that indicate corrections/dissatisfaction
CORRECTION_PATTERNS = [
    r"(?i)^no[,.\s]",
    r"(?i)wrong",
    r"(?i)not what I",
    r"(?i)I meant",
    r"(?i)that's not",
    r"(?i)please don't",
    r"(?i)stop",
    r"(?i)undo",
    r"(?i)revert",
    r"(?i)you misunderstood",
    r"(?i)incorrect",
    r"(?i)fix (this|that|it)",
    r"(?i)try again",
    r"(?i)that broke",
    r"(?i)doesn't work",
    r"(?i)not working",
    r"(?i)why did you",
]

# Patterns indicating user is repeatedly asking for something (skill gap signal)
REQUEST_PATTERNS = [
    (r"(?i)parse.*csv", "csv-parsing"),
    (r"(?i)format.*json", "json-formatting"),
    (r"(?i)convert.*pdf", "pdf-conversion"),
    (r"(?i)send.*email", "email-sending"),
    (r"(?i)create.*chart", "chart-creation"),
    (r"(?i)scrape.*web", "web-scraping"),
    (r"(?i)deploy", "deployment"),
    (r"(?i)docker", "docker-management"),
    (r"(?i)git.*commit", "git-operations"),
    (r"(?i)test.*unit|unit.*test", "unit-testing"),
    (r"(?i)database|sql|query", "database-operations"),
    (r"(?i)api.*call|fetch.*api|rest.*api", "api-integration"),
]


def classify_tool_result(content: str) -> tuple[bool, str]:
    """Classify a tool result as success or failure, return (is_error, error_type)."""
    if not content:
        return False, ""

    for pattern in ERROR_PATTERNS:
        match = re.search(pattern, content)
        if match:
            # Extract a short error description
            start = max(0, match.start() - 10)
            end = min(len(content), match.end() + 50)
            snippet = content[start:end].strip().replace("\n", " ")
            return True, snippet

    return False, ""


def detect_retry_patterns(messages: list[dict]) -> list[dict]:
    """Detect when the same tool is called multiple times in quick succession (retry loop)."""
    retries = []
    prev_tool = None
    prev_time = 0
    prev_session = None
    consecutive_count = 0

    for msg in messages:
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            try:
                calls = json.loads(msg["tool_calls"]) if isinstance(msg["tool_calls"], str) else msg["tool_calls"]
                for call in (calls if isinstance(calls, list) else [calls]):
                    tool_name = call.get("name") or call.get("function", {}).get("name", "")
                    ts = msg["timestamp"]
                    if tool_name == prev_tool and (ts - prev_time) < 30:
                        consecutive_count += 1
                    else:
                        if consecutive_count >= 2:
                            retries.append({
                                "tool": prev_tool,
                                "count": consecutive_count + 1,
                                "session_id": prev_session,
                            })
                        consecutive_count = 0
                    prev_tool = tool_name
                    prev_time = ts
                    prev_session = msg["session_id"]
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue

    if consecutive_count >= 2:
        retries.append({"tool": prev_tool, "count": consecutive_count + 1, "session_id": prev_session})

    return retries


def analyze_sessions(days: int = 7, session_id: str = None) -> dict[str, Any]:
    """Analyze recent sessions for performance metrics."""
    if not DB_PATH.exists():
        return {"error": f"Database not found at {DB_PATH}"}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cutoff = time.time() - (days * 86400)

    # Get sessions
    if session_id:
        sessions = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchall()
    else:
        sessions = conn.execute(
            "SELECT * FROM sessions WHERE started_at > ? ORDER BY started_at DESC",
            (cutoff,),
        ).fetchall()

    if not sessions:
        conn.close()
        return {
            "sessions_analyzed": 0,
            "message": "No sessions found in the specified time range.",
        }

    session_ids = [s["id"] for s in sessions]
    placeholders = ",".join("?" for _ in session_ids)

    # Get all messages for these sessions
    messages = conn.execute(
        f"SELECT * FROM messages WHERE session_id IN ({placeholders}) ORDER BY timestamp",
        session_ids,
    ).fetchall()
    messages = [dict(m) for m in messages]

    conn.close()

    # === Analyze tool calls ===
    tool_stats = defaultdict(lambda: {"total": 0, "errors": 0, "error_types": Counter()})
    all_errors = []

    for msg in messages:
        if msg["role"] == "tool" and msg.get("tool_name"):
            tool_name = msg["tool_name"]
            tool_stats[tool_name]["total"] += 1

            is_error, error_type = classify_tool_result(msg.get("content", ""))
            if is_error:
                tool_stats[tool_name]["errors"] += 1
                tool_stats[tool_name]["error_types"][error_type] += 1
                all_errors.append({
                    "tool": tool_name,
                    "error": error_type,
                    "session_id": msg["session_id"],
                    "timestamp": msg["timestamp"],
                })

    # === Analyze user corrections ===
    corrections = []
    for msg in messages:
        if msg["role"] == "user" and msg.get("content"):
            content = msg["content"]
            for pattern in CORRECTION_PATTERNS:
                if re.search(pattern, content):
                    corrections.append({
                        "content": content[:100],
                        "pattern": pattern,
                        "session_id": msg["session_id"],
                        "timestamp": msg["timestamp"],
                    })
                    break

    # === Detect skill gaps ===
    skill_gaps = Counter()
    for msg in messages:
        if msg["role"] == "user" and msg.get("content"):
            for pattern, gap_name in REQUEST_PATTERNS:
                if re.search(pattern, msg["content"]):
                    skill_gaps[gap_name] += 1

    # === Detect retry patterns ===
    retries = detect_retry_patterns(messages)

    # === Compute summary ===
    total_tool_calls = sum(s["total"] for s in tool_stats.values())
    total_errors = sum(s["errors"] for s in tool_stats.values())
    overall_success = (
        round((1 - total_errors / total_tool_calls) * 100, 1)
        if total_tool_calls > 0
        else 100.0
    )

    # Rank tools by failure rate
    weakest_tools = []
    for tool_name, stats in sorted(
        tool_stats.items(),
        key=lambda x: x[1]["errors"] / max(x[1]["total"], 1),
        reverse=True,
    ):
        if stats["errors"] > 0:
            success_rate = round((1 - stats["errors"] / stats["total"]) * 100, 1)
            top_error = stats["error_types"].most_common(1)
            weakest_tools.append({
                "tool": tool_name,
                "total": stats["total"],
                "errors": stats["errors"],
                "success_rate": success_rate,
                "top_error": top_error[0][0] if top_error else "",
            })

    # Skill gaps that appeared 2+ times
    recurring_gaps = [
        {"capability": name, "requests": count}
        for name, count in skill_gaps.most_common(10)
        if count >= 2
    ]

    result = {
        "timestamp": time.time(),
        "days_analyzed": days,
        "sessions_analyzed": len(sessions),
        "total_tool_calls": total_tool_calls,
        "total_errors": total_errors,
        "overall_success_rate": overall_success,
        "weakest_tools": weakest_tools[:10],
        "user_corrections": len(corrections),
        "correction_samples": corrections[:5],
        "retry_patterns": retries,
        "skill_gaps": recurring_gaps,
        "total_messages": len(messages),
        "sessions": [
            {
                "id": s["id"],
                "source": s["source"],
                "model": s["model"],
                "tool_calls": s["tool_call_count"],
                "messages": s["message_count"],
                "started_at": s["started_at"],
            }
            for s in sessions[:20]
        ],
    }

    return result


def print_dashboard(data: dict):
    """Print a human-readable dashboard."""
    if "error" in data:
        print(f"Error: {data['error']}")
        return

    if data["sessions_analyzed"] == 0:
        print(data.get("message", "No sessions found."))
        return

    print("=" * 60)
    print("  HERMES DOJO — PERFORMANCE ANALYSIS")
    print("=" * 60)
    print(f"  Sessions analyzed:  {data['sessions_analyzed']} (last {data['days_analyzed']} days)")
    print(f"  Total tool calls:   {data['total_tool_calls']}")
    print(f"  Total messages:     {data['total_messages']}")
    print(f"  Overall success:    {data['overall_success_rate']}%")
    print()

    if data["weakest_tools"]:
        print("  TOP WEAKNESSES:")
        print("  " + "-" * 56)
        for i, tool in enumerate(data["weakest_tools"][:5], 1):
            print(f"  {i}. {tool['tool']}: {tool['success_rate']}% success "
                  f"({tool['errors']}/{tool['total']} failures)")
            if tool["top_error"]:
                print(f"     → {tool['top_error'][:60]}")
        print()

    if data["user_corrections"] > 0:
        print(f"  USER CORRECTIONS: {data['user_corrections']}")
        for c in data["correction_samples"][:3]:
            print(f"     • \"{c['content'][:50]}...\"")
        print()

    if data["skill_gaps"]:
        print("  SKILL GAPS DETECTED:")
        for gap in data["skill_gaps"]:
            print(f"     • {gap['capability']}: requested {gap['requests']}x, no skill exists")
        print()

    if data["retry_patterns"]:
        print(f"  RETRY LOOPS: {len(data['retry_patterns'])}")
        for r in data["retry_patterns"][:3]:
            print(f"     • {r['tool']}: called {r['count']}x in rapid succession")
        print()

    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Dojo Performance Monitor")
    parser.add_argument("--days", type=int, default=7, help="Days to analyze (default: 7)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--session-id", type=str, help="Analyze specific session")
    args = parser.parse_args()

    data = analyze_sessions(days=args.days, session_id=args.session_id)

    if args.json:
        # Make Counter objects serializable
        print(json.dumps(data, indent=2, default=str))
    else:
        print_dashboard(data)

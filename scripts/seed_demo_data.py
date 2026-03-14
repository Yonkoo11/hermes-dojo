#!/usr/bin/env python3
"""
Hermes Dojo — Demo Data Seeder

Creates realistic session data in state.db for demo purposes.
Simulates several days of agent usage with deliberate failure patterns
that Dojo can then detect and fix.

Usage:
    python3 seed_demo_data.py             # Seed 5 days of data
    python3 seed_demo_data.py --days 10   # Seed 10 days
    python3 seed_demo_data.py --clear     # Clear seeded data first
"""

import json
import os
import random
import sqlite3
import time
import uuid
from pathlib import Path

HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
DB_PATH = HERMES_HOME / "state.db"

# Realistic session scenarios with deliberate failures
SCENARIOS = [
    {
        "description": "User asks to parse CSV data",
        "messages": [
            {"role": "user", "content": "Can you parse this CSV file at ~/data/sales.csv and give me a summary?"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "cat ~/data/sales.csv"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "Error: No such file or directory: /Users/user/data/sales.csv"},
            {"role": "assistant", "content": "The file doesn't exist. Let me check the directory..."},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "ls ~/data/"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "Error: No such file or directory: /Users/user/data/"},
            {"role": "user", "content": "No, I meant ~/Documents/data/sales.csv"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "cat ~/Documents/data/sales.csv"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "name,amount,date\nWidget A,150,2026-01-15\nWidget B,230,2026-01-16\nWidget C,89,2026-01-17"},
            {"role": "assistant", "content": "Here's the summary of your sales data:\n- 3 entries\n- Total: $469\n- Date range: Jan 15-17, 2026"},
        ],
    },
    {
        "description": "User asks to format JSON",
        "messages": [
            {"role": "user", "content": "Format this JSON: {\"name\":\"test\",\"items\":[1,2,3],\"nested\":{\"a\":true}}"},
            {"role": "assistant", "content": "```json\n{\n  \"name\": \"test\",\n  \"items\": [1, 2, 3],\n  \"nested\": {\n    \"a\": true\n  }\n}\n```"},
            {"role": "user", "content": "Thanks! Now can you also validate this JSON? {bad json here}"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "execute_code", "arguments": {"code": "import json; json.loads('{bad json here}')"}}]},
            {"role": "tool", "tool_name": "execute_code", "content": "Error: json.decoder.JSONDecodeError: Expecting value: line 1 column 2 (char 1)"},
            {"role": "assistant", "content": "That JSON is invalid. The error is at position 1."},
        ],
    },
    {
        "description": "Web scraping with timeout",
        "messages": [
            {"role": "user", "content": "Scrape the latest headlines from news.ycombinator.com"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "web_extract", "arguments": {"url": "https://news.ycombinator.com"}}]},
            {"role": "tool", "tool_name": "web_extract", "content": "Error: Request timeout after 30 seconds"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "web_extract", "arguments": {"url": "https://news.ycombinator.com"}}]},
            {"role": "tool", "tool_name": "web_extract", "content": "Error: Request timeout after 30 seconds"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "web_search", "arguments": {"query": "hacker news top stories today"}}]},
            {"role": "tool", "tool_name": "web_search", "content": "1. Show HN: I built a...\n2. Ask HN: What are you...\n3. Why Rust is...\n4. The future of...\n5. How we scaled..."},
            {"role": "assistant", "content": "Here are today's top Hacker News stories:\n1. Show HN: I built a...\n2. Ask HN: What are you...\n3. Why Rust is...\n4. The future of...\n5. How we scaled..."},
        ],
    },
    {
        "description": "Git operations with wrong branch",
        "messages": [
            {"role": "user", "content": "Commit my changes to the feature branch"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "git add -A && git commit -m 'Update feature'"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "On branch main\n[main abc1234] Update feature\n 3 files changed, 45 insertions(+)"},
            {"role": "user", "content": "Wrong branch! That committed to main, not the feature branch. Undo that."},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "git reset --soft HEAD~1"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": ""},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "git checkout feature && git add -A && git commit -m 'Update feature'"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "Switched to branch 'feature'\n[feature def5678] Update feature\n 3 files changed, 45 insertions(+)"},
            {"role": "assistant", "content": "Done. Moved the commit to the feature branch."},
        ],
    },
    {
        "description": "Successful code generation",
        "messages": [
            {"role": "user", "content": "Write a Python function to calculate fibonacci numbers"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "file_write", "arguments": {"path": "fib.py", "content": "def fib(n):\n    if n <= 1:\n        return n\n    return fib(n-1) + fib(n-2)"}}]},
            {"role": "tool", "tool_name": "file_write", "content": "File written: fib.py"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "python3 -c 'from fib import fib; print([fib(i) for i in range(10)])'"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "[0, 1, 1, 2, 3, 5, 8, 13, 21, 34]"},
            {"role": "assistant", "content": "Created fib.py with a recursive fibonacci function. Test output: [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]"},
        ],
    },
    {
        "description": "Database query failure",
        "messages": [
            {"role": "user", "content": "Query my SQLite database at ~/project/data.db for all users"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "sqlite3 ~/project/data.db 'SELECT * FROM users'"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "Error: no such table: users"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "sqlite3 ~/project/data.db '.tables'"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "accounts  orders  products"},
            {"role": "assistant", "content": "The database doesn't have a 'users' table. Available tables: accounts, orders, products. Did you mean 'accounts'?"},
            {"role": "user", "content": "Yes, I meant accounts"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "sqlite3 ~/project/data.db 'SELECT * FROM accounts'"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "1|alice|alice@example.com\n2|bob|bob@example.com\n3|carol|carol@example.com"},
            {"role": "assistant", "content": "Here are all accounts:\n| ID | Name | Email |\n|---|---|---|\n| 1 | alice | alice@example.com |\n| 2 | bob | bob@example.com |\n| 3 | carol | carol@example.com |"},
        ],
    },
    {
        "description": "API call with rate limiting",
        "messages": [
            {"role": "user", "content": "Fetch data from the GitHub API for repo NousResearch/hermes-agent"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "web_extract", "arguments": {"url": "https://api.github.com/repos/NousResearch/hermes-agent"}}]},
            {"role": "tool", "tool_name": "web_extract", "content": "Error: 403 Forbidden - API rate limit exceeded. Try again in 42 seconds."},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "web_extract", "arguments": {"url": "https://api.github.com/repos/NousResearch/hermes-agent"}}]},
            {"role": "tool", "tool_name": "web_extract", "content": "Error: 403 Forbidden - API rate limit exceeded. Try again in 38 seconds."},
            {"role": "assistant", "content": "I'm hitting GitHub's API rate limit. Let me try the web search instead."},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "web_search", "arguments": {"query": "NousResearch hermes-agent github repository"}}]},
            {"role": "tool", "tool_name": "web_search", "content": "hermes-agent: The agent that grows with you. Stars: 2.5k, Language: Python, Last updated: 2 days ago"},
            {"role": "assistant", "content": "Hermes Agent by Nous Research: 2.5k stars, Python, actively maintained."},
        ],
    },
    {
        "description": "Successful memory update",
        "messages": [
            {"role": "user", "content": "Remember that I prefer dark mode and use vim keybindings"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "memory", "arguments": {"action": "add", "content": "User prefers dark mode and vim keybindings"}}]},
            {"role": "tool", "tool_name": "memory", "content": "Memory updated successfully."},
            {"role": "assistant", "content": "Got it! I'll remember your preference for dark mode and vim keybindings."},
        ],
    },
    {
        "description": "CSV parsing request (skill gap)",
        "messages": [
            {"role": "user", "content": "Parse this CSV and give me statistics: column means, medians, and correlations"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "execute_code", "arguments": {"code": "import pandas as pd\ndf = pd.read_csv('data.csv')\nprint(df.describe())"}}]},
            {"role": "tool", "tool_name": "execute_code", "content": "Error: ModuleNotFoundError: No module named 'pandas'"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "pip install pandas"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "Successfully installed pandas-2.2.0"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "execute_code", "arguments": {"code": "import pandas as pd\ndf = pd.read_csv('data.csv')\nprint(df.describe())"}}]},
            {"role": "tool", "tool_name": "execute_code", "content": "       value1    value2\ncount  100.0     100.0\nmean   50.5      75.3\nstd    28.8      12.1\nmin    1.0       45.0\nmax    100.0     99.0"},
            {"role": "assistant", "content": "Statistics for your CSV:\n- value1: mean=50.5, std=28.8, range=[1, 100]\n- value2: mean=75.3, std=12.1, range=[45, 99]"},
        ],
    },
    {
        "description": "Deploy with wrong config",
        "messages": [
            {"role": "user", "content": "Deploy my app to production"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "docker build -t myapp . && docker push myapp:latest"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "Error: denied: requested access to the resource is denied"},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "docker login"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "Error: unauthorized: authentication required"},
            {"role": "user", "content": "I meant deploy to my server via SSH, not Docker Hub"},
            {"role": "assistant", "content": "Sorry about that! Let me deploy via SSH instead."},
            {"role": "assistant", "content": None, "tool_calls": [{"name": "terminal_run", "arguments": {"command": "rsync -avz --exclude node_modules . user@server:/app/"}}]},
            {"role": "tool", "tool_name": "terminal_run", "content": "sending incremental file list\n./\npackage.json\nsrc/\nsrc/index.js\nsent 12,345 bytes  received 234 bytes  total size is 45,678"},
            {"role": "assistant", "content": "Deployed via SSH. Files synced to server:/app/"},
        ],
    },
]


def seed_data(days: int = 5, clear: bool = False, deterministic: bool = True):
    """Seed the database with realistic demo data.

    Args:
        days: Number of days of data to seed
        clear: Clear previously seeded data first
        deterministic: Use fixed seed for reproducible demo output
    """
    if deterministic:
        random.seed(42)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Ensure required tables exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            source TEXT,
            model TEXT,
            started_at REAL,
            ended_at REAL,
            end_reason TEXT,
            message_count INTEGER DEFAULT 0,
            tool_call_count INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL
        )
    """)
    conn.commit()

    if clear:
        # Only clear seeded sessions (they have 'dojo-seed' in their source)
        conn.execute("DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE source = 'dojo-seed')")
        conn.execute("DELETE FROM sessions WHERE source = 'dojo-seed'")
        conn.commit()
        print("Cleared previously seeded data.")

    now = time.time()
    sessions_created = 0
    messages_created = 0

    for day in range(days):
        # 3-5 sessions per day
        num_sessions = random.randint(3, 5)
        day_start = now - (days - day) * 86400

        for s in range(num_sessions):
            session_id = str(uuid.uuid4())
            session_start = day_start + random.randint(0, 43200)  # Within first 12 hours

            # Pick a random scenario
            scenario = random.choice(SCENARIOS)

            # Create session
            conn.execute(
                """INSERT INTO sessions (id, source, model, started_at, ended_at, end_reason, message_count, tool_call_count)
                   VALUES (?, 'dojo-seed', 'hermes-3-llama-3.1-70b', ?, ?, 'completed', ?, ?)""",
                (
                    session_id,
                    session_start,
                    session_start + random.randint(60, 600),
                    len(scenario["messages"]),
                    sum(1 for m in scenario["messages"] if m.get("tool_calls")),
                ),
            )
            sessions_created += 1

            # Create messages
            msg_time = session_start
            for msg in scenario["messages"]:
                msg_time += random.uniform(1, 10)
                tool_calls_json = json.dumps(msg["tool_calls"]) if msg.get("tool_calls") else None

                conn.execute(
                    """INSERT INTO messages (session_id, role, content, tool_calls, tool_name, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        msg["role"],
                        msg.get("content"),
                        tool_calls_json,
                        msg.get("tool_name"),
                        msg_time,
                    ),
                )
                messages_created += 1

    conn.commit()

    # Rebuild FTS index for seeded data
    try:
        conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
        conn.commit()
    except Exception:
        pass

    conn.close()

    print(f"Seeded {sessions_created} sessions with {messages_created} messages over {days} days.")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Dojo Demo Data Seeder")
    parser.add_argument("--days", type=int, default=5, help="Days of data to seed")
    parser.add_argument("--clear", action="store_true", help="Clear previous seeds first")
    parser.add_argument("--random", action="store_true", help="Use random seed (non-deterministic)")
    args = parser.parse_args()

    seed_data(days=args.days, clear=args.clear, deterministic=not args.random)

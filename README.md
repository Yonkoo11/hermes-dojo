# Hermes Dojo

**Your agent, getting better while you sleep.**

Hermes Dojo is a self-improvement system for [Hermes Agent](https://github.com/NousResearch/hermes-agent) that watches how your agent performs, finds its weakest skills, fixes them with self-evolution, and shows you the results.

## The Problem

Your AI agent makes the same mistakes every day. You correct it, it forgets next session. Skills exist but nobody knows which ones work well and which ones silently fail. Self-evolution exists but nobody uses it because there's no signal about WHAT to evolve.

## The Solution

Dojo closes the feedback loop:

```
measure → identify weakness → evolve → measure again → report
```

It turns "the agent that grows with you" from a tagline into reality.

## How It Works

### 1. Performance Monitor
Reads your agent's session logs from `state.db`. Identifies failures: tool errors, retry loops, user corrections ("no, I meant..."), explicit complaints. Tracks per-skill success rates.

### 2. Weakness Analyzer
Categorizes root causes and ranks improvement opportunities:
- "web_extract fails 100% of the time. Root cause: no retry logic for timeouts"
- "No skill exists for CSV parsing, but user asked for it 5 times"

### 3. Auto-Fixer
For each weakness:
- Skill exists but fails → patch it with targeted error handling
- No skill exists → create one based on session patterns
- Run self-evolution (GEPA) on weak skills for measurable improvement

### 4. Reports
Generates reports for CLI or Telegram delivery with deltas, sparklines, and actionable summaries.

### 5. Learning Curve
Stores daily metrics. Shows improvement over days/weeks. Proof that the agent is actually growing.

## Quick Start

```bash
# Install as a Hermes skill
cp -r . ~/.hermes/skills/hermes-dojo/

# Seed demo data (optional, for testing)
python3 scripts/seed_demo_data.py --days 7

# Run the full pipeline
python3 scripts/demo.py --reset
```

## Commands (via Hermes Agent)

| Command | What it does |
|---------|-------------|
| `/dojo analyze` | Analyze recent sessions for failures |
| `/dojo improve` | Fix weakest skills + run self-evolution |
| `/dojo report` | Generate improvement report |
| `/dojo history` | Show learning curve over time |
| `/dojo auto` | Set up overnight cron (analyze + improve + report) |

## Architecture

```
hermes-dojo/
├── SKILL.md              # Main orchestrator (Hermes skill format)
├── scripts/
│   ├── monitor.py        # Reads session SQLite, computes metrics
│   ├── analyzer.py       # Categorizes failures, ranks weaknesses
│   ├── fixer.py          # Patches skills, creates new ones, runs evolution
│   ├── reporter.py       # Generates CLI/Telegram reports
│   ├── tracker.py        # Stores/retrieves learning curve data
│   ├── seed_demo_data.py # Demo data generator
│   └── demo.py           # Full pipeline demo runner
├── references/
│   └── failure_patterns.md
└── data/
    └── metrics.json      # Historical performance data
```

## Hermes Features Used

| Feature | How Dojo Uses It |
|---------|-----------------|
| Skills system | Dojo IS a skill; it creates/patches other skills |
| Self-evolution (GEPA) | Evolves weak skills via DSPy optimization |
| Session search | Reads past sessions to identify failure patterns |
| Cron scheduler | Runs overnight improvement cycle |
| Multi-platform | Morning report on Telegram |
| skill_manage | Creates and patches skills programmatically |

## Requirements

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) v0.2.0+
- Python 3.10+
- [hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) (for GEPA)

## Built for

Nous Research Hermes Agent Hackathon (March 2026)

---

Built on [Hermes Agent](https://github.com/NousResearch/hermes-agent) by [Nous Research](https://nousresearch.com)

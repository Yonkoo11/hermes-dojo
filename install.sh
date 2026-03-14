#!/bin/bash
# Hermes Dojo — Quick Install
# Copies the skill into your Hermes skills directory

set -e

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SKILL_DIR="$HERMES_HOME/skills/hermes-dojo"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$HERMES_HOME/hermes-agent" ]; then
    echo "Error: Hermes Agent not found at $HERMES_HOME/hermes-agent"
    echo "Install it first: https://github.com/NousResearch/hermes-agent"
    exit 1
fi

echo "Installing Hermes Dojo..."
mkdir -p "$SKILL_DIR/scripts" "$SKILL_DIR/references" "$SKILL_DIR/data"

cp "$SCRIPT_DIR/SKILL.md" "$SKILL_DIR/"
cp "$SCRIPT_DIR/scripts/"*.py "$SKILL_DIR/scripts/"
[ -d "$SCRIPT_DIR/references" ] && cp "$SCRIPT_DIR/references/"*.md "$SKILL_DIR/references/" 2>/dev/null || true

echo "Installed to $SKILL_DIR"
echo ""
echo "Quick test:"
echo "  cd $SKILL_DIR/scripts"
echo "  python3 seed_demo_data.py --days 7    # Seed demo data"
echo "  python3 demo.py --reset               # Run full pipeline"
echo ""
echo "Or use in Hermes: /dojo analyze"

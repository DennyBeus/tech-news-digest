#!/bin/bash
# =============================================================================
# run-digest-agent.sh — daily digest agent for multi-parser
#
# Runs after run-parser.sh (pipeline). Exports articles from DB, then
# launches Claude agent which translates, generates PDF and sends to Telegram.
#
# Install in crontab (06:30 UTC):
#   30 6 * * * /path/to/multi-parser/cron/run-digest-agent.sh >> /path/to/multi-parser/logs/digest/cron.log 2>&1
#
# Log structure:
#   logs/digest/run-YYYYMMDD-HHMMSS.log  — per-run log (kept 30 days)
#   logs/digest/cron.log                 — crontab stdout/stderr redirect
#
# Required env vars (set in .env):
#   DATABASE_URL       — Postgres connection string
#   TELEGRAM_CHAT_ID   — Telegram chat/user ID to send digest to
#
# Claude Code CLI must be installed and authorized on the server (claude auth login)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$SCRIPT_DIR/logs/digest"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
EXPORT_FILE="/tmp/digest-raw.md"
PROMPT_FILE="$SCRIPT_DIR/agent-instructions/digest-prompt.md"

# Source environment variables
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

mkdir -p "$LOG_DIR"

RUN_LOG="$LOG_DIR/run-${TIMESTAMP}.log"

# All output goes to both per-run log and stdout (captured by crontab → cron.log)
exec > >(tee -a "$RUN_LOG") 2>&1

echo "=== Digest agent run $TIMESTAMP ==="

# Validate required env vars
if [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    echo "[fail] TELEGRAM_CHAT_ID is not set in .env — aborting"
    exit 1
fi
if [ -z "${DATABASE_URL:-}" ]; then
    echo "[fail] DATABASE_URL is not set in .env — aborting"
    exit 1
fi

# Export articles from DB → /tmp/digest-raw.md
echo "[..] Exporting articles from DB..."
cd "$SCRIPT_DIR"
python3 scripts/delivery/export-latest.py \
    --hours 25 \
    --min-score 5 \
    --top-n 100 \
    --output "$EXPORT_FILE"
echo "[ok] Export complete: $EXPORT_FILE"

# Launch Claude agent with Telegram plugin
echo "[..] Starting Claude digest agent..."
export MULTI_PARSER_DIR="$SCRIPT_DIR"
export DIGEST_DATE=$(date -u +%Y%m%d)

claude \
    --dangerously-skip-permissions \
    --channels plugin:telegram@claude-plugins-official \
    -p "$(cat "$PROMPT_FILE")"

# Cleanup old per-run logs
find "$LOG_DIR" -name "run-*.log" -mtime +30 -delete 2>/dev/null || true

echo "=== Digest agent finished ==="

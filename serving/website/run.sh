#!/bin/bash
# Apertus Data Search — start the web server
# Usage: ES_HOST=<host> [ES_PORT=9200] [PORT=8888] ./run.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8888}"
VENV="$SCRIPT_DIR/.venv"

export ES_HOST="${ES_HOST:-localhost}"
export ES_PORT="${ES_PORT:-9200}"
export ES_INDEX="${ES_INDEX:-apertus-data}"

# ── Print access info ────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          Apertus Data Search                             ║"
echo "╠══════════════════════════════════════════════════════════╣"
printf "║  ES  → http://%s:%s\n" "$ES_HOST" "$ES_PORT"
printf "║  Idx → %s\n" "$ES_INDEX"
echo "╠══════════════════════════════════════════════════════════╣"
HOSTNAME=$(hostname -f 2>/dev/null || hostname)
printf "║  Internal cluster URL  → http://%s:%s\n" "$HOSTNAME" "$PORT"
echo "║"
echo "║  From your laptop, run:"
printf "║    ssh -L %s:localhost:%s %s\n" "$PORT" "$PORT" "$(whoami)@$HOSTNAME"
printf "║  then open → http://localhost:%s\n" "$PORT"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Create venv if needed ────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  echo "Creating virtual environment with Python 3.11…"
  /usr/bin/python3.11 -m venv "$VENV"
fi

source "$VENV/bin/activate"

# ── Install / upgrade dependencies quietly ───────────────────────
echo "Checking dependencies…"
pip install -q --upgrade pip
pip install -q -r "$SCRIPT_DIR/../environment/requirements.txt"
echo "Dependencies OK."
echo ""

# ── Launch ───────────────────────────────────────────────────────
cd "$SCRIPT_DIR"
exec uvicorn server:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info

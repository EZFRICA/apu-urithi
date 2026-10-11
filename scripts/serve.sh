#!/usr/bin/env bash
#
# Restart this project's server, and only this project's.
#
#     scripts/serve.sh            # port from URITHI_PORT, 8790 by default
#
# The process to stop is found by the port it holds, never by its name: another project on
# this machine may run a server with a similar command line, and stopping by name stops it
# too. A port is this project's alone.

set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${URITHI_PORT:-8790}"
LOG="${TMPDIR:-/tmp}/ai-apprentice-${PORT}.log"

for pid in $(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null); do
    echo "Stopping the process on port $PORT (pid $pid)"
    kill "$pid"
done
for _ in $(seq 1 20); do
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1 || break
    sleep 0.5
done

nohup uv run python -m server --port "$PORT" > "$LOG" 2>&1 &
for _ in $(seq 1 60); do
    if curl -s -o /dev/null "http://localhost:$PORT/"; then
        echo "The showcase:      http://localhost:$PORT/"
        echo "Teach:             http://localhost:$PORT/teach/"
        echo "Learn:             http://localhost:$PORT/learn/"
        echo "The presentation:  http://localhost:$PORT/presentation/"
        echo "Log: $LOG"
        exit 0
    fi
    sleep 1
done
echo "The server did not answer on port $PORT. See $LOG" >&2
exit 1

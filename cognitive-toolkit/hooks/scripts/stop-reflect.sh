#!/usr/bin/env bash
# Stop hook that nudges the agent to reflect after significant work.
# The agent decides whether reflection is warranted — this just asks the question.
#
# IMPORTANT: To avoid infinite block loops, this hook:
# 1. Uses a flag file to track that reflection was already requested
# 2. On second fire (after the agent reflected or decided to skip), approves the stop
# 3. Flag file is per-session to avoid stale state

set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Flag file to prevent infinite loops: one reflection prompt per stop sequence
FLAG_DIR="/tmp/claude-reflect-hooks"
FLAG_FILE="${FLAG_DIR}/reflected-${SESSION_ID}"

mkdir -p "$FLAG_DIR"

# If we already prompted for reflection this stop sequence, let the agent stop
if [ -f "$FLAG_FILE" ]; then
  rm -f "$FLAG_FILE"
  echo '{"decision": "approve"}'
  exit 0
fi

# Mark that we're prompting, so next Stop passes through
touch "$FLAG_FILE"

cat <<'EOF'
{
  "decision": "block",
  "reason": "Before wrapping up, consider whether a brief reflection is warranted. Ask yourself:\n\n1. Did you just complete a significant task (implementation, debugging session, research, architecture decision)?\n2. Did anything go unexpectedly wrong or surprisingly well?\n3. Are there lessons that would be useful in future sessions?\n\nIf YES to any: run a quick /reflect — keep it to 3-5 bullet points max, only persist what matters.\nIf NO (trivial task, simple question, no lessons): just say 'No reflection needed' and finish.\n\nDo NOT block yourself in a reflection loop. One reflection pass, then stop."
}
EOF

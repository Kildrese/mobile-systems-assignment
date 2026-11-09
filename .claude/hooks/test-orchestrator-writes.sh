#!/usr/bin/env bash
# Self-check for orchestrator-writes.sh: ./.claude/hooks/test-orchestrator-writes.sh
set -u
hook="$(cd "$(dirname "$0")" && pwd)/orchestrator-writes.sh"
wt=/repo/.claude/worktrees/x
fails=0

expect() { # expect <exit code> <payload> <label>
  printf '%s' "$2" | "$hook" 2>/dev/null
  local got=$?
  [ "$got" = "$1" ] || { echo "FAIL ($got, want $1): $3"; fails=1; }
}
edit() { jq -nc --arg p "$1" --arg a "${2-}" '{tool_name:"Edit",tool_input:{file_path:$p}} + (if $a == "" then {} else {agent_id:$a} end)'; }

expect 0 "$(edit "$wt/openspec/changes/x/decisions.md")" "decision log"
expect 0 "$(edit openspec/changes/fix-y/decisions.md)" "relative decision log"
expect 2 "$(edit "$wt/backend/app/main.py")" "code"
expect 2 "$(edit "$wt/openspec/changes/x/tasks.md")" "another artifact"
expect 2 "$(edit "$wt/decisions.md")" "decisions.md outside a change"
expect 0 "$(edit "$wt/backend/app/main.py" a1)" "a subagent passes"
expect 2 '{"tool_name":"Edit","tool_input":{"file_path":"/repo/x.py"},"agent_id":""}' "empty agent_id is the main thread"
expect 2 'not json' "a bad payload blocks"
expect 2 '{"agent_id": "a1"} not json' "unreadable JSON never counts as a subagent"

[ $fails = 0 ] && echo "orchestrator-writes: all checks pass"
exit $fails

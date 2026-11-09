#!/usr/bin/env bash
# PreToolUse (orchestrator agent, Edit|Write): the orchestrator writes no code.
# A subagent's call passes (only subagent payloads carry agent_id). In the main thread only
# a change's decisions.md passes; anything else, unreadable JSON included, blocks.
# ponytail: Bash redirects and sed -i get past this; the orchestrator prompt forbids them and the reviewer reads the diff.
input=$(cat)
agent=$(jq -r '.agent_id // ""' <<<"$input") && [ -n "$agent" ] && exit 0
path=$(jq -er '.tool_input.file_path // ""' <<<"$input") || { echo "orchestrator-writes.sh: unreadable hook payload" >&2; exit 2; }
case "$path" in
  */openspec/changes/*/decisions.md | openspec/changes/*/decisions.md) exit 0 ;;
esac
echo "The orchestrator only writes openspec/changes/<name>/decisions.md. Delegate the edit to $path to a subagent." >&2
exit 2

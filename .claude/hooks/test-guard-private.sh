#!/usr/bin/env bash
# Self-check for guard-private.sh: ./.claude/hooks/test-guard-private.sh
set -u
hook="$(cd "$(dirname "$0")" && pwd)/guard-private.sh"
repo=$(mktemp -d) && trap 'rm -rf "$repo"' EXIT
git -C "$repo" init -q
mkdir -p "$repo/private" && touch "$repo/private/cv.docx" "$repo/.env" "$repo/.env.example" "$repo/ok.py"
fails=0

expect() { # expect <exit code> <command>
  jq -n --arg c "$2" --arg d "$repo" '{tool_input:{command:$c},cwd:$d}' | "$hook" 2>/dev/null
  local got=$?
  [ "$got" = "$1" ] || { echo "FAIL ($got, want $1): $2"; fails=1; }
}

expect 0 "ls -la"
expect 0 "git add ok.py .env.example"
expect 2 "git add private/cv.docx"
expect 2 "git add -f .env"
expect 2 "git add . && git commit -m x"
expect 2 "git commit -am x"
expect 0 "git commit -m 'adds private key handling'"
git -C "$repo" add -f private/cv.docx
expect 2 "git commit -m x"

[ $fails = 0 ] && echo "guard-private: all checks pass"
exit $fails

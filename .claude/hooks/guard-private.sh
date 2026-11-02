#!/usr/bin/env bash
# PreToolUse(Bash): the repo is public, so block any git add/commit that would
# publish private/ or a .env file (.env.example is fine). Exit 2 = blocked.
input=$(cat)
cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
cwd=$(jq -r '.cwd // "."' <<<"$input")

secret() { grep -E '(^|/)private(/|$)|(^|/)\.env[^/]*$' | grep -Ev '(^|/)\.env\.example$'; }
block() { echo "Blocked: $1 would publish private files (public repo): $(tr '\n' ' ' <<<"$2")" >&2; exit 2; }

grep -Eq '\bgit\b' <<<"$cmd" || exit 0

# ponytail: word match, so a commit message like "add private/ docs" is also
# blocked; reword the message, or parse git's argv if that gets annoying.
if grep -Eq '\badd\b' <<<"$cmd"; then
  hits=$(tr -s " \t;&|()\"'" '\n' <<<"$cmd" | secret)
  [ -n "$hits" ] && block "git add" "$hits"
fi

if grep -Eq '\bcommit\b' <<<"$cmd"; then
  hits=$(git -C "$cwd" diff --cached --name-only 2>/dev/null | secret)
  # `git add . && git commit` stages in the same command: check what add would pick up.
  if grep -Eq '\badd\b|\bcommit\b.* -[a-zA-Z]*a' <<<"$cmd"; then
    hits+=$(git -C "$cwd" status --porcelain --untracked-files=all 2>/dev/null | cut -c4- | secret)
  fi
  [ -n "$hits" ] && block "git commit" "$hits"
fi
exit 0

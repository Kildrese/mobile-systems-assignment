#!/usr/bin/env bash
# Stop: before Claude ends a turn with uncommitted changes, run the fast checks
# (ruff, tsc) for the parts that changed. Exit 2 sends the failures back to
# Claude. Tests stay with the `checker` agent and CI (the backend's need Postgres).
cwd=$(jq -r '.cwd // "."')
root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root" || exit 0
changed=$(git status --porcelain --untracked-files=all | cut -c4-)
[ -n "$changed" ] || exit 0

fail="" out=""
for proj in backend services/verifier; do
  grep -Eq "^$proj/.*\.py$" <<<"$changed" || continue
  r=$(cd "$proj" && uv run --quiet ruff check 2>&1 && uv run --quiet ruff format --check 2>&1) \
    || { fail+=" $proj(ruff)"; out+=$'\n'$(tail -30 <<<"$r"); }
done
if grep -Eq '^frontend/.*\.(ts|tsx)$' <<<"$changed" && [ -d frontend/node_modules ]; then
  r=$(cd frontend && npx tsc -b 2>&1) || { fail+=" frontend(tsc)"; out+=$'\n'$(tail -30 <<<"$r"); }
fi

[ -z "$fail" ] && exit 0
echo "Checks failed:$fail. Fix them before finishing." >&2
echo "$out" >&2
exit 2

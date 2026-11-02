#!/usr/bin/env bash
# PostToolUse(Edit|Write): ruff-format an edited Python file with the ruff of
# its own uv project (backend/ or services/verifier/). Never blocks.
file=$(jq -r '.tool_input.file_path // empty')
[[ $file == *.py && -f $file ]] || exit 0
dir=$(dirname "$file")
until [[ -f $dir/pyproject.toml || $dir == / ]]; do dir=$(dirname "$dir"); done
[[ -f $dir/pyproject.toml ]] && uv run --quiet --directory "$dir" ruff format --quiet "$file" >/dev/null 2>&1
exit 0

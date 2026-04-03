#!/bin/sh

set -eu

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

python_bin="${QUALITY_GATES_PYTHON:-python}"
quality_home="${QUALITY_GATES_HOME:-$repo_root/.git/.quality-gates-home}"
detect_secrets_excludes='(^dist/|^python/pollyweb_cli\.egg-info/|(^|/)(__pycache__|\.pytest_cache|\.venv|\.venv-[^/]+)(/|$)|\.pyc$)'

mkdir -p "$quality_home"

export HOME="$quality_home"
export USERPROFILE="$quality_home"

printf '%s\n' "quality-gates: running test suite..."
"$python_bin" -m pytest
printf '%s\n' "quality-gates: tests passed."

printf '%s\n' "quality-gates: auditing Python dependencies..."
"$python_bin" -m pip_audit --strict .
printf '%s\n' "quality-gates: dependency audit passed."

printf '%s\n' "quality-gates: running Bandit..."
"$python_bin" -m bandit -q -r python
printf '%s\n' "quality-gates: Bandit passed."

printf '%s\n' "quality-gates: scanning tracked files for secrets..."
git ls-files -z \
  | xargs -0 "$python_bin" -m detect_secrets.pre_commit_hook \
      --baseline .secrets.baseline \
      --exclude-files "$detect_secrets_excludes"
printf '%s\n' "quality-gates: detect-secrets passed."

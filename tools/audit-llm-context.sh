#!/bin/sh

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)

tmp_file=$(mktemp)
trap 'rm -f "$tmp_file"' EXIT HUP INT TERM

cat <<'EOF' > "$tmp_file"
AGENTS.md|260|always-read repo instructions
docs/usage.md|220|usage router
docs/llm-token-efficiency.md|220|process doc
tasks/lessons.md|5200|repo learnings
EOF

printf '%-44s %7s %7s %7s %7s  %s\n' "FILE" "WORDS" "LINES" "BUDGET" "DELTA" "STATUS"

while IFS='|' read -r relative_path word_budget note; do
  absolute_path="$ROOT_DIR/$relative_path"
  word_count=$(wc -w < "$absolute_path" | tr -d ' ')
  line_count=$(wc -l < "$absolute_path" | tr -d ' ')
  delta=$((word_count - word_budget))

  if [ "$word_count" -le "$word_budget" ]; then
    status="OK ($note)"
  elif [ "$delta" -le 80 ]; then
    status="TRIM SOON ($note)"
  else
    status="SPLIT/CONDENSE ($note)"
  fi

  printf '%-44s %7s %7s %7s %7s  %s\n' \
    "$relative_path" "$word_count" "$line_count" "$word_budget" "$delta" "$status"
done < "$tmp_file"

echo
echo "Run this after touching AGENTS, docs, or lessons so wallet-cli routing files stay cheap to reload."

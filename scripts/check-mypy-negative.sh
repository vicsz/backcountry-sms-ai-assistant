#!/usr/bin/env bash
set -euo pipefail

negative_log=$(mktemp)
trap 'rm -f "$negative_log"' EXIT

if [[ -x .venv/bin/mypy ]]; then
  mypy_command=(.venv/bin/mypy)
else
  mypy_command=(mypy)
fi

if "${mypy_command[@]}" --config-file /dev/null --no-error-summary --show-error-codes tests/typecheck/negative.py >"$negative_log" 2>&1; then
  echo "mypy unexpectedly accepted the negative fixture"
  exit 1
fi

grep -q "assignment" "$negative_log"
echo "mypy rejected the negative fixture as expected"

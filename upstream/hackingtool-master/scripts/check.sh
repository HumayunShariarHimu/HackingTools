#!/usr/bin/env bash
# Single source of truth for dev checks. Run locally (git pre-push hook, or
# `make check`) AND in CI — same command both places, so nothing surprises you
# after a push. Fails fast on the first red check.
set -euo pipefail
cd "$(dirname "$0")/.."

# Prefer uv (dev group has ruff+pytest); fall back to bare tools if uv absent.
run() {
  if command -v uv >/dev/null 2>&1; then
    uv run --group dev "$@"
  else
    "$@"
  fi
}

echo "==> ruff (must-fix: syntax / undefined names / bad f-strings)"
run ruff check . --select=E9,F63,F7,F82,PLE,YTT

echo "==> pytest (unit + catalog/taxonomy conformance)"
run pytest -q

echo "OK — all local checks passed."

.PHONY: check test setup

# Run the full local gate (lint + tests) — same command CI runs.
check:
	./scripts/check.sh

# Just the tests.
test:
	uv run --group dev pytest -q

# One-time per clone: wire the pre-push hook so `check` runs before every push.
setup:
	git config core.hooksPath .githooks
	@echo "pre-push hook enabled — 'make check' now runs automatically before push."

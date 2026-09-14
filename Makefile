# Thin wrapper around the cross-platform runner (scripts/task.py).
#
# `make` is not available by default on Windows, so the Python runner is the
# canonical entry point:  python scripts/task.py <target>
# This Makefile exists purely for convenience on macOS/Linux/WSL.

PYTHON ?= python3

TARGETS := setup up down logs reset seed-small seed-performance lint audit metrics \
           test-unit test-integration test-e2e test coverage profile-report \
           benchmark-report dev-backend dev-frontend

.PHONY: help $(TARGETS)

help:
	@$(PYTHON) scripts/task.py --list

$(TARGETS):
	@$(PYTHON) scripts/task.py $@

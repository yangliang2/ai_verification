#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
RUN="$ROOT/docs/runs/2026-08-03-issue-88-aggregate"

PYTHONPATH="$ROOT/src" uv run --no-project \
  --with pyyaml --with jsonschema --python 3.14 \
  python -m aiverify.bench.m6_case_package aggregate \
  --manifest "$ROOT/bench/m6/m6-qualification-v1.yaml" \
  --packages \
    "$ROOT/docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-01.json" \
    "$ROOT/docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-02.json" \
    "$ROOT/docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-03.json" \
    "$ROOT/docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-01.json" \
    "$ROOT/docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-02.json" \
    "$ROOT/docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-03.json" \
  --repo-root "$ROOT" \
  --json-output "$RUN/aggregate.json" \
  --markdown-output "$RUN/aggregate.md"

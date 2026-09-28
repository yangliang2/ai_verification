#!/usr/bin/env bash
# Issue #225 — exact release commands that produced this run's evidence.
#
# The documented host checkout path is /Users/peter/hosts/opencalc-calibration.
# On the machine that produced this evidence the same pinned checkout (commit
# 0584d61189e916a62a3b402223b35e1d7a3093db) lives at $HOME/hosts/opencalc-calibration.
set -euo pipefail

REPO=/Users/80268204/Projects/ai_verification
RUN="$REPO/docs/runs/2026-09-28-issue-225-runtime-mapping-reissue"
CANDIDATE=bench/runtime-calibration/opencalc-input-save-enabled-v1
SOURCE="$HOME/hosts/opencalc-calibration"

cd "$REPO"

/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  .venv/bin/python -m aiverify.bench.runtime_calibration verify-candidate \
  --candidate-root "$CANDIDATE" \
  --output-root "$RUN/verification/candidate-stage" \
  > "$RUN/verification/candidate-stage.stdout" 2>&1

/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  .venv/bin/python -m aiverify.bench.runtime_calibration admit-family \
  --candidate-root "$CANDIDATE" \
  --source-root "$SOURCE" \
  --predecessor-root "$RUN/verification/candidate-stage" \
  --output-root "$RUN/verification/family-stage-final" \
  --materialization-root /tmp/opencalc-issue-225-project-materializations \
  --change-materialization-root /tmp/opencalc-issue-225-change-materializations \
  > "$RUN/verification/family-stage-final.stdout" 2>&1

Implemented issue #203 in commit `c71309640739d39a499b0734424d07afd538e2dc`.

The deterministic backend now admits and drives the frozen opaque OpenCalc sequence: wait for oneButton, then tap oneButton, twoButton, addButton, threeButton, and fourButton. Every tap reads a fresh device-scoped layout, requires exactly one clickable resource-ID match and valid center, dispatches exactly one derived tap, and settles for 350 ms with no retry/fallback. Evidence and lineage distinguish observation probes from side-effect dispatches, and the driver remains outcome-blind.

Durable verification record: `docs/runs/2026-08-28-issue-203-opaque-opencalc-keypad/README.md`

Exact verification commands/results:

- `PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -q --junitxml=docs/runs/2026-08-28-issue-203-opaque-opencalc-keypad/verification/full-pytest.xml` — exit 0; 1,362 tests; 0 failures; 0 errors; 1 skip; pytest 187.604s; real 187.83s.
- `PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -q --junitxml=docs/runs/2026-08-28-issue-203-opaque-opencalc-keypad/verification/runner-pytest.xml tests/runner/test_deterministic_backend.py tests/runner/test_journey_backend_selection.py tests/runner/test_journey.py tests/runner/test_cli.py tests/bench/test_runtime_calibration.py` — exit 0; 141 tests; 0 failures; 0 errors; 0 skips; pytest 2.314s; real 2.41s.
- `uv run --with ruff ruff check src/aiverify/runner/deterministic_backend.py tests/runner/test_deterministic_backend.py --output-format concise` — exit 0, all checks passed.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src tests` — exit 0.
- `uv run --with mypy mypy src/aiverify/runner/deterministic_backend.py --ignore-missing-imports` — exit 0, no issues in 1 source file.

Implementation/evidence files: `src/aiverify/runner/deterministic_backend.py`, `src/aiverify/runner/journey.py`, `src/aiverify/runner/execution_identity.py`, `src/aiverify/runner/cli.py`, and `tests/runner/test_deterministic_backend.py`; JUnit reports and checksums are under `docs/runs/2026-08-28-issue-203-opaque-opencalc-keypad/verification/`.

Manual/device verification: not performed; this run used recording-device fakes only. No screenshots, layout dumps, device logs, or generated JSON were produced. The known gap is real Android/emulator dispatch verification.

# Issue #203 verification: opaque OpenCalc keypad Journey

- Date: 2026-08-28
- Repository: `yangliang2/ai_verification`
- Implementation commit: `c71309640739d39a499b0734424d07afd538e2dc`
- Scope: deterministic, recording-device validation of the six-action opaque keypad lane.

## Outcome

Issue #203 acceptance behavior is implemented and the existing deterministic fixtures remain green. The driver admits and executes the frozen sequence `wait oneButton`, then `tap oneButton`, `tap twoButton`, `tap addButton`, `tap threeButton`, and `tap fourButton`. Each tap reads a fresh layout, requires one clickable resource-ID match with a valid on-screen center, dispatches exactly one derived tap, and settles for 350 ms. Wait/probe and tap/dispatch lineage are recorded separately; no verdict is produced by the driver.

## Verification commands and results

Tool versions: Python 3.11.15; pytest 9.1.1; Ruff 0.16.5; mypy 2.3.1.

Full repository suite:

```text
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -q --junitxml=docs/runs/2026-08-28-issue-203-opaque-opencalc-keypad/verification/full-pytest.xml
```

Result: exit 0; 1,362 tests; 0 failures; 0 errors; 1 skip; pytest time 187.604 s; `/usr/bin/time` real time 187.83 s.

Focused runner/calibration suite:

```text
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -q --junitxml=docs/runs/2026-08-28-issue-203-opaque-opencalc-keypad/verification/runner-pytest.xml tests/runner/test_deterministic_backend.py tests/runner/test_journey_backend_selection.py tests/runner/test_journey.py tests/runner/test_cli.py tests/bench/test_runtime_calibration.py
```

Result: exit 0; 141 tests; 0 failures; 0 errors; 0 skips; pytest time 2.314 s; `/usr/bin/time` real time 2.41 s.

Additional checks:

```text
uv run --with ruff ruff check src/aiverify/runner/deterministic_backend.py tests/runner/test_deterministic_backend.py --output-format concise
```

Result: exit 0, `All checks passed!`.

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src tests
```

Result: exit 0.

```text
uv run --with mypy mypy src/aiverify/runner/deterministic_backend.py --ignore-missing-imports
```

Result: exit 0, `Success: no issues found in 1 source file`.

## Acceptance evidence

- `src/aiverify/runner/deterministic_backend.py`: frozen plan admission, canonical/raw Run Spec binding, typed device tap capability, fresh layout lookup, exact clickable-node/center validation, one-shot dispatch, fixed settle, fail-closed behavior, and raw observation/dispatch evidence.
- `src/aiverify/runner/journey.py`: backend-neutral normalized results with explicit observation-probe versus side-effect-dispatch lineage.
- `src/aiverify/runner/execution_identity.py`: exact multi-action identity receipts and dispatch-count/command validation without model calls.
- `src/aiverify/runner/cli.py`: passes the configured `adb_bin` into the deterministic device adapter.
- `tests/runner/test_deterministic_backend.py`: full keypad success path, fresh-read/order/center assertions, all material admission and node failures, no-retry dispatch failures, settle interruption, byte drift, and identity/lineage contracts.

## Review evidence

The Standards and Spec reviews used fixed point `bdff1c7964ad99770a8ae5672a23b49293b3ee60`. Their findings were addressed before this record was finalized:

- Standards: capability typing and durable evidence were the hard findings; the injected adapter now exposes the tap capability explicitly (with a layout-only compatibility wrapper), and this committed run record supplies durable evidence. Remaining items were judgement-level duplication/scalar-or-sequence-shape smells.
- Spec: public plan canonical digest admission, false success from a missing tap result, center/bounds validation, and complete probe/dispatch lineage were corrected and regression-tested. No scope-creep finding.

## Artifact inventory and checksums

- `verification/full-pytest.xml`: full-suite JUnit report.
- `verification/runner-pytest.xml`: focused-suite JUnit report.
- `checksums.sha256`: SHA-256 checksums for both reports.
- `issue-comment.md`: exact evidence body posted to GitHub issue #203.
- No screenshots, layout dumps, device logs, or generated JSON were produced: validation used the checked-in recording adapter and fake OpenCalc layouts.

## Known gaps

- No real Android device or emulator was available or used in this run, so physical dispatch/manual verification remains outstanding. The recording adapter verifies the exact command vector, coordinates, order, retry count, and settle calls.
- A broader mypy pass over legacy runner modules still reports pre-existing typing debt; the new deterministic backend passes the scoped mypy check above.

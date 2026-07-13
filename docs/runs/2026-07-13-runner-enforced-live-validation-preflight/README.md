# 2026-07-13 runner-enforced live-validation preflight

Issue: #37

## Result

Implemented runner-enforced live-validation preflight for Verification Agent
runs.

The runner now executes the generic live-validation gate before logcat clearing,
host launch, Journey driving, or oracle evaluation. It persists
`live-validation-gate.json` beside `verdict.json` and links that artifact from
`preflight.live_validation_gate`.

When the gate fails, the runner writes a non-accountable verdict with
`execution.reason=live_validation_preflight_failed`,
`metric_context.seed_outcome=not_accountable`, and no L1/L2/L3 oracle verdicts.
The host app is not launched and the Journey runner is not constructed.

## Scope

Code and documentation:

- `src/aiverify/runner/run_spec.py`
  - adds `live_validation` Run Spec configuration;
  - supports optional explicit `app_smoke` target-surface validation;
  - validates app-smoke activity and target-surface requirements.
- `src/aiverify/bench/live_validation_gate.py`
  - skips app-smoke launch when any generic gate check fails.
- `src/aiverify/runner/cli.py`
  - runs and persists mandatory preflight before app driving;
  - links the gate artifact from completed and non-accountable verdicts;
  - blocks host launch, Journey execution, oracle evaluation, and benchmark
    accounting when preflight fails.
- `docs/live-validation-gate.md`
  - documents the runner contract;
  - documents Run Spec app-smoke configuration;
  - classifies evidence captured before runner-enforced preflight as legacy.

Tests:

- `tests/runner/test_run_spec.py`
- `tests/runner/test_cli.py`
- `tests/bench/test_live_validation_gate.py`

## Verification Commands

Targeted tests:

```bash
.venv/bin/pytest tests/runner/test_run_spec.py tests/runner/test_cli.py tests/bench/test_live_validation_gate.py -q
```

Result: `43 passed`, `0 failed`.

Whitespace check:

```bash
git diff --check
```

Result: exit `0`, no output.

Full test suite:

```bash
.venv/bin/pytest -q
```

Result: `323 passed`, `0 failed`.

Warnings:

- `src/aiverify/agent/oracle/l2.py:123`: existing Element truth-value
  deprecation warning from
  `tests/agent/test_oracle_l2.py::test_l2_fail_when_node_gone`.
- `src/aiverify/agent/oracle/l2.py:123`: existing Element truth-value
  deprecation warning from
  `tests/bench/test_goldset_process_death_02_state_loss.py::test_defect_build_l2_fails_with_state_loss`.

Collected test count:

```bash
.venv/bin/pytest --collect-only -q | awk -F': ' '/: [0-9]+$/ {sum += $2} END {print sum}'
```

Result: `323`.

Checksum inventory:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums docs/runs/2026-07-13-runner-enforced-live-validation-preflight
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums --verify docs/runs/2026-07-13-runner-enforced-live-validation-preflight
```

Result: inventory generated at `checksums.sha256`; verify exit `0` with
`checksum inventory verified`.

## Acceptance Evidence

- Every new live runner invocation persists generic gate evidence:
  `test_completed_run_persists_and_links_live_validation_preflight` asserts
  `live-validation-gate.json` is written and linked from
  `preflight.live_validation_gate`.
- Failed generic preflight prevents launch, Journey, oracle accounting, and seed
  outcome creation:
  `test_failed_live_validation_preflight_is_non_accountable_and_blocks_launch`
  asserts `DeviceController` and `JourneySegmentRunner` are not constructed,
  verdict status is `non_accountable`, and seed outcome is `not_accountable`.
- Generic gate failure also prevents app-smoke launch:
  `test_live_validation_gate_skips_app_smoke_when_generic_gate_fails` asserts
  no `am start` command is issued after a failed generic layout check.
- Explicit app-smoke configuration stays host-neutral:
  `test_parse_run_spec_live_validation_app_smoke` and
  `test_app_smoke_preflight_uses_explicit_run_spec_configuration` use
  `com.example.host` and explicit target-surface criteria, not Wikipedia
  defaults.
- Timeout, command failure, malformed layout, and success paths are covered via
  the fake command-runner seam:
  `test_live_validation_gate_records_command_timeout`,
  `test_live_validation_gate_fails_on_uiautomator_dump_failure`,
  `test_live_validation_gate_fails_on_invalid_android_layout`, and
  `test_live_validation_gate_passes_when_all_checks_are_healthy`.
- Legacy evidence classification is documented in `docs/live-validation-gate.md`.

## Artifact Inventory

- `README.md` - this run record.
- `checksums.sha256` - generated checksum inventory for this run record.

## Known Gaps

- No Android emulator or physical device was used for this implementation
  verification. This is intentional for #37: the issue requested deterministic
  fake command-runner and Journey/backend seams rather than live hardware.
- Existing historical run records are not rewritten. Documentation now marks
  evidence without runner-enforced preflight as legacy.

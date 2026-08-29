# Issue #202 — deterministic resource-wait verification

Date: 2026-08-27 (America/New_York)

Status: **durable repository evidence when committed with the implementation**.
This record covers the minimal `deterministic_android_v1` execution slice from
fixed point `a2d989f` on branch `issue-197-runtime-source-preparation`.

## Outcome and claim boundary

The runner now admits a strict, checksum-bound deterministic Driver Plan with
one opaque `wait_for_resource_id` action. The backend receives only segment and
action identity, the admitted plan action, a read-only layout adapter, and an
opaque recording sink. It polls the device-scoped Android CLI layout for the
fixed 5-second/350-ms bound, retains every observation, and emits deterministic
raw evidence plus runner-owned backend-neutral normalized result and action
lineage artifacts.

`PASSED` proves only that the requested resource was observed exactly once;
this slice performs no tap, text entry, coordinate selection, oracle work, or
product-quality claim. Invalid plans are rejected before an `ExecutionRecord`
or device command. Deterministic identity binds the actual Android CLI tool,
marks model identity not applicable, and records a zero-model-call ledger; no
Codex receipt or Codex-named normalized artifact is produced.

## Implementation and acceptance evidence

- `src/aiverify/runner/deterministic_backend.py` implements strict plan parsing,
  exact Run Spec/action binding, the least-authority request, read-only layout
  adapter, fixed-bound Observation Poll, recording sink, raw result, and
  invocation evidence.
- `src/aiverify/runner/admission.py` validates deterministic plans during
  side-effect-free production-seam admission.
- `src/aiverify/runner/cli.py` validates source-backed plans before creating an
  `ExecutionRecord`, constructs the explicit deterministic backend, and rejects
  model/L3 configuration on this model-free slice.
- `src/aiverify/runner/journey.py` passes only the deterministic request shape
  and writes canonical backend-neutral result and complete action-lineage
  artifacts without Codex aliases.
- `src/aiverify/runner/execution_identity.py` records the actual deterministic
  Android CLI identity, explicit not-applicable model fields, and a
  checksum-bound zero-model invocation ledger; Codex provenance remains
  unchanged.
- `tests/runner/test_deterministic_backend.py` covers strict JSON/digest/action
  contracts, duplicate keys, pre-record rejection, success, bounded timeout,
  missing/duplicate resources, malformed layouts, read/sleep interruption,
  normalized evidence, and deterministic identity.
- Existing `tests/runner` and repository tests cover unchanged Codex behavior.

## Exact verification commands and results

All commands ran from `/Users/peter/projects/ai_verfication`.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -o addopts='' -q tests/runner --junitxml=docs/runs/2026-08-27-issue-202-deterministic-resource-wait/verification/runner-pytest.xml
```

Result: 358 tests, 0 failures, 0 errors, 0 skipped; pytest suite time 9.070s;
shell timing real 9.18s, user 4.21s, sys 4.18s.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -o addopts='' -q --junitxml=docs/runs/2026-08-27-issue-202-deterministic-resource-wait/verification/full-pytest.xml
```

Result: 1,342 passed, 1 skipped, 0 failures, 0 errors out of 1,343 tests;
pytest suite time 149.950s (2:29); shell timing real 150.05s, user 76.76s,
sys 62.81s.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src tests
git diff --check
```

Both commands passed with exit status 0. No real device, emulator, APK, model,
Codex CLI, or manual UI session was used; the device boundary was exercised by
recording fakes and the production adapter was limited to the read-only
`android layout --device=... --pretty` command.
The repository has no configured `.venv` `ruff` or `mypy` executables, so those
optional checks were not run.

```sh
cd docs/runs/2026-08-27-issue-202-deterministic-resource-wait
shasum -a 256 -c checksums.sha256
```

All four listed evidence artifacts verified with `OK` and exit status 0.

## Artifact inventory

| Artifact | Purpose | SHA-256 |
| --- | --- | --- |
| `verification/runner-pytest.xml` | Runner-focused JUnit report | `df7b706ae398c972f5fd4d18f832dbf24d51a278cb3908ee59f78dcc2289fd91` |
| `verification/full-pytest.xml` | Repository-wide JUnit report | `079d1c24a11c4f1502809650bc791a1a9912628a652b23cadcf2a639c1e3d27e` |
| `code-review.md` | Final standards/spec review | `835b8032ee8ae0e972194469327ca7d55a7fed6aa09d798cfd070ee877a3bc3d` |
| `checksums.sha256` | Machine-checkable run-record inventory | inventory file itself excluded |

The JUnit reports are the durable test-result artifacts. The source and test
files above are the authoritative implementation artifacts. No screenshots,
layout dumps, logcat, APKs, or live-device artifacts exist for this
model-free Python seam verification.

## Known gaps and limitation

- This issue intentionally admits exactly one wait action. The OpenCalc
  six-action plan and `tap_resource_id` primitive remain a later capability
  slice; this backend rejects them as out of scope.
- No real Android runtime was available or required in this validation, so
  device transport correctness beyond the narrow adapter command shape is not
  claimed.
- Evidence is durable because this directory is committed with the
  implementation.

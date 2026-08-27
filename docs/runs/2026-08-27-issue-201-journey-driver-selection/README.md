# Issue #201 — Journey Driver Selection verification

Date: 2026-08-27 (America/New_York)

Status: **durable repository evidence when committed with the implementation**.
This record verifies the runner-policy selection seam on branch
`issue-197-runtime-source-preparation`, from fixed point `6693fe1`.

## Outcome and claim boundary

The runner now admits exactly `codex_cli` and `deterministic_android_v1`,
defaults omitted selection to `codex_cli`, keeps selection and the optional
Driver Plan outside `RunSpec`, and rejects contradictory backend inputs before
any agent/device execution. A Codex-selected Journey uses the shared backend
seam, writes runner-owned neutral normalized result and action-lineage
artifacts, retains Codex raw result/event artifacts separately, and keeps
historical Codex-named normalized aliases readable.

`deterministic_android_v1` is intentionally only the admitted selection seam in
this issue. Its execution implementation, strict plan semantics, least-
authority request, and deterministic identity belong to issue #202; this code
fails closed with an unavailable-backend error and never falls back to Codex.
No Android device, emulator, build, provider, or model invocation was used in
this verification.

## Implementation and acceptance evidence

- `src/aiverify/runner/journey_backend.py` defines the closed backend identities,
  backend-neutral Journey result carrier, selection validation, checksum-bound
  Driver Plan binding, backend factory, and identity mismatch/unavailable errors.
- `src/aiverify/runner/admission.py` admits the selected backend and plan digest,
  resolves only the selected backend's prerequisites, and rebinds the plan on
  receipt verification.
- `src/aiverify/runner/cli.py` accepts `--backend` / `--journey-backend` and
  `--driver-plan` / `--driver-plan-path`, dispatches the selected backend, and
  preserves the existing Codex phase ordering and model handoff.
- `src/aiverify/runner/journey.py` separates backend raw evidence from neutral
  normalized result and action-lineage artifacts while retaining legacy Codex
  aliases for existing readers.
- `src/aiverify/runner/codex_backend.py` declares the Codex identity and keeps
  its request/result contract and raw evidence behavior intact.
- `src/aiverify/runner/execution_identity.py` records the selected Journey
  backend alongside the existing Codex tool and requested/effective model-role
  identity, while legacy provenance without the field remains verifiable.
- `tests/runner/test_journey_backend_selection.py` covers closed identities,
  defaulting, plan binding/drift, contradictory inputs, factory dispatch,
  canonical/raw evidence, request-boundary behavior, and no deterministic-to-
  Codex fallback.
- `tests/runner/test_execution_identity.py` covers the recorded Codex backend
  identity, legacy provenance without the new field, and rejects an invalid
  tampered backend identity.
- `tests/runner/test_cli.py` covers explicit `codex_cli` selection preserving
  the existing model handoff and runner dispatch.

## Exact verification commands and results

All commands ran from `/Users/peter/projects/ai_verfication`.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -o addopts='' -q tests/runner --junitxml=docs/runs/2026-08-27-issue-201-journey-driver-selection/verification/runner-pytest.xml
```

Passed: 338 passed, 0 failed, 0 skipped; pytest time 9.28s; wall time 9.36s.
The JUnit report records 338 tests in 9.068s.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -o addopts='' -qq --junitxml=docs/runs/2026-08-27-issue-201-journey-driver-selection/verification/full-pytest.xml
```

Passed: 1,322 passed, 0 failed, 0 errors, 1 skipped; 1,323 collected; pytest
JUnit time 150.522s; wall time 152.85s. The one skip is the repository's
pre-existing external-fixture gate.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src tests/runner/test_journey_backend_selection.py
git diff --check
uv run --with ruff ruff check src/aiverify/runner/journey_backend.py tests/runner/test_journey_backend_selection.py
```

All three commands passed with exit status 0. Tool versions were CPython
3.11.15, pytest 9.1.1, Ruff 0.16.4, uv 0.11.7, and Git 2.50.1.

## Artifact inventory

| Artifact | Purpose | SHA-256 |
| --- | --- | --- |
| `verification/runner-pytest.xml` | Runner-focused JUnit report, 338 tests | `839f8d80845c20054920c2b2a46c276a7165b4a47bfb0d20284a3ddaaffb8fb9` |
| `verification/full-pytest.xml` | Full repository JUnit report, 1,323 tests / 1 skip | `792a56159f59e11e9e287756d269562d91f3eda395b2e31f2f159e199ca8d956` |
| `code-review.md` | Final standards/spec review | `665c56fd2648f738d550fef3d4403e664bfa3c62eb527b92441d045d67ab5ded` |
| `checksums.sha256` | Machine-checkable inventory of every other run-record file | generated and verified after final edits |

No screenshots, layout dumps, logcat, APKs, device/emulator logs, generated
runtime JSON, model traces, or manual runtime artifacts exist for this
Python-only seam verification.

## Known gaps

- The deterministic backend is selected and admitted but is not executed until
  issue #202; no deterministic identity or primitive capability claim is made.
- Strict Driver Plan JSON/action validation and exact Run Spec digest binding
  are intentionally deferred to issue #202.
- The existing repository has pre-existing Ruff findings in several modified
  legacy modules; the new backend module and its contract test pass Ruff.
- Final review notes a non-blocking dynamic typing follow-up at the
  heterogeneous backend handoff; runtime backend identity guards are covered,
  and a fully typed deterministic request contract is deferred to #202.
- The evidence record is durable only after this directory is included in the
  implementation commit.

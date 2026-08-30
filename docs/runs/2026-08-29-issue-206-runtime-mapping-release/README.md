# Issue #206 — Atomic four-lane Runtime Mapping Release

Status: passed; evidence is committed with the implementation.

This run joins the completed OpenCalc ChangeTarget and ProjectTarget discovery
admissions into the frozen four-lane Runtime Calibration V1 mapping. It proves
the release boundary only. No Gradle build, APK preparation, Android CLI, adb,
device/emulator, runtime attempt, model, or oracle work was performed.

## Scope and identities

- Issue: [#206](https://github.com/yangliang2/ai_verification/issues/206)
- Parent: [#199](https://github.com/yangliang2/ai_verification/issues/199)
- Branch: `issue-197-runtime-source-preparation`
- Fixed point reviewed: `ea50276099b592c7ae52bb77125294b54a913371`
- Implementation commits before evidence publication: `3c0304e`, `05d47e1`, `24ffd6d`, `5321be8`, `9865162`, `b374b3a`
- Family: `opencalc-runtime-calibration-v1` / `v1`
- Release: `opencalc-runtime-mapping-release-v1`
- Candidate: `bench/runtime-calibration/opencalc-input-save-enabled-v1`
- Candidate identity: `1e247a243e2d9fcfc9704a641c5f1174b1f4cbceee7f2af28ad494d32c68bfd5`
- Candidate manifest SHA-256: `cda8a8946ea77720f2fb473517559fc2c65f7c56ed3b71fd329fec322147b04b`
- Candidate artifact inventory SHA-256: `393a19ce2ca16b60510ed21f80ba637df1bf3236da3b565fbc7a7856ad1eab14`
- Pinned source: `/Users/peter/hosts/opencalc-calibration`
- Pinned source commit: `0584d61189e916a62a3b402223b35e1d7a3093db`

The release contains exactly this opaque lane order:

1. `ocrc-v1-lane-01`
2. `ocrc-v1-lane-02`
3. `ocrc-v1-lane-03`
4. `ocrc-v1-lane-04`

The auditor-side meaning is ChangeTarget/control, ChangeTarget/defect,
ProjectTarget/control, and ProjectTarget/defect respectively. The driver
surface exposes only opaque projection IDs, fixed document shape, and a
serialization digest.

## Acceptance evidence

- `runtime_mapping.py` validates all four terminal discovery result objects,
  re-runs leakage auditing, checks zero build/device/model side effects, and
  cross-binds each source-rich package, blind projection, candidate projection,
  setup plan, driver plan, recipe, and Run Spec by identity and digest.
- Shared discovery contracts are compared by their neutral semantic fields;
  target-specific hypothesis delta/contract IDs are retained in the auditor
  package but are not incorrectly treated as a cross-lane mismatch.
- `RuntimeMappingRelease` requires exactly four ordered admissions and lanes,
  unique package/projection identities, matching discovery-result kinds, the
  `sealed_blind` → `mapping_released` transition, candidate identity, and
  uniform driver-visible shape.
- `write_runtime_mapping_release()` performs an exclusive fsync-and-hard-link
  creation of `mapping-release.json`; an existing release, reordered release,
  duplicate lane, or replacement fails without overwriting the original.
- Source meaning is available only through the typed `SourceAuthority` view;
  reducer meaning requires `RuntimeReducerAuthority` plus typed terminal
  evidence. Other consumers and premature reducer access fail closed.
- Candidate re-verification catches changed candidate bytes and input digests;
  strict persisted parsing catches duplicate/unknown fields, identity drift,
  changed lane meaning, and post-release discovery drift.
- The staged `admit-family` command requires an accepted
  `verify-candidate` predecessor, writes one start receipt, releases one
  mapping only after all four admissions pass, and writes one terminal receipt.
  Ordinary admission exceptions are terminalized as rejected rather than
  leaving an unaccounted started stage.

## Verification commands and results

Tool versions: CPython `3.11.15`, pytest `9.1.1`, Ruff `0.16.5`, mypy
`2.3.1`, uv `0.11.7`, Git `2.50.1 (Apple Git-155)`.

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.runtime_calibration verify-candidate --candidate-root bench/runtime-calibration/opencalc-input-save-enabled-v1 --output-root docs/runs/2026-08-29-issue-206-runtime-mapping-release/verification/candidate-stage
```

Result: accepted; 28 candidate artifacts; inventory
`393a19ce2ca16b60510ed21f80ba637df1bf3236da3b565fbc7a7856ad1eab14`; real
`0.17s`.

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.runtime_calibration admit-family --candidate-root bench/runtime-calibration/opencalc-input-save-enabled-v1 --source-root /Users/peter/hosts/opencalc-calibration --predecessor-root docs/runs/2026-08-29-issue-206-runtime-mapping-release/verification/candidate-stage --output-root docs/runs/2026-08-29-issue-206-runtime-mapping-release/verification/family-stage-final --materialization-root /tmp/opencalc-issue-206-runtime-mapping-materializations-final
```

Result: exit `0`; `mapping_released`; all four lanes in frozen order; real
`4.05s`; release identity and all lane/source-request identities are in
`verification/family-stage-final/mapping-release.json`.

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q tests/bench/test_opencalc_discovery.py tests/bench/test_runtime_calibration.py tests/bench/test_runtime_mapping.py --junitxml=docs/runs/2026-08-29-issue-206-runtime-mapping-release/verification/focused-pytest.xml
```

Result: **55 passed**, 0 failed/errors/skipped; pytest `57.599s`, real
`57.71s`.

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q --junitxml=docs/runs/2026-08-29-issue-206-runtime-mapping-release/verification/full-pytest.xml
```

Result: **1,395 passed, 1 skipped, 0 failed/errors** of 1,396 tests; pytest
`446.073s`, real `446.41s`. The pre-existing skip is
`tests.bench.test_m9_recovery_formal.test_frozen_target_specific_mismatch_is_side_effect_free`.

```text
uv run --with ruff ruff check src/aiverify/bench/runtime_mapping.py src/aiverify/bench/runtime_calibration.py tests/bench/test_runtime_mapping.py
uv run --with mypy mypy --ignore-missing-imports src/aiverify/bench/runtime_mapping.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m compileall -q src tests
git diff --check ea50276099b592c7ae52bb77125294b54a913371...HEAD
```

Results: Ruff and mypy passed; compileall and diff check exited `0`.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -c 'from aiverify.bench import runtime_mapping as m; p="docs/runs/2026-08-29-issue-206-runtime-mapping-release/verification/family-stage-final/mapping-release.json"; x=m.load_runtime_mapping_release(p); print(m.stage_status("docs/runs/2026-08-29-issue-206-runtime-mapping-release/verification/family-stage-final")); print(m.verify_runtime_mapping_release(x, candidate_root="bench/runtime-calibration/opencalc-input-save-enabled-v1")); print(x.identity_sha256, x.lane_ids, x.status, x.previous_status)'
```

Result: `accepted`, `True`, release identity
`bc98ab402cf6fbe73343749a2bfb11a12ba40e6efb56ec59e090c4bde840a8eb`, the
four frozen lane IDs, `mapping_released`, and `sealed_blind`.

## Review

The required two-axis review was attempted with parallel read-only Standards
and Spec workers. Both worker sessions stalled before returning reports, so
they were closed. The main review then inspected the fixed-point diff against
`AGENTS.md`, `CONTEXT.md`, `docs/agents/domain.md`, ADRs 0003–0005, the
frozen OpenCalc calibration specification, issue #206, and the changed
code/tests.

The review found and remediated one real implementation defect: full equality
of discovery hypothesis/plan objects rejected the valid target-specific
delta/contract fields. Commit `05d47e1` compares their neutral semantic
projection while retaining source-rich target binding. Commit `24ffd6d`
binds each admission receipt to the corresponding discovery-result kind.
Commit `9865162` ensures unexpected ordinary admission exceptions still
close the staged operation with a terminal rejection receipt. No unresolved
standards or specification blocker remains. Details are in `code-review.md`.

## Evidence inventory

- `verification/candidate-stage/stage-start.json` and `stage-terminal.json` —
  accepted candidate predecessor receipts.
- `verification/family-stage-final/stage-start.json`,
  `mapping-release.json`, and `stage-terminal.json` — final accepted
  four-lane release evidence.
- `verification/family-stage-pre-final/` — retained earlier successful smoke
  receipts from before terminal-exception hardening; not authoritative final
  output.
- `verification/focused-pytest.xml` — 54-test focused JUnit report.
- `verification/full-pytest.xml` — 1,395-test repository-wide JUnit report.
- `verification/verification.json` — machine-readable command, identity, and
  result summary.
- `code-review.md` — Standards/Spec review and remediation record.
- `checksums.sha256` — checksum inventory for every committed run artifact.

No screenshots, layout dumps, logcat, APKs, device receipts, or manual UI
artifacts exist because runtime execution is outside this issue's claim
boundary. Temporary ProjectTarget materializations remain under the documented
`/tmp` root; their source identities and clean-state receipts are preserved
in the committed mapping release, while the temporary trees themselves are not
committed.

## Claim boundary and follow-up

This proves only the model-free, side-effect-free four-lane Runtime Mapping
Release and its source/reducer consumption boundary. It does not prove source
build preparation, APK identity, device behavior, lifecycle evidence, oracle
outcomes, or a formal benchmark result. The next preparation/execution stages
must consume this release through the existing source-authority and runner
seams; they remain outside #206.

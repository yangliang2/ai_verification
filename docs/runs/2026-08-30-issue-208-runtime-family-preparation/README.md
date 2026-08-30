# Issue #208 — Four-lane Runtime Family Preparation

Status: passed; implementation and validation evidence are committed with the
family-preparation stage.

This run records the pre-device orchestration for the four opaque OpenCalc
Runtime Calibration lanes. It validates the accepted mapping predecessor and
candidate inputs, invokes each planned lane once in frozen order, records
lane-local/shared abort dispositions, preserves real artifacts, and closes the
family-wide APK admission gates. It does not create a device session or any
runtime attempt record.

## Scope and identities

- Issue: [#208](https://github.com/yangliang2/ai_verification/issues/208)
- Parent: [#199](https://github.com/yangliang2/ai_verification/issues/199)
- Blocker completed by: [#207](https://github.com/yangliang2/ai_verification/issues/207)
- Branch: `issue-197-runtime-source-preparation`
- Fixed point reviewed: `6c03f89`
- Family: `opencalc-runtime-calibration-v1` / `v1`
- Mapping release: `opencalc-runtime-mapping-release-v1`
- Mapping release identity: `bc98ab402cf6fbe73343749a2bfb11a12ba40e6efb56ec59e090c4bde840a8eb`
- Mapping release raw SHA-256: `947341f108f78d3100adc543d138f63e59279c66c27a4ea1c039a9c8df1eaa37`
- Candidate root: `bench/runtime-calibration/opencalc-input-save-enabled-v1`
- Candidate identity: `1e247a243e2d9fcfc9704a641c5f1174b1f4cbceee7f2af28ad494d32c68bfd5`
- Candidate manifest: `cda8a8946ea77720f2fb473517559fc2c65f7c56ed3b71fd329fec322147b04b`
- Candidate artifact inventory: `393a19ce2ca16b60510ed21f80ba637df1bf3236da3b565fbc7a7856ad1eab14`
- Frozen lane order: `ocrc-v1-lane-01`, `ocrc-v1-lane-02`, `ocrc-v1-lane-03`, `ocrc-v1-lane-04`

## Implementation evidence

- `src/aiverify/bench/runtime_family_preparation.py` provides the immutable
  lane input/result/row/terminal receipt contracts, fresh-worktree and recipe
  validation, one-call frozen-order orchestration, shared-health reproof,
  artifact preservation, stage receipts, and terminal re-verification.
- `src/aiverify/bench/runtime_calibration.py` exposes the explicit
  `prepare-family` command and a module-callable lane-input boundary. The
  command delegates exact, already-authorized lane input construction to the
  source boundary and never constructs runtime inputs from driver-visible
  meaning.
- `src/aiverify/runtime_family_preparation.py` is a compatibility import, and
  `src/aiverify/runtime_preparation.py` lazily exposes the family vocabulary
  without introducing an import cycle.
- `tests/bench/test_runtime_family_preparation.py` uses recording fakes to
  cover complete success through the default one-lane handoff, lane-local
  continuation, shared abort, interruption, artifact preservation, no runtime
  effects, and every family-wide gate.

The family stage emits only `prepared`, `preparation_rejected`,
`not_prepared_due_to_family_abort`, and `prepared_but_family_not_admitted`.
Failed family gates preserve the real sealed APK files in the output tree;
unstarted lanes have no synthetic receipt or lane output directory.

## Verification commands and results

Tool versions: CPython `3.11.15`, pytest `9.1.1`, Ruff `0.16.5`, mypy
`2.3.1`, uv `0.11.7`, Git `2.50.1 (Apple Git-155)`.

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run pytest -q tests/bench/test_runtime_family_preparation.py tests/test_runtime_sealed_apk.py tests/test_runtime_preparation.py tests/bench/test_runtime_mapping.py tests/bench/test_runtime_calibration.py --junitxml=docs/runs/2026-08-30-issue-208-runtime-family-preparation/verification/focused-pytest.xml
```

Result: **117 passed**, 0 failed/errors/skipped; pytest XML time `54.514s`,
wall time `54.83s`.

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run pytest -qq --junitxml=docs/runs/2026-08-30-issue-208-runtime-family-preparation/verification/full-pytest.xml
```

Result: **1,424 passed, 1 skipped, 0 failed/errors** of 1,425 tests; pytest
XML time `217.759s`, wall time `218.15s`. The sole skip is the pre-existing
`tests.bench.test_m9_recovery_formal.test_frozen_target_specific_mismatch_is_side_effect_free`
external-fixture case, which requires explicit admission.

```text
uv run --with ruff ruff check src/aiverify/bench/runtime_family_preparation.py src/aiverify/runtime_family_preparation.py src/aiverify/bench/runtime_calibration.py tests/bench/test_runtime_family_preparation.py
uv run --with ruff ruff format --check src/aiverify/bench/runtime_family_preparation.py src/aiverify/runtime_family_preparation.py tests/bench/test_runtime_family_preparation.py
uv run --with mypy mypy --follow-imports=skip --ignore-missing-imports src/aiverify/runtime_preparation.py src/aiverify/bench/runtime_family_preparation.py
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run python -m compileall -q src tests
git diff --check
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run python -m aiverify.bench.runtime_calibration prepare-family --help
```

All commands exited `0`; Ruff check/format, mypy, compileall, diff, and the
public command help passed. The two JUnit reports are retained under
`verification/`.

## Evidence inventory and checksums

- `verification/focused-pytest.xml` — 117-test focused JUnit report;
  SHA-256 `f296fa22850f8d422092e33dee63e11d7ff9aa647bda8bc966e82f8e92f8e26e`.
- `verification/full-pytest.xml` — 1,425-test repository-wide JUnit report;
  SHA-256 `e19fb1166861f056053a093e0407197dacc54225c2f6ed07d51b366751297005`.
- `verification/verification.json` — machine-readable command/result and
  acceptance summary.
- `code-review.md` — final Standards/Spec review and remediation record.
- `checksums.sha256` — checksum inventory for every committed run artifact.

No APK, private vault bytes, credentials, screenshots, layout dumps, logcat,
device receipts, execution records, or generated model evidence is committed.

## Claim boundary and known gaps

The recording-fake tests prove the orchestration and persistence contract but
do not claim a real Gradle build, `aapt2`, `apksigner`, Android CLI, adb,
emulator, device, or manual runtime session. The production path requires the
four source-authorized lane inputs, the external Runtime Input Vault, real
tool identities, and strict mapped authorities. No lane `ExecutionRecord`,
install, launch, Journey, lifecycle event, oracle, agent, or model call is
created by this stage. The one external-fixture skip is documented above.

The CLI lane-input provider is an explicit source-authority boundary: it must
return the four already-materialized inputs and must not perform a build. The
committed #206 mapping currently records one shared ChangeTarget source path
for lanes 01/02; strict family preparation rejects that non-independent input
until a fresh per-lane source mapping is issued. The recording-fake success
path uses the explicit test-substitute flag and does not claim strict production
admission.

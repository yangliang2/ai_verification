# Issue #207 — Mapped lane sealed Runtime APK

Status: passed; implementation and verification evidence are committed.

This run records the side-effect-free handoff from one mapped Runtime Calibration
lane to an inspected, immutable APK. It covers source/mapping admission,
external vault and signing provenance, the fixed offline build contract, APK
inspection and sealing, and runner re-verification. Device deployment,
`adb`, model, and oracle work remain outside this issue.

## Scope and identities

- Issue: [#207](https://github.com/yangliang2/ai_verification/issues/207)
- Parent: [#199](https://github.com/yangliang2/ai_verification/issues/199)
- Blocker completed by: [#206](https://github.com/yangliang2/ai_verification/issues/206)
- Branch: `issue-197-runtime-source-preparation`
- Fixed point reviewed: `e015604`
- Family: `opencalc-runtime-calibration-v1` / `v1`
- Mapping release: `opencalc-runtime-mapping-release-v1`
- Mapping release identity: `bc98ab402cf6fbe73343749a2bfb11a12ba40e6efb56ec59e090c4bde840a8eb`
- Candidate root: `bench/runtime-calibration/opencalc-input-save-enabled-v1`
- Candidate identity: `1e247a243e2d9fcfc9704a641c5f1174b1f4cbceee7f2af28ad494d32c68bfd5`
- Candidate manifest: `cda8a8946ea77720f2fb473517559fc2c65f7c56ed3b71fd329fec322147b04b`
- Candidate artifact inventory: `393a19ce2ca16b60510ed21f80ba637df1bf3236da3b565fbc7a7856ad1eab14`
- Tested lane: `ocrc-v1-lane-01`
- Materialized source tree: `8793c063c6a990ff3448fece38e62bc103952610`
- Frozen source commit: `0584d61189e916a62a3b402223b35e1d7a3093db`
- Required build output: `app/build/outputs/apk/debug/app-debug.apk`
- Lane-local sealed output: `build/app-debug.apk`

The public tests use an isolated mapped source view plus explicit
`allow_test_substitutes=True` for the build and APK inspector. The production
path requires a full `RuntimeMappingRelease` with its candidate root, the
`SubprocessCommandRunner`, and `AaptApkInspector`; substitute use is recorded
in the receipt and is never implicit.

## Acceptance evidence

- `MappedRuntimeSourceAuthority` consumes the released mapping, verifies the
  selected lane and candidate input digests, rechecks the source request and
  worktree identities, and binds the candidate projection/driver plan/recipe/
  Run Spec before build.
- `RuntimeInputVaultManifest` records only the external canonical root,
  retention status, exact relative inventory, sizes, SHA-256 digests, aggregate
  digest, and public signing identity. Private key bytes, passwords, and
  credentials are rejected from the manifest schema.
- Vault files and the manifest are verified read-only, regular, single-link,
  checksum-bound, complete, and free of symlink/extra/missing drift. Build
  dependencies and the non-production keystore are copied as separate
  read-only files into private homes.
- `RuntimeBuildRecipe` enforces the exact offline clean debug vector, fixed
  environment allowlist, private homes, explicit tool identity, 900-second
  bound, and no retry. Admission and all input checks complete before the one
  build call; runtime/device/agent effects remain false.
- `AaptApkInspector` parses package, launcher, version, SDK, and debuggable
  metadata and, for the production path, runs explicit `apksigner verify
  --verbose --print-certs` against the authorized certificate with V1/V2
  verification. Ambient APK/signing overrides are rejected.
- The strict path rejects missing, extra, escaped, non-regular, linked,
  nonzero, timed-out, mismatched, and drifted outputs; hashes the APK across
  inspection and source re-admission; atomically writes a read-only lane-local
  sealed copy; and binds its path, size, and digest to the receipt.
- `verify_runtime_preparation_receipt` revalidates the sealed artifact,
  private inputs, source handoff, mapping, metadata, and no-runtime claim before
  the runner can establish an `ExecutionRecord`. The runner consumes only the
  sealed artifact and rejects ambient/custom identity overrides.

## Verification commands and results

Tool versions: CPython `3.11.15`, pytest `9.1.1`, Ruff `0.16.5`, mypy
`2.3.1`, uv `0.11.7`, Git `2.50.1 (Apple Git-155)`.

```text
uv run pytest -q tests/test_runtime_sealed_apk.py tests/test_runtime_preparation.py --junitxml=docs/runs/2026-08-29-issue-207-runtime-sealed-apk/verification/focused-pytest.xml
```

Result: **72 passed**, 0 failed/errors/skipped; pytest XML time `37.698s`.

```text
uv run pytest -qq --junitxml=docs/runs/2026-08-29-issue-207-runtime-sealed-apk/verification/full-pytest.xml
```

Result: **1,407 passed, 1 skipped, 0 failed/errors** of 1,408 tests; pytest
XML time `255.181s`. The sole skip is the pre-existing
`tests.bench.test_m9_recovery_formal.test_frozen_target_specific_mismatch_is_side_effect_free`
external-fixture case.

```text
uv run --with ruff ruff check --select E,F,I src/aiverify/runtime_preparation.py src/aiverify/runner/command.py tests/test_runtime_sealed_apk.py
uv run --with ruff ruff format --check src/aiverify/runtime_preparation.py src/aiverify/runner/command.py tests/test_runtime_sealed_apk.py
uv run --with mypy mypy src/aiverify/runtime_preparation.py --follow-imports=skip --ignore-missing-imports
uv run python -m compileall -q src tests/test_runtime_sealed_apk.py
git diff --check
```

Results: all commands exited `0`; Ruff check and format passed, mypy reported
no issues, and compileall/diff checks passed.

## Evidence inventory and checksums

- `verification/focused-pytest.xml` — 72-test focused JUnit report.
- `verification/full-pytest.xml` — 1,408-test repository-wide JUnit report.
- `verification/verification.json` — machine-readable command/result and
  acceptance summary.
- `code-review.md` — final Standards/Spec review and remediation record.
- `checksums.sha256` — checksums for the committed run artifacts below.

No APK, private vault bytes, credentials, screenshots, layout dumps, logcat,
device receipts, or execution records are committed. Test fixtures use
ephemeral temporary roots; successful fixtures are removed by pytest cleanup.

## Claim boundary and known gaps

No real Gradle build, `aapt2`, `apksigner`, Android CLI, `adb`, emulator,
device, runtime attempt, model, or oracle invocation was performed. The
production classes and exact command paths are implemented, while the public
success test uses explicit build/inspection substitutes as allowed by issue
#207. The production full-release mapping path is intentionally separate from
the direct source-view substitute seam. The external dependency/signing vault
is represented by test fixtures only and must be supplied by the later runtime
lane execution stage.

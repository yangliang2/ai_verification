# M9-R1 recovery baseline and package-reset hardening

Status: implementation, verification, and dual-axis review passed their R1
scope for issue #148. The merge/tracker completion gate remains mandatory
before R2 begins. This is a recovery-readiness result only. It does not change
the immutable #137 `Not Supported` aggregate and does not execute any frozen
#136/#137 lane.

## Outcome

R1 established a clean recovery worktree at
`716ce60020916127176b24c71e3829f603468a5e` (the latest `origin/main` when
the issue started), reproduced the pre-install failure without invoking a
formal lane, and replaced the ambiguous `pm clear` interpretation with an
explicit package-presence decision:

- `pm path` empty stdout/stderr with exit 1 means the exact package is
  already absent, so no clear command is dispatched;
- one or more unique absolute `package:` paths with exit 0 prove the package
  is installed, after which `pm clear` must return exit 0, stdout `Success`,
  and empty stderr;
- query failures, malformed or contradictory path output, controller/device
  identity mismatch, and installed-package clear failures all fail closed
  with a terminal receipt.

The package reset now runs through the public runner's `pre_run_setup` phase,
after its `ExecutionRecord` is established. The frozen #137 executor remains
guarded by its exact-commit preflight and was not rerun.

## Diagnosis

The historical command and result are preserved in
[`diagnosis.json`](diagnosis.json). A current API-35 probe reproduced the same
semantics:

```text
adb -s emulator-5554 shell pm path com.example.android.architecture.blueprints.main
→ exit 1; stdout empty; stderr empty

adb -s emulator-5554 shell pm clear com.example.android.architecture.blueprints.main
→ exit 1; stdout "Failed"; stderr empty
```

The first response proves the package is absent; the second response alone
does not. Matching only the generic word `Failed` could therefore hide a real
clear failure on an installed package. The new operation records exact device
and package identity and separates those states before deciding whether setup
may continue.

## Recovered canary-only baseline

Two new external target worktrees were created from the pinned upstream
baseline. The control remained clean. The defect started from the same
baseline and applied the already-committed #136 option-A patch with
`git apply --index`; no old formal lane worktree was used.

```text
control HEAD/tree:
ee66e1526b84c026615df032c705842b7d2a521f
19455e693ec8c96c37a56aec55059a220826c5a3

defect HEAD/index tree:
ee66e1526b84c026615df032c705842b7d2a521f
34998af23aed59aa17eaf915d848ab1b916a63e2

option-A patch SHA-256:
cc317d74012a83ab6a2e400fbc7442dfcb3bec8464fdbf68a1ba1cdc7974b277
```

Both isolated Gradle builds reproduced the historical APKs byte-for-byte:

| Variant | Build | APK bytes | SHA-256 |
|---|---:|---:|---|
| control | 43/43 tasks, 46.15s wall | 24,681,606 | `d38b30f17010da114b5585dadec8326eb76b04dfbae4a175f7cb2840a0093c66` |
| defect | 43/43 tasks, 28.90s wall | 24,681,461 | `61063a0fd247eb03d1bd251b0d9359c3c2a5ea07cb8abe4b38d3daae57c153ac` |

The exact recipe, paths, source trees, patch identity, builds, and APK
identities are in
[`recovery-baseline.json`](recovery-baseline.json). These historical fixtures
are explicitly `canary_eligible=true` and
`formal_qualification_eligible=false`. They may be used only by R2 and are
forbidden from R3, R4, or any M9 Supported conclusion.

## Verification

Targeted regression command:

```text
uv run --extra dev pytest -q -o addopts='' \
  tests/runner/test_package_reset.py \
  tests/harness/test_device_controller.py \
  tests/bench/test_m9_formal.py \
  tests/bench/test_m9_recovery_baseline.py \
  tests/runner/test_cli.py
→ 112 passed, 0 failed in 0.24s.
```

Full suite:

```text
/usr/bin/time -p uv run --extra dev pytest -q -o addopts=''
→ 889 passed, 0 failed in 33.38s.
→ real 33.50s; user 25.44s; sys 6.08s.
```

Static and package checks:

```text
uv run --extra dev python -m py_compile \
  src/aiverify/runner/package_reset.py \
  src/aiverify/harness/device/controller.py \
  src/aiverify/bench/m9_formal.py
→ passed.

git diff --check
→ passed.

uv build --quiet --out-dir /private/tmp/m9-r1-aiverify-package.V9Wx3L
→ aiverify 0.1.0 built in 0.87s.
→ wheel: 394,206 bytes,
  SHA-256 007b1c420960e7991f5060e82d71d6db2076a468d9c155d811786fd17462e959.
→ sdist: 358,146 bytes,
  SHA-256 fd58e8483a97d823c177908b2f8015b8f0f05352f6c947cced6a7286d71663f1.
```

Structured results are in
[`verification.json`](verification.json) and
[`package-build.json`](package-build.json).

## Dual-axis review

Standards and Spec were reviewed concurrently in separate read-only contexts
against fixed point
`716ce60020916127176b24c71e3829f603468a5e`. The initial findings were
Standards 1 Medium and Spec 1 High + 2 Medium. No package-reset behavior defect,
ADR conflict, material code smell, or scope creep was found.

The evidence findings are resolved by the diagnostic artifacts, review receipt,
and checksum ledger in this run record. The Spec High finding is the required
external sequencing gate: PR, merge, and the #148 completion comment must
finish before R2 starts. Full reports and resolutions are in
[`dual-axis-review.md`](dual-axis-review.md). A confirmation re-review of the
resolved evidence returned 0 material Standards findings and 0 material Spec
implementation/evidence findings.

## Implementation and tests

- `src/aiverify/runner/package_reset.py` implements the fail-closed semantic
  decision and auditable receipt.
- `src/aiverify/harness/device/controller.py` exposes the bound serial and the
  exact `pm path` query through the existing injectable ADB seam.
- `src/aiverify/bench/m9_formal.py` delegates future-only reset behavior and
  wires it through `pre_run_setup`; its exact #136 commit guard still prevents
  replay as a new formal population.
- `tests/runner/test_package_reset.py` covers absent, installed success,
  installed clear failure, query failure, malformed/duplicated paths, and
  controller/device contradiction.
- `tests/bench/test_m9_formal.py` checks success and failure receipts at the M9
  call site.
- `tests/bench/test_m9_recovery_baseline.py` locks the canary-only boundary and
  committed source/patch/APK identities, and verifies the complete run-record
  checksum inventory.

## Environment and artifact inventory

The emulator was `emulator-5554`, AVD `aiverify_api35`, API 35, build
fingerprint
`google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys`.
Android CLI layout and direct UIAutomator dump both passed. Tool paths,
versions, and important executable checksums are in
[`tool-versions.json`](tool-versions.json). Exact diagnostic commands/results
are in [`environment-diagnostics.json`](environment-diagnostics.json), with
the captured [Android layout](environment-layout.json) and
[UIAutomator hierarchy](environment-window-dump.xml).

Committed artifacts:

- this README;
- diagnosis and current live package-reset receipt;
- recovery recipe/source/build/APK identity receipt;
- tool/environment identity;
- environment diagnostics, Android layout, and UIAutomator hierarchy;
- test/build verification and aiverify package-build receipt;
- dual-axis review;
- 11-entry root checksum inventory.

Root checksum verification:

```text
(cd docs/runs/2026-08-07-issue-148-m9-r1-recovery-baseline &&
  shasum -a 256 -c checksums.sha256)
→ 11/11 entries passed.
```

External artifacts:

- `/private/tmp/m9-r1-canary-recovery/control/.../app-debug.apk`;
- `/private/tmp/m9-r1-canary-recovery/defect/.../app-debug.apk`;
- `/private/tmp/m9-r1-aiverify-package.V9Wx3L/` wheel and sdist.

These external artifacts are reproducible, non-formal inputs or disposable
build products. Their exact byte counts and SHA-256 identities are committed;
they are not claimed as durable formal qualification evidence.

Manual verification steps: none. Device actions were read-only environment
diagnostics plus package-presence/absent-package clear probes. No APK was
installed or launched in R1.

## Known gaps and claim boundary

- R1 did not exercise install, launch, codex-default identity, Verification
  Agent execution, oracle evaluation, independent review, or reconciliation.
  R2 must exercise all of those on these non-holdout canary inputs.
- The installed-package success path is regression-tested through the real ADB
  abstraction but is not claimed from a live installed target in R1.
- External APK/package archives are not committed repository artifacts.
- The original `issue-73-accessibility-slice` dirty worktree was not modified.
- #136/#137 issues, artifacts, checksums, lane attempts, and aggregate remain
  immutable. R1 neither repairs nor reinterprets their result.

R1 supports only recovery readiness, reproducible canary inputs, and
fail-closed pre-install package-reset semantics on the recorded local tool and
API-35 environment. It does not support M9 runtime behavior or a Supported
conclusion.

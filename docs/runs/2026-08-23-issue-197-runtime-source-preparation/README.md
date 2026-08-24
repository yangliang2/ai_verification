# Issue #197 runtime source preparation

Date: 2026-08-23 (America/New_York)

Status: **branch evidence, not pushed**. This record is committed with the
implementation it verifies, but it is not durable GitHub evidence until the
branch commits are pushed.

## Outcome

Issue [#197](https://github.com/yangliang2/ai_verification/issues/197) is
implemented as a non-formal DIL-M1 vertical slice. One public preparation
interface admits either a clean checkout or a sealed injected worktree, runs a
shell-free build vector only after admission, verifies exactly one APK, and
returns an immutable checksum-bound prepared/rejected receipt. The public runner
consumes one mutually exclusive `RuntimePreparationHandoff` and re-verifies the
source, complete build-visible worktree, Run Spec, runner options, receipt,
build executable, APK set/bytes, and manifest before it establishes an
`ExecutionRecord`.

This evidence proves local source/build preparation only. It does not prove a
real Android build, install, launch, device behavior, defect/control pair,
Discovery Campaign, Verification Agent invocation, oracle outcome, or benchmark
performance.

## Fixed point and implementation surface

- Branch: `issue-197-runtime-source-preparation`
- Implementation review fixed point:
  `0719a05cee1370849a553b1f9a517b3fcf0fc422`
- Issue labels at implementation start: `enhancement`, `ready-for-agent`

Acceptance criteria are implemented by:

- `src/aiverify/runtime_preparation.py`: `RuntimeBuildRecipe`, both source
  authority adapters, checked-in catalog rebinding, safe Gradle task admission,
  local APK inspection, immutable preparation receipts and handoffs,
  `prepare_runtime_case()`, and pre-run receipt verification;
- `src/aiverify/runner/admission.py`: structured immutable host/source authority
  values, the `SourceAuthority` seam, complete worktree identity, and a
  pristine-only compatibility path for legacy clean receipts;
- `src/aiverify/injection/materialization.py`: read-only reinspection of the
  exact tracked materialized tree, complete build-visible tree including
  Git-ignored paths, canonical staged diff, ownership marker, and untracked
  source boundary;
- `src/aiverify/injection/packets.py`: public canonical ChangeTarget packet-ID
  derivation used by the sealed authority;
- `src/aiverify/runner/cli.py`: mutually exclusive prepared handoff verification
  before `ExecutionRecordStore.establish()`;
- `tests/test_runtime_preparation.py`: temporary-Git and local-substitute public
  contract matrix.

## Exact verification commands and results

All commands ran from `/Users/peter/projects/ai_verfication`.

### Public preparation contract

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -o addopts='' -q tests/test_runtime_preparation.py --junitxml=docs/runs/2026-08-23-issue-197-runtime-source-preparation/verification/contract-pytest.xml
```

Result: 60 passed, 0 failed, 0 skipped; pytest time 23.72s, wall time
23.88s.

### Injection Lab and runner focused regression

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -o addopts='' -q tests/injection tests/runner tests/test_runtime_preparation.py --junitxml=docs/runs/2026-08-23-issue-197-runtime-source-preparation/verification/focused-pytest.xml
```

Result: 475 passed, 0 failed, 0 skipped; pytest time 122.53s, wall time
122.66s.

### Full repository regression

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -o addopts='' -qq --junitxml=docs/runs/2026-08-23-issue-197-runtime-source-preparation/verification/full-pytest.xml
```

Result: 1,293 collected; 1,292 passed, 0 failed, 1 skipped; JUnit suite time
304.162s, wall time 304.47s. The sole skip is the pre-existing
`test_frozen_target_specific_mismatch_is_side_effect_free`, which requires the
explicit `--run-external-fixtures` admission flag.

### Static and repository checks

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/python -m compileall -q src tests/test_runtime_preparation.py
git diff --check
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m aiverify.bench.run_record_checksums docs/runs/2026-08-23-issue-197-runtime-source-preparation
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m aiverify.bench.run_record_checksums docs/runs/2026-08-23-issue-197-runtime-source-preparation --verify
```

Results: all exited 0. `compileall` wall time was 0.09s. The checksum command is
run after the final evidence inventory is generated.

## Contract coverage

The public test matrix covers:

- clean and sealed-injection successful preparation;
- path, origin, baseline commit, result tree, result diff, receipt identity,
  tracked source, canonical packet identity, packet material, checked-in catalog,
  and ownership-marker drift;
- unsealed and fabricated injection authorities, self-consistent replacement
  packets, ordinary dirty checkout, and pre-existing Git-ignored inputs;
- admission-before-build ordering and admission runners restricted to read-only
  Git identity calls;
- explicit Gradle `assemble*`/`clean` plus safe-flag admission, and rejection of
  direct or `env`-nested shell, Android CLI, adb, emulator, full or abbreviated
  install/connected-device tasks, and Codex commands;
- build executable absence, exact argv contradiction, failure, timeout, and
  post-build source drift;
- missing, duplicate, aliased, outside-host, byte-drifted, package-mismatched,
  activity-mismatched, and uninspectable APKs;
- Run Spec, runner option, tracked or ignored source, receipt, APK set/bytes, and
  manifest drift at runner handoff, including APK mutation inside the inspector
  or final source-authority check;
- pristine legacy clean-receipt compatibility, ignored-byte rejection, and
  contradictory admission/preparation handoff rejection;
- immutable receipt exposure and a shell-free production `aapt2 dump badging`
  adapter.

Tests use synthetic package `org.example.injected`, launcher
`org.example.injected.MainActivity`, fixed local APK bytes, temporary Git
repositories, and a tracked no-op `gradlew` substitute. Per-build duration is
bound in each generated preparation receipt; no real host build duration or
real APK/application identifier is claimed by this run.

## Artifact inventory

- `verification/contract-pytest.xml`: 60-case public contract JUnit receipt.
- `verification/focused-pytest.xml`: Injection Lab/runner focused JUnit receipt.
- `verification/full-pytest.xml`: full repository JUnit receipt.
- `code-review.md`: Standards and Spec findings, remediations, and final clean
  review results.
- `verification.json`: machine-readable commands, counts, timings, and claim
  boundary.
- `tool-versions.txt`: host and verification tool versions.
- `checksums.sha256`: SHA-256 inventory for the files above and this README.

No screenshots, Android layout dumps, logcat, APK, device record, or manual UI
evidence exists because device/runtime work is explicitly outside this issue.

## Known gaps

- The production `AaptApkInspector` is contract-tested with a local command
  substitute; no real Android build-tools invocation occurs in this run.
- Cleanup of a built Injection Lab worktree remains under auditor ownership;
  this slice does not add a cleanup orchestrator or delete build output.
- The runner has an optional programmatic preparation handoff but no new public
  CLI flags; adding a preparation CLI is explicitly out of scope.
- No OpenCalc injected pair or Catima action was performed.

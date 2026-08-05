# M8-5 formal qualification (#122)

Date: 2026-08-05

## Result

The exact merged #121 manifest was admitted (37/37 admission checks, 12/12
ordered lane handoffs). The formal executor created one append-only terminal
attempt for each frozen lane, in order `lane-01` through `lane-12`. All 12
attempts were non-accountable at `execution-identity-capture` with the same
reason: the frozen Run Spec binds `host_project` to the lifecycle fixture
subdirectory, while the pre-fix runner required that path to equal the git
repository root. No APK install, activity launch, Codex invocation, system
event, screenshot, layout, or logcat evidence was reached. The qualification
conclusion is therefore `inconclusive`; no state-evolution supported/rejected
runtime claim is made.

The raw result is immutable. The runner compatibility fix is commit `22af9b2`
(explicit opt-in for a fixture host project below the captured repository),
but the frozen one-attempt lanes were not retried or replaced. A future runtime
qualification requires a newly frozen cohort/contract and is outside this
run.

## Commands and results

- `uv run python -m aiverify.bench.m8_formal --manifest bench/m8/m8-state-evolution-qualification-v1.json --repo-root /Users/peter/projects/ai_verification-m8-122 --artifact-root docs/runs/2026-08-05-issue-122-formal-execution --device emulator-5554 --workspace-root /Users/peter/projects/ai_verification-m8-122-workspaces`: completed; exact #121 ancestry verified; 12/12 terminal lane records; no retry/replacement.
- `adb devices -l`: `emulator-5554`, `sdk_gphone64_arm64`.
- `android --version`: `1.0.15498356`.
- `adb version`: `1.0.41`, platform `37.0.0-14910828`.
- `codex --version`: `codex-cli 0.144.6` (not invoked in a formal lane because identity failed first).
- `./gradlew --offline :app:assembleDebug` in each detached variant: control 2.727 s, defect 2.440 s; both APK metadata and no-INTERNET permission checks passed.
- `uv run pytest -q`: 821 tests collected and passed; final wall time 55.98 s
  (the environment had a slower second half than the earlier 28.32 s run).
- `uv build --out-dir package`: source distribution and wheel built successfully.
- Isolated wheel import check: `aiverify`, `aiverify.bench.m8_formal`, and `aiverify.runner.execution_identity` imported successfully.

## Artifact inventory

- `preflight.json`: exact manifest/admission handoff, side-effect-free.
- `qualification-input-verification.json`: contract provenance and matched-pair checksums.
- `admitted-package-bindings.json`: all 12 frozen package digests.
- `auditor-mapping-release.json`: mapping released only after plan admission.
- `build-receipts.json`, `build/control.apk`, `build/defect.apk`, and Gradle logs.
- `lane-01/` … `lane-12/`: setup receipt, terminal ExecutionRecord, runner verdict,
  state/migration/oracle/reduction receipts, and per-lane checksum file.
- `attempt-inventory.jsonl`: append-only 12-row inventory, one attempt each.
- `independent-adjudication.json`: ordered accounting, mode-separated cells,
  mapping, oracle/reduction and claim checks.
- `independent-adjudication-final-v2.json`: post-run independent reconciliation that
  reloads all 12 terminal records, oracle/reduction receipts, per-lane
  checksums, attribution, leakage, separate denominators, and claim boundary;
  it explicitly flags the original static migration receipts as unsupported.
- `admission_check.py` and `audit_reconciliation.py`: exact, side-effect-free
  regeneration/audit entry points used by the verification receipt.
- `post-run-diagnosis.json` and `post-run-amendment.json`: root cause, corrective
  action, and explicit no-rerun boundary.
- `formal-summary-amendment.json`, `verification-commands.json`, and
  `root-worktree-preservation.json`: final claim, command/timing/tool receipt,
  and caller dirty-root guard.
- `package/`: committed wheel and sdist; `package-verification.json` records
  sizes, SHA-256 digests, and isolated import check.
- `checksums.sha256`, each lane's `checksums.sha256`, and
  `important-checksums.sha256`: durable checksum inventory.

Important package checksums:

- wheel: `2db23a1f4a03d30137f9b203a880aa5b7e83eb1bd66e70755ac670305c48703d` (305412 bytes)
- sdist: `84c92beb7f47e77ab6757ae58ba724494280ceefd97f737056fb532685a73d18` (274183 bytes)
- control APK: `ca39fbdd5c964c842d0d75dbd9aef8cae30d13f30529908c5e9b07e30c087a7e` (930614 bytes)
- defect APK: `32e5d93a413f93368e897e5c2fde0949063f5a6b5ec8330d95caea0e6c2a1afe` (930611 bytes)

## Manual/device steps and gaps

The controlled device was the local API-35 emulator only. The executor issued
one `pm clear dev.aiverify.lifecyclefixture` per lane; each returned `Success`.
No network policy was changed and no production or upstream state was touched.
Because identity admission failed before deployment, no Journey action, backup
restore, process-death, screenshot/layout/logcat, or state oracle observation
exists. Those are known gaps and are the reason the result remains
non-accountable/inconclusive.

Claim boundary: frozen local fixture, exact recorded admission, and terminal
execution-accounting facts only. No Android generality, OEM/physical-device,
production, benchmark-rate, or M7-combined claim is made.

## Post-run reconciliation and immutability

The original 12 lane attempts are immutable. The common identity-capture
failure was diagnosed after the run and fixed in runner commit `22af9b2`; the
frozen cohort was not retried or replaced. The formal code now verifies the
checksum-bound Effective Execution Identity before accounting, requires an
observed old-to-current state transition before issuing migration evidence,
and fails closed when durable lane artifacts cannot be reloaded. These changes
are admission hardening for a future freshly frozen qualification and do not
alter this run's denominator.

`independent-adjudication-final-v2.json` records 12/12 ordered attempts, one attempt
per lane, 0/12 accountable, separate change/project denominators of 0/6
accountable (6 excluded in each), and an `inconclusive` qualification
conclusion. Its artifact reconciliation check fails closed on the pre-fix
static migration receipts; this is retained as a known evidence gap rather
than relabeled as runtime support. The original `formal-summary.json`,
inventory, lane receipts, and no-rerun diagnosis remain preserved.

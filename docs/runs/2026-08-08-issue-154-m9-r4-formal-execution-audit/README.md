# M9-R4 Phase B formal execution audit (#154)

Status: formal evidence sealed; aggregate interpretation reserved for M9-R5.

This record audits the one permitted M9-R4 formal invocation. It is deliberately
outside the sealed formal namespace at
`docs/runs/2026-08-07-m9-r4-formal-attempt-01/`; no file was added to or changed
inside that namespace after its root checksum ledger was written.

## Outcome

- Exact merged consumer commit:
  `ba81f04b088ce457ea4e047848f9ae4d60fcbc92`.
- Exact merged tree: `86fac0a045dc9418f385213a1361b0e4d6f530e8`.
- Formal command invocation count: exactly one.
- Process result: exit 2, `terminal_failed`, reported duration 0.206 seconds.
- Terminal stage: `PORTFOLIO_FROZEN`.
- Terminal reason: `M9RecoveryFormalError: target-specific Attack Plan was
  rejected: evidence expectations do not cover hypothesis requirements`.
- The contradictory packet was reproduced and rejected before build, device,
  agent, or runtime side effects and remained outside the denominator.
- Context Acquisition and the three-prior portfolio completed without side
  effects. The target-specific Attack Plan then failed closed before plan
  admission.
- Mapping release, leakage audit completion, fresh source-fixture creation,
  production-seam admission, device setup, APK install/launch, model invocation,
  runtime evidence, oracle evaluation, and falsification review were not reached.
- The consumer sealed six ordered terminal rows and six unique ExecutionRecord
  attempt identities. All are non-accountable typed absences; no runtime lane was
  executed.
- Counts: 0/6 accountable, 0/6 attempt-evidence-valid, 0/6 reviews survived,
  zero retry, zero replacement, and zero discretionary rerun.
- The formal summary retains `aggregate_result=reserved_for_M9_R5` and
  `formal_holdout_executed=false`. R5 must apply the frozen all-or-nothing gate.

The exact command was:

```text
uv run python -m aiverify.bench.m9_recovery_formal --execute --expected-consumer-commit ba81f04b088ce457ea4e047848f9ae4d60fcbc92
```

It was not retried after the terminal result and must never be invoked again for
this packet or namespace.

## Pre-execution verification

The isolated execution worktree was created from the exact Phase A merge:

```text
git fetch origin main
git worktree add -b m9-r4-formal-evidence /Users/peter/projects/ai_verification-m9-r4-phase-b ba81f04b088ce457ea4e047848f9ae4d60fcbc92
```

The following checks established a clean execution seal:

```text
git branch --show-current
git rev-parse HEAD
git rev-parse HEAD^{tree}
git rev-parse origin/main
git status --porcelain=v1 -uall | shasum -a 256
git diff --check
```

Results: branch `m9-r4-formal-evidence`; HEAD and `origin/main` both
`ba81f04b088ce457ea4e047848f9ae4d60fcbc92`; tree
`86fac0a045dc9418f385213a1361b0e4d6f530e8`; clean-status SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
`git diff --check` passed. The formal root and
`/private/tmp/m9-r4-formal-sources` were absent. The filesystem had 14,641,336
KiB free.

Android CLI was used first, before ADB inspection:

```text
/Users/peter/.local/bin/android --version
/Users/peter/.local/bin/android info
/Users/peter/.local/bin/android emulator list
adb devices -l
adb -s emulator-5554 shell getprop sys.boot_completed
adb -s emulator-5554 shell getprop ro.build.version.sdk
adb -s emulator-5554 shell getprop ro.boot.qemu.avd_name
adb -s emulator-5554 shell settings get secure default_input_method
codex login status
```

Results: Android CLI 1.0.15498356; `emulator-5554` online and boot-complete;
AVD `aiverify_api35`; Android 15 / API 35; arm64-v8a; 1080x2400; default IME
`com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME`;
Codex logged in using ChatGPT. These were read-only environmental checks, not
formal lane calls.

Both external R3 source/APK bindings were checked before the formal namespace
was claimed:

```text
git rev-parse HEAD
git rev-parse HEAD^{tree}
git remote get-url origin
git status --porcelain=v1 -uall | shasum -a 256
stat -f %z Jetchat/app/build/outputs/apk/debug/app-debug.apk
shasum -a 256 Jetchat/app/build/outputs/apk/debug/app-debug.apk
```

- Defect: commit `56b59e237b253bc52e2ce1141dce26af07503415`, tree
  `993432fb446913107df1bc0c040a05f8dae1c5b2`, APK 17,511,239 bytes,
  SHA-256 `41d7c3ff47f2f2d2a04942d11ab57c6c76ac7314ff6abf8dad14fd9b3149e55b`.
- Control: commit `038c8208307508ceedcb5dd07a4fe2794017644c`, tree
  `e658ec4cdbb25d8e75a04879e9e20a0c245832e9`, APK 17,511,449 bytes,
  SHA-256 `a1536cec09a33063f7796dc77e0effdf1847a3ad325dcef707216fa87d78386d`.
- Both origins were `https://github.com/android/compose-samples.git` and both
  worktrees were clean.

Static and external-input verification:

```text
/usr/bin/time -p uv run python -m aiverify.bench.m9_recovery_formal --static-preflight
/usr/bin/time -p uv run python -m aiverify.bench.m9_recovery_qualification --check-manifest
/usr/bin/time -p uv run python -c 'import json; from aiverify.bench.m9_recovery_formal import FormalInputs, _source_bindings, _validate_formal_inputs; inputs=FormalInputs(expected_consumer_commit="ba81f04b088ce457ea4e047848f9ae4d60fcbc92"); print(json.dumps(_validate_formal_inputs(inputs, _source_bindings(inputs)), ensure_ascii=False, sort_keys=True))'
```

Results: all passed. Static preflight reported zero device, model, and formal
lane calls; manifest SHA-256
`aa860f4b10144c2e6374912685ef914a420a234fc805d36cebb72b0c705629ad`;
packet commitment
`a2ae1d8ca4902a500c67aa6107a0f42fe06a3948ca484305861d2d2670033225`;
57-entry R3 ledger SHA-256
`0d3b311387dae768cf361a1f7683605a97600851ccb1e38c8ce2632b3ee9dc47`.
Static preflight took 8.47 seconds including initial environment creation;
manifest validation took 0.14 seconds; input binding took 0.26 seconds.

The first focused-test command did not enter collection because the new virtual
environment did not yet include the optional `dev` extra:

```text
/usr/bin/time -p uv run pytest tests/bench/test_m9_recovery_formal.py tests/bench/test_m9_recovery_qualification.py
```

It exited 2 with `Failed to spawn: pytest`. The declared development extra was
then installed and the identical test command was rerun:

```text
uv sync --extra dev
/usr/bin/time -p uv run pytest tests/bench/test_m9_recovery_formal.py tests/bench/test_m9_recovery_qualification.py
```

Result: 92 passed in 15.16 seconds; wall 17.77 seconds; no failures, errors, or
skips. This dependency setup and test rerun occurred before formal start and did
not claim the formal namespace.

## Evidence verification and inventory

The sealed formal root contains 28 files totaling 277,331 bytes:

- 21 valid JSON documents.
- One 27-entry root checksum ledger.
- Six two-entry per-lane checksum ledgers.
- Six ExecutionRecords and six typed-absence receipts.
- Zero screenshots, layout dumps, or logcat files because the attempt stopped
  before device execution.

Important sealed artifacts:

- `formal-start.json`
- `formal-input-preflight.json`
- `contradiction-rejection.json`
- `context-acquisition.json`
- `hypothesis-portfolio.json`
- `formal-attempt-terminal-failure.json`
- `formal-attempt-inventory.json`
- `auditor-reconciliation-input.json`
- `formal-execution-summary.json`
- `formal-artifacts/m9-r4-lane-01/` through
  `formal-artifacts/m9-r4-lane-06/`
- `checksums.sha256`

The root ledger SHA-256 is
`94488b89e52739e3d2fdd8d4d0633cc2feda104e90e5d2268ff51da598f28160`.
The exact checksum verification was:

```text
cd docs/runs/2026-08-07-m9-r4-formal-attempt-01
shasum -a 256 -c checksums.sha256
for lane in formal-artifacts/m9-r4-lane-*; do (cd "$lane" && shasum -a 256 -c checksums.sha256); done
```

Result: 27/27 root entries and 12/12 lane entries passed. All 21 JSON files
passed `jq empty`. The six attempt IDs are unique. An independent path/glob audit
checked all 258 declared absent artifacts and found zero violations.

No screenshot exists to inspect visually. No manual device/UI action was
performed. This is expected typed-absence evidence, not a skipped runtime QA
step.

## Tools and environment

- Formal Python: CPython 3.11.15 through uv.
- Host `python3`: 3.14.4.
- uv: 0.11.7 at `/Users/peter/.local/bin/uv`, SHA-256
  `40a78912c850286ea5756211f1f88c0928fb15b788869d46d4355cd4ac556023`.
- git: 2.50.1 Apple Git-155 at `/usr/bin/git`, SHA-256
  `506cb2ddd061e2992c8ee7c53853340688b53d9fcec94c3aa936524cea5b40cb`.
- Android CLI: 1.0.15498356 at `/Users/peter/.local/bin/android`, SHA-256
  `288c28a83023fb2c2385dc9f7ed4497d3ef7d39111213bcdb4cb30a93d0243fc`.
- ADB: 1.0.41 / 37.0.0-14910828 at `/opt/homebrew/bin/adb`, SHA-256
  `9fdf861259dc807937b13afdd5f053c7fda9f3b7726933fe0e0f45130ecb8dc7`.
- codex-cli: 0.144.6 at `/opt/homebrew/bin/codex`, SHA-256
  `80a3933d11a9d13ef806aa24f7bb8afc9169cfe4e9b09d6da6a92922cbde9cff`.

## Protected state and boundaries

The original dirty worktree remained unchanged before and after formal
execution:

- Path: `/Users/peter/projects/ai_verfication`.
- Branch: `issue-73-accessibility-slice`.
- HEAD: `ef94cb543b76254687acab5e2de1b6527076d9ae`.
- Status SHA-256:
  `af08d39f3854aa888b242408361083afe51117ad8ef078aa365cfaef19443ceb`.
- Tracked-diff SHA-256:
  `75e2cd7dc7750142ef17eab9e719f15cc2ee244600528ec6973a68e778239e57`.
- Staged-diff SHA-256:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

R1/R2 inputs were not reused. #136 and #137 were not rerun, copied, or changed;
#137 remains its immutable Runtime Not Supported result. This R4 attempt supports
no runtime, upstream, production, physical-device, OEM, ColorOS, benchmark-rate,
recall, or completeness claim.

## Known gaps and R5 hand-off

- The frozen target-specific Attack Plan could not satisfy the admitted
  hypothesis evidence requirements, so the formal holdout never reached runtime.
- There is no device/runtime Finding or local control rejection to interpret.
- Mapping release did not occur in the formal consumer. R5 must use the already
  committed auditor mapping, verify its canonical commitment, overlay roles only
  for mechanical reconciliation, and must not mutate this evidence.
- The one-attempt rule forbids fixing the consumer and trying this packet again.
- R5 must preserve the terminal rows, apply the frozen Supported gate, record the
  resulting `Not Supported` decision if any gate fails, and reconcile #154/#128
  without weakening the claim boundary.

Machine-readable audit facts are in `verification.json`. `checksums.sha256`
seals the files in this audit record.

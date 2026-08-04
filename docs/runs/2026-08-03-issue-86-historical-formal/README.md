# Issue #86 — formal historical qualification

Date: 2026-08-03 (UTC run completed 2026-08-04 00:52:04Z)  
Project commit: `cbcf84513bbe5ec173715fb0e71eabc98a43829a`  
Source checkout: local detached clone of `https://github.com/wikimedia/apps-android-wikipedia`  
Device: `emulator-5554`, API 35, `sdk_gphone64_arm64`

## Result

The approved formal historical slice completed with 18 accountable lanes: 9
pre-fix lanes produced the preregistered local rejection and 9 fixed lanes
passed. The raw instrumentation output contains 15 assertion failures across
the 9 pre-fix lanes (H-01: 1 per run, H-02: 3 per run, H-03: 1 per run) and
zero assertion failures across the 9 fixed lanes. All 18 instrumentation
processes, six builds, six deployments, and 18 package attempts exited 0.

| Slot | Pre-fix revision / build s | Pre-fix observations | Fixed revision / build s | Fixed observations |
|---|---|---|---|---|
| H-01 / T425894 | `b88c6a6…e03ce` / 7.14 | 3 × 1 test, 1 failure | `996ad85…81006` / 8.08 | 3 × 1 test, pass |
| H-02 / T379777 | `675b930…a2709` / 12.07 | 3 × 3 tests, 3 failures | `c7250ce…a56cfff` / 10.52 | 3 × 3 tests, pass |
| H-03 / T382892 | `d67ec44…6934c` / 11.07 | 3 × 1 test, 1 failure | `fdc4ffb…7c1e66` / 10.42 | 3 × 1 test, pass |

The independent audit is `independent-audit.md` and reports PASS. It reads
the raw instrumentation artifacts independently of the package verdicts,
checks all three packages, all 18 accountable attempts, source-state counts,
raw assertion counts, revision bindings, independent adjudication, and the
local-only claim boundary.

## Exact commands

The formal lane driver is `run-formal.sh`. It detached the local source clone
at each frozen revision, copied one project fixture into the temporary Android
test source tree, and removed that file after each revision. No branch, commit,
push, task comment, or pull request was made in the source repository.

Build command for each of the six revisions:

```text
JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew clean :app:assembleDevDebug :app:assembleDevDebugAndroidTest --offline --no-daemon
```

Deployment commands for each built revision:

```text
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 install -r -d app/build/outputs/apk/dev/debug/app-dev-debug.apk
adb -s emulator-5554 install -r -d app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk
```

Each of the three repetitions per source state then ran:

```text
adb -s emulator-5554 shell pm clear org.wikipedia.dev
/usr/bin/time -p adb -s emulator-5554 shell am instrument -w -e class org.wikipedia.m6.<fixture> org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Package validation and independent audit:

```text
PYTHONPATH=src uv run --no-project --with pytest --with pyyaml --with jsonschema --python 3.14 python -m aiverify.bench.m6_case_package validate docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-01.json --repo-root .
PYTHONPATH=src uv run --no-project --with pytest --with pyyaml --with jsonschema --python 3.14 python -m aiverify.bench.m6_case_package validate docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-02.json --repo-root .
PYTHONPATH=src uv run --no-project --with pytest --with pyyaml --with jsonschema --python 3.14 python -m aiverify.bench.m6_case_package validate docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-03.json --repo-root .
PYTHONPATH=src uv run --no-project --with pyyaml --with jsonschema --python 3.14 python docs/runs/2026-08-03-issue-86-historical-formal/independent_audit.py
```

Validation results were `status: valid` for all three packages. The audit
result was `Status: PASS`, with source states `fixed: 9`, `pre_fix: 9`,
outcomes `pass: 9`, `fail: 9`, raw assertion failures `fixed: 0`, `pre_fix: 15`,
and `accountable_attempts: 18`.

## Evidence inventory

- `lanes/`: six checkout/build/deploy records and 18 raw instrumentation
  repetitions, including per-attempt metadata and clear logs.
- `slots/`: 18 ExecutionRecord, provenance, and verdict artifacts.
- `packages/m6-h-01.json`, `m6-h-02.json`, `m6-h-03.json`: the three validated
  Qualification Case Packages with explicit matched pre-fix/fixed build
  identities and six source-state-bound ledger attempts each.
- `source/`: exact binary git diffs from each frozen pre-fix revision to its
  frozen fixed revision.
- `environment.txt`: project/source/device/tool versions and clean source
  checkout status.
- `independent-audit.json` and `independent-audit.md`: separate auditor
  evidence.
- `checksums.sha256`: SHA-256 inventory for every run artifact except the
  checksum file itself.

Important package source SHA-256 values:

```text
m6-h-01.json  3af5d84bdffd2210d41fa0ce2eca97517633a31273e08e830b12858b0ec224ea
m6-h-02.json  dc05bd5b23c6d1c2558ecbe671596c7bf0a5ee794b91d41b79ac1e362c010e04
m6-h-03.json  2fe06d8ccf892812f808d6c9f43d3c67bcbd0a3ac8a9bc53dbe5d7dcd3f38116
```

## Boundaries and gaps

This is a local emulator observation of the three frozen historical pairs. It
does not alter or accept upstream state and does not support a generalized
Android or cross-track conclusion. Instrumentation reports assertion failures
in its raw output while returning process exit 0; the package records those
assertions as the oracle outcome without converting them into process failures.
No real-device run was performed. Prospective #87 lanes and the six-package
aggregate in #88 remain separate follow-up work.

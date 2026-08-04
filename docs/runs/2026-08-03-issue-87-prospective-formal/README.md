# Issue #87 — formal prospective qualification

Date: 2026-08-03 (UTC run completed as recorded in `run-start.txt`)  
Project commit: `17654e4ee9a2993d245562b0f50a7033eba822a6`  
Source base: `79ef892e5e88dfea705350bbfa1be2ee14458b47`  
Device: `emulator-5554`, API 35, `sdk_gphone64_arm64`

## Result

The approved prospective slice completed 18 accountable lanes: three control
observations and three candidate observations for each of P-01, P-02, and P-03.
P-01 and P-02 candidates were locally supported (all three candidate runs
passed). P-03 is explicitly adjudicated `inconclusive`: its candidate removes
the duplicate setup path, but the frozen fixture simultaneously requires both
lifecycle commands to contain the Read More fragment and computes six
projected occurrences as a failure. That contradiction was preserved and not
fixed after candidate freeze.

| Slot | Candidate revision | Control | Candidate | Build wall |
|---|---|---|---|---:|
| P-01 / T425733 | `bb9a5a5…d60f9f` | 3 × 1 test, 1 failure | 3 × 1 test, pass | 70.98s |
| P-02 / T426893 | `2a95791…0a737` | 3 × 1 test, 1 failure | 3 × 1 test, pass | 71.67s |
| P-03 / T427224 | `a6d33f1…c14993` | 3 × 1 test, 1 failure | 3 × 1 test, oracle contradiction | 71.17s |

The shared control build took 27.60s. All four builds, four deployments, and
18 instrumentation processes exited 0. The independent audit is
`independent-audit.md` and reports PASS: 18/18 accountable, source states
`control: 9`/`candidate: 9`, six passing candidate observations, one
adjudicated inconclusive package, and verifier blinding checks passed.

## Development and freeze boundary

The Development Agent sessions are in `development/p-01/session.json` through
`development/p-03/session.json`. They contain task input, candidate patch,
source-base identity, effective model, prompt/session identity, network policy,
and local commit identity. Candidate commits were frozen before the formal
run:

- P-01: `bb9a5a5c2c7ae616ee7c560b5688697c09d60f9f` — initialize onboarding
  screen state from the app theme.
- P-02: `2a957912de43cc43e87f8ed81b34a1755ed0a737` — add the three offline-cache
  headers to the gallery image-metadata endpoint.
- P-03: `a6d33f1479c2a52ff5c4b13bb11242755c614993` — remove the duplicate setup
  Read More projection while retaining the lazy append path.

`candidate-freeze.json` is the machine-readable freeze record. No candidate
source or evidence was changed after the freeze. The Verification Agent
sessions in `verification/p-01/session.json` through `verification/p-03/session.json`
received only an opaque case id, behavior specification, Run Spec, fixture,
candidate revision/diff, and execution environment. Task URL/identifier,
developer reasoning, and fix history were withheld; network policy was
disabled.

## Exact commands

The formal driver is `run-formal.sh`. It builds one common control APK with all
three fixtures, then one candidate APK per frozen local commit. For each state
it clears app data and runs three repetitions.

Build command:

```text
JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew clean :app:assembleDevDebug :app:assembleDevDebugAndroidTest --offline --no-daemon
```

Deployment commands:

```text
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 install -r -d app/build/outputs/apk/dev/debug/app-dev-debug.apk
adb -s emulator-5554 install -r -d app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk
```

Instrumentation command per repetition:

```text
adb -s emulator-5554 shell pm clear org.wikipedia.dev
/usr/bin/time -p adb -s emulator-5554 shell am instrument -w -e class org.wikipedia.m6.<fixture> org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Package validation and audit:

```text
PYTHONPATH=src uv run --no-project --with pytest --with pyyaml --with jsonschema --python 3.14 python -m aiverify.bench.m6_case_package validate docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-01.json --repo-root .
PYTHONPATH=src uv run --no-project --with pytest --with pyyaml --with jsonschema --python 3.14 python -m aiverify.bench.m6_case_package validate docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-02.json --repo-root .
PYTHONPATH=src uv run --no-project --with pytest --with pyyaml --with jsonschema --python 3.14 python -m aiverify.bench.m6_case_package validate docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-03.json --repo-root .
PYTHONPATH=src uv run --no-project --with pyyaml --with jsonschema --python 3.14 python docs/runs/2026-08-03-issue-87-prospective-formal/independent_audit.py
```

All three package validations returned `status: valid`; the audit returned
`Status: PASS`.

## Evidence inventory and checksums

- `lanes/`: control/candidate checkout, build, APK, deployment, clear, and 18
  raw instrumentation artifacts.
- `development/`, `candidate-freeze.json`, `verification/`: session identity,
  blinding boundary, and immutable candidate records.
- `packages/`: three Qualification Case Packages plus verdict, oracle, and
  adjudication artifacts; each package has six source-state-bound attempts and
  a complete ledger.
- `source/`: exact base-to-candidate diffs for all three candidates.
- `environment.txt`: tool/device/source identities.
- `independent-audit.json`/`.md`: separate auditor evidence.
- `checksums.sha256`: SHA-256 inventory for every run artifact except itself.

Package SHA-256 values:

```text
m6-p-01.json  94b2f6a473019b5cc1a68a347f07304c50ed9cff69629a170b26925ec3d84fa4
m6-p-02.json  900fd46023b802abed30a9e70de8f96145cdb1e200a1bfa60e331ada6eeae3f5
m6-p-03.json  b96cc4c67e184c223a3ca5076eb03b08ba08218902179afebf8d9e32b621ba88
```

## Boundaries and gaps

This is a local API-35 emulator run only; no physical-device run was
performed. The source checkout stayed detached and clean after fixture/build
cleanup. No upstream branch, commit, push, task comment, pull request, or
acceptance assertion was created. The three packages make only local,
blinded-observation and adjudication claims; P-03 remains explicitly
inconclusive rather than being manually corrected.

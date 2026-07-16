# M3 v2 swallowed-Back L2 reliability re-baseline

Date executed: 2026-07-16 (America/New_York)

Issue: `#55` (parent `#48`)

Fixed point: `13b096bc40ef294a929de6323fbd21f20b387bec`

Manifest: `bench/goldset/m3-reliability-slice-v2.yaml`

Device: `aiverify_api35`, `emulator-5554`, Android 15 / API 35

The run-record directory retains the `2026-07-15` name fixed by the committed
schema-v2 manifest. The six live lanes themselves were executed on July 16.

## Result

All six fresh swallowed-Back lanes completed on their first attempt and were
accountable. All three baseline controls returned from SearchActivity to the
Search tab and passed L2 without a defect-class hypothesis. All three injected
defects remained in SearchActivity after the navigation Back and failed L2 with
`state_loss` under the corrected SearchActivity-versus-Search-tab evidence
boundary.

| Metric | Result |
|---|---:|
| Fresh swallowed-Back lanes executed | 6/6 |
| Formal attempts | 6 |
| First-attempt accountable | 6/6 |
| Eventual accountable | 6/6 |
| Retries | 0 |
| Baseline controls passed | 3/3 |
| Defects caught at L2 / `state_loss` | 3/3 |
| Total formal attempt time | 875.215 s |
| Operational interventions | 0 |

The evidence-derived full-v2 partial aggregate in `progress.json` is 30 planned,
6 pending, 23 first-attempt/eventually accountable, 11 passed controls, 12
caught defects, one historical retry, two historical preflight-environment
failures, and 2,994.442 seconds of formal attempt time. It includes the
committed ANR, oversized-state, and query-duplication slices and is not a final
M3 claim. The six remaining lanes belong to the Search-card L3 issue `#56`.

## Lane evidence

| Lane / attempt | Child runner exit | Accountability / result | Duration |
|---|---:|---|---:|
| `v2-swallowed-back-baseline-1/attempt-1` | 0 | accountable; L2 pass | 161.599 s |
| `v2-swallowed-back-baseline-2/attempt-1` | 0 | accountable; L2 pass | 126.656 s |
| `v2-swallowed-back-baseline-3/attempt-1` | 0 | accountable; L2 pass | 153.189 s |
| `v2-swallowed-back-defect-1/attempt-1` | 1 | accountable; L2 fail / `state_loss` | 134.359 s |
| `v2-swallowed-back-defect-2/attempt-1` | 1 | accountable; L2 fail / `state_loss` | 141.505 s |
| `v2-swallowed-back-defect-3/attempt-1` | 1 | accountable; L2 fail / `state_loss` | 157.907 s |

Every formal attempt retained a passing runner-enforced five-check
live-validation gate. Every Journey produced exact `action-1` / `action-2`
lineage with `PASSED` / `PASSED`, a pre-event checkpoint, the runner-injected
`dark_mode {night: yes}` boundary, and a post-event checkpoint. No accountable
outcome was retried.

## Corrected matched contract

Baseline and defect lanes used the same Wikipedia commit, Run Spec, package,
launch activity, two requested Journey actions, preference seed, light-mode
starting state, sentinel, Back sequence, configuration event, assertion, and
checkpoint boundary. The only intentional difference was the committed patch
in `SearchActivity.kt`.

The Journey contract was deliberately neutral about the destination:

1. From the main feed, tap `nav_tab_search`, then `search_card` to open
   SearchActivity.
2. Focus `search_src_text`, type and confirm `zznavbackqx`; press system Back
   once to hide the keyboard, then press system Back a second time for Activity
   navigation; after that command, stop immediately without inspecting the
   destination, pressing Back again, or navigating.

Each `action-2` command lineage contains exactly two Android system-Back events,
with the second Back as its terminal command. Android's equivalent adb key names
`BACK` and `KEYCODE_BACK` both occurred in retained evidence; no layout command
or interaction followed the second Back. Destination judgment therefore stayed
with L2 rather than leaking into the Journey action.

Each accountable attempt records:

- Journey segment
  `wikipedia-navigation-02-back-button-swallowed-segment-0`.
- Two exact requested actions from the Run Spec, both `PASSED` under stable-ID
  lineage.
- `injected_events=[{"event":"dark_mode","args":{"night":"yes"}}]`.
- Checkpoints `after-segment-0` and `after-event-0`.
- L1 `inconclusive` for both roles.
- Baseline: both layouts contain `search_card`, omit `search_src_text`, and show
  `nav_tab_search` selected; L2 `pass` with no defect class.
- Defect: both layouts omit `search_card` and retain
  `search_src_text=zznavbackqx`; L2 `fail` / `state_loss`, with the missing
  `search_card` preserved in verdict evidence.

The top-level baseline `metric_context.seed_outcome` remains `missed` because
the shared Run Spec describes an injected defect. The M3 role-aware aggregate
correctly classifies those baseline lanes as `passed_control`; this record does
not reinterpret that seed-local field in isolation.

## Historical protocol isolation

No M2 or schema-v1 attempt was copied into, linked as an attempt under, or
counted in this schema-v2 denominator. In particular:

- `docs/runs/2026-07-07-wikipedia-navigation-02-back-button-swallowed/` is M2
  history only.
- `docs/runs/2026-07-13-m3-swallowed-back-reliability/` is the schema-v1
  comparison package only.
- The four old destination-asserting baseline packages retained under that
  package's `superseded-protocol-evidence/` directory remain historical and
  outside this run.
- The schema-v1 defect-1 non-accountable attempt caused by a destination-
  asserting Journey is also history only.

This run has exactly six fresh v2 lane directories and exactly one fresh
attempt in each. Historical evidence informs the protocol correction but never
enters `progress.json` as new evidence.

## Exact build and deployment commands

The Wikipedia host was clean at
`6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`. The baseline source checksum before
the run was
`51231dffe24dbab3861db9858cbf423312e3107582f46d3da148941f2de207bc`.
The existing Gradle APK output was identified as the prior query-duplication
defect, so it was not reused before a successful fresh build.

Fresh baseline build, from `/Users/peter/hosts/wikipedia`:

```bash
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchActivity.kt
git apply --check \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
mkdir -p aiverify-builds/m3-v2-swallowed-back
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-v2-swallowed-back/baseline-app-dev-debug.apk
shasum -a 256 \
  aiverify-builds/m3-v2-swallowed-back/baseline-app-dev-debug.apk
stat -f '%z bytes' \
  aiverify-builds/m3-v2-swallowed-back/baseline-app-dev-debug.apk
```

Result: `BUILD SUCCESSFUL in 7s`; 77 tasks (1 executed, 5 from cache,
71 up-to-date); real 7.37 s; 121,628,105 bytes; SHA-256
`c0a3bfb315d758385918d273f5b5a36802ad59ec8e3b24c5492d8db97f7f06b0`.

Baseline deployment:

```bash
android run \
  --apks=/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-swallowed-back/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Android CLI reported `Installation completed successfully` and
`Activation completed successfully`.

Defect injection and build:

```bash
git apply --check \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
git apply \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchActivity.kt
git apply -R --check \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-v2-swallowed-back/defect-app-dev-debug.apk
shasum -a 256 \
  aiverify-builds/m3-v2-swallowed-back/defect-app-dev-debug.apk
stat -f '%z bytes' \
  aiverify-builds/m3-v2-swallowed-back/defect-app-dev-debug.apk
```

Result: patched source SHA-256
`751496c19d885c257984b3072acd61ce83d6a9a67c693fb2678e4351593ef8a6`;
`BUILD SUCCESSFUL in 9s`; 77 tasks (1 executed, 5 from cache,
71 up-to-date); real 10.02 s; 121,628,216 bytes; SHA-256
`bd3700b4fb92b832b0912a3b7f57a4e395985f80b9d53e33bdf960fc1670d1a0`.

Defect deployment:

```bash
android run \
  --apks=/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-swallowed-back/defect-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Android CLI again reported successful installation and activation.

## Exact per-attempt setup

Before every formal attempt, the device was reset to the same light-mode app
state. The committed six-key XML is identical in meaning to the corrected
historical swallowed-Back setup input and has SHA-256
`38bf4495419940a7887a0178597fe67ad2bba6449654643b501025803c208b18`.

```bash
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push \
  /Users/peter/projects/ai_verfication/docs/runs/2026-07-15-m3-v2-swallowed-back-reliability/setup-probes/issue55-prefs.xml \
  /data/local/tmp/issue55-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue55-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue55-prefs.xml \
  shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -W \
  -a android.intent.action.MAIN -c android.intent.category.LAUNCHER \
  -n org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --device=emulator-5554 --pretty \
  -o=<run-root>/setup-probes/<lane>-ready-layout.json
```

All six ready layouts contained 23 nodes and the `nav_tab_search` target. The
first baseline and first defect also used an independent generic-plus-app gate:

```bash
PYTHONPATH=/Users/peter/projects/ai_verfication/src \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.live_validation_gate \
  --device emulator-5554 \
  --app-package org.wikipedia.dev \
  --app-activity org.wikipedia.DefaultIcon \
  --target-resource-id nav_tab_search \
  --target-content-desc Search \
  --output <run-root>/setup-probes/<role>-1-preflight-gate.json
```

Both independent gates passed all eight checks. These setup probes are not lane
attempts and are outside oracle accounting. Every formal attempt separately ran
and persisted the public runner's mandatory five-check preflight.

## Exact public runner commands

An absolute `PYTHONPATH` was used because the child runner changes its working
directory to the Wikipedia host. The declarative Run Spec retains the comparison
host path `/Users/80268204/hosts/wikipedia`; the explicit `--workdir` selects the
actual clean host without editing the pinned spec.

```bash
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-swallowed-back-baseline-1 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-swallowed-back-baseline-2 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-swallowed-back-baseline-3 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-swallowed-back-defect-1 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-swallowed-back-defect-2 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-swallowed-back-defect-3 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
```

The outer orchestration commands returned zero after persisting each attempt.
The retained child exit codes are 0 for the three passing controls and 1 for the
three accountable caught defects.

Partial aggregate generation:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml plan \
  --json-output docs/runs/2026-07-15-m3-v2-swallowed-back-reliability/plan-after-swallowed-back.json
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml progress \
  --json-output docs/runs/2026-07-15-m3-v2-swallowed-back-reliability/progress.json
```

Strict final `summary` was not run because the six `#56` v2 lanes remain
pending.

## Restoration

After the last defect lane, the source patch was reversed, the exact baseline
checksum and clean Git state were reverified, and the fresh baseline APK was
reinstalled:

```bash
git apply -R --check \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
git apply -R \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchActivity.kt
git diff --exit-code -- app/src/main/java/org/wikipedia/search/SearchActivity.kt
git status --short --branch
android run \
  --apks=/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-swallowed-back/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

The restored source SHA-256 was
`51231dffe24dbab3861db9858cbf423312e3107582f46d3da148941f2de207bc`;
the Wikipedia worktree was clean on `main`; Android CLI reported successful
baseline installation and activation. Device-side SHA-256 of the installed
`base.apk` was
`c0a3bfb315d758385918d273f5b5a36802ad59ec8e3b24c5492d8db97f7f06b0`,
matching the saved baseline exactly. A final light-mode reset, 23-node layout,
and eight-check app-level restoration gate all passed with `nav_tab_search` /
`Search` present.

## Build outputs and tools

- Installed package: `org.wikipedia.dev`, versionCode `50594`, versionName
  `50594-dev-2026-07-13`.
- Android CLI `1.0.15498356`; adb `1.0.41`, platform-tools
  `37.0.0-14910828`; emulator `36.6.11.0`; Codex CLI `0.144.1`.
- Python `3.11.15`; pytest `9.0.3`; OpenJDK `17.0.19+0`; Gradle `9.5.1`;
  Git `2.50.1 (Apple Git-155)`.
- The two APKs remain outside the repository under
  `/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-swallowed-back/` because
  they total about 243 MB. Their absolute paths, exact sizes, and SHA-256 values
  are retained in `environment.json`.

## Artifact inventory

- 6 formal attempt directories and 6 attempt-level checksum manifests.
- 6 attempt records, passing live-validation gates, verdicts, and stdout/stderr
  pairs.
- 6 raw Journey results, normalized results, event streams, and stable-ID action
  lineage records.
- 12 checkpoint capture sets: before and after the dark-mode event for every
  lane, each retaining layout, logcat, commands, capture manifest, screenshot,
  and annotated screenshot.
- Under `lanes/`: 132 files total — 72 JSON, 6 JSONL, 24 PNG, 24 text/log, and
  6 checksum manifests.
- Under `setup-probes/`: 11 files — six ready layouts, two independent gates,
  one preference XML, and the final restoration layout/gate.
- `plan-after-swallowed-back.json`, `progress.json`, `environment.json`, this
  README, and the root checksum inventory.

## Operational interventions and known gaps

- There were no formal retries and no operational interventions. All six
  attempts completed inside the runner's own timeouts and were not interrupted.
- This seed used the available `aiverify_api35` Android 15 / API 35 AVD,
  matching the query-duplication v2 slice. The already committed v2 ANR and
  oversized-state slices used a `medium_phone` Android 16 / API 36 AVD on
  another host. The final `#57` audit must preserve this mixed-device identity
  and must not imply one homogeneous v2 device environment.
- No physical-device, cross-host, second-AVD, ColorOS, fully unattended, or
  visual-only/multimodal validation was performed. L3 is outside this L2 slice.
- Device screenshots were retained as secondary evidence. Destination and
  oracle conclusions were derived from resource-ID layout evidence, not visual
  text alone.
- The 12 device-originated `logcat.txt` checkpoint captures are retained
  byte-for-byte. A repository-wide `git diff --cached --check` reports 2,343
  trailing-whitespace entries across those 12 immutable raw logs (4,686 output
  lines). The scoped check over authored source and run metadata passes; raw
  evidence is not normalized after capture.
- This partial result does not claim the overall M3 v2 threshold passed; six L3
  lanes remain pending and the earlier ANR baseline lane remains exhausted.

## Verification

The committed evidence contract is covered by
`test_committed_v2_swallowed_back_progress_has_matched_auditable_attempts`. It
checks all attempt checksums, gates, exact Journey action lineage, the two-Back
terminal boundary, injected event and checkpoints, both role-specific surfaces,
baseline/defect L2 outcomes, partial aggregate snapshot, historical-protocol
isolation disclosure, and the root checksum.

TDD red command:

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/bench/test_m3_reliability.py::test_committed_v2_swallowed_back_progress_has_matched_auditable_attempts
# RED: 1 failed; FileNotFoundError for the not-yet-created progress.json
```

Final verification before review:

```bash
/usr/bin/time -p .venv/bin/pytest -o addopts='' -q \
  tests/bench/test_m3_reliability.py \
  tests/bench/test_run_record_checksums.py \
  tests/bench/test_goldset_navigation_02_back_button_swallowed.py \
  tests/bench/test_live_validation_gate.py \
  tests/runner/test_cli.py tests/runner/test_evidence.py \
  tests/runner/test_journey.py tests/runner/test_system_events.py
# 151 passed in 2.25s; real 2.40s

.venv/bin/python -m compileall -q src tests
# exit 0

/usr/bin/time -p .venv/bin/pytest -o addopts='' -q
# 417 passed in 7.80s; real 7.98s

.venv/bin/pytest -o addopts='' --collect-only -q
# 417 tests collected in 0.08s

git diff --cached --check -- \
  tests/bench/test_m3_reliability.py \
  docs/runs/2026-07-15-m3-v2-swallowed-back-reliability/README.md \
  docs/runs/2026-07-15-m3-v2-swallowed-back-reliability/environment.json \
  docs/runs/2026-07-15-m3-v2-swallowed-back-reliability/plan-after-swallowed-back.json \
  docs/runs/2026-07-15-m3-v2-swallowed-back-reliability/progress.json \
  docs/runs/2026-07-15-m3-v2-swallowed-back-reliability/setup-probes/issue55-prefs.xml
# exit 0

git diff --cached --check
# exit 2: 2,343 retained raw-log whitespace entries / 4,686 output lines

for attempt in \
  docs/runs/2026-07-15-m3-v2-swallowed-back-reliability/lanes/*/attempt-*
do
  PYTHONPATH=src .venv/bin/python \
    -m aiverify.bench.run_record_checksums --verify "$attempt" || exit
done
# six attempt inventories verified

PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-15-m3-v2-swallowed-back-reliability
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-15-m3-v2-swallowed-back-reliability
# checksum inventory verified; 147 covered files
```

All 85 JSON files, six JSONL streams, the preference XML, and 24 PNG evidence
files were also parsed or format-checked. The test suite produced no warnings in
this environment.

## Review

The required parallel Standards and Spec reviews used fixed point `13b096b` and
inspected the complete 149-file staged change.

- **Standards: PASS after remediation.** Initial review found that the new
  historical snapshot test used full equality against the evolving live v2
  aggregate. It was corrected to lock the committed #55 fields exactly while
  comparing future live progress monotonically, matching adjacent v2 tests. A
  follow-up finding tightened `failure_classes` from a lower bound to exact
  `{"preflight_environment": 2}`. Final independent re-review found no blocker.
- **Spec: PASS.** Zero missing, partial, incorrect, or out-of-scope behaviors
  were found. The reviewer independently checked the six fresh identities,
  passing preflights, retry bounds, matched neutral Journey and terminal second
  Back, role-specific layouts and L2 outcomes, historical isolation, derived
  aggregate, external build identity, restoration, and all checksums.

One non-blocking Fowler judgment remains: the seed-local evidence test repeats
some audit scaffolding from adjacent v2 tests. It is retained because the
swallowed-Back surface and terminal-event assertions are seed-specific; a
shared abstraction would currently obscure acceptance evidence.

Review summary: zero blocking Standards findings after remediation, one
non-blocking Standards judgment, and zero Spec findings.

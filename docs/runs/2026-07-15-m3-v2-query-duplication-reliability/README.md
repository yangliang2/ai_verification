# M3 v2 query-duplication L2 reliability re-baseline

Date executed: 2026-07-16 (America/New_York)

Issue: `#54` (parent `#48`)

Fixed point: `97f0a7ca83d2328937708dd55fffd989ea89aaba`

Manifest: `bench/goldset/m3-reliability-slice-v2.yaml`

Device: `aiverify_api35`, `emulator-5554`, Android 15 / API 35

The run-record directory retains the `2026-07-15` name fixed by the committed
schema-v2 manifest. The six live lanes themselves were executed on July 16.

## Result

All six fresh query-duplication lanes completed on their first attempt and were
accountable. All three baseline controls passed L2 without a defect-class
hypothesis. All three injected-defect repetitions failed L2 with `state_loss`;
their post-configuration-change layout and verdict evidence retain the actual
duplicated value `zzsentinelqxzzsentinelqx`.

| Metric | Result |
|---|---:|
| Fresh query-duplication lanes executed | 6/6 |
| Formal attempts | 6 |
| First-attempt accountable | 6/6 |
| Eventual accountable | 6/6 |
| Retries | 0 |
| Baseline controls passed | 3/3 |
| Defects caught at L2 / `state_loss` | 3/3 |
| Total formal attempt time | 895.299 s |
| Operational interventions | 0 |

The evidence-derived full-v2 partial aggregate in `progress.json` is 30 planned,
12 pending, 17 first-attempt/eventually accountable, 8 passed controls, 9 caught
defects, one historical retry, and two historical preflight-environment failures.
It includes the committed ANR and oversized-state slices and is not a final M3
claim.

## Lane evidence

| Lane / attempt | Child runner exit | Accountability / result | Duration |
|---|---:|---|---:|
| `v2-query-duplication-baseline-1/attempt-1` | 0 | accountable; L2 pass | 115.745 s |
| `v2-query-duplication-baseline-2/attempt-1` | 0 | accountable; L2 pass | 124.343 s |
| `v2-query-duplication-baseline-3/attempt-1` | 0 | accountable; L2 pass | 134.208 s |
| `v2-query-duplication-defect-1/attempt-1` | 1 | accountable; L2 fail / `state_loss` | 137.473 s |
| `v2-query-duplication-defect-2/attempt-1` | 1 | accountable; L2 fail / `state_loss` | 133.554 s |
| `v2-query-duplication-defect-3/attempt-1` | 1 | accountable; L2 fail / `state_loss` | 249.976 s |

Every formal attempt retained a passing runner-enforced five-check
live-validation gate. Every Journey produced exact `action-1` / `action-2`
lineage with `PASSED` / `PASSED`, a pre-event checkpoint, the runner-injected
`dark_mode {night: yes}` boundary, and a post-event checkpoint. No accountable
outcome was retried.

## Matched contract

Baseline and defect lanes used the same Wikipedia commit, Run Spec, package,
launch activity, two requested Journey actions, preference seed, light-mode
starting state, sentinel, configuration event, target state, assertion, and
checkpoint boundary. The only intentional difference was the committed source
patch in `SearchFragment.initSearchView()`.

Each accountable attempt records:

- Journey segment
  `wikipedia-config-change-02-query-duplication-segment-0`.
- Two exact requested actions, both `PASSED` under the remediated stable-ID
  lineage protocol.
- Pre-event `search_src_text=zzsentinelqx`.
- `injected_events=[{"event":"dark_mode","args":{"night":"yes"}}]`.
- Checkpoints `after-segment-0` and `after-event-0`.
- L1 `inconclusive` for both roles.
- Baseline L2 `pass`, no defect class, and post-event
  `search_src_text=zzsentinelqx`.
- Defect L2 `fail` / `state_loss`, with post-event
  `search_src_text=zzsentinelqxzzsentinelqx` in both layout and verdict evidence.

## Exact build and deployment commands

The Wikipedia host was clean at
`6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`. The baseline source checksum before
the run was
`324c78af401539508bdbdba117a1b6cd0c7fc8a52189880eff0e1c7b9da88f1f`.

Fresh baseline build, from `/Users/peter/hosts/wikipedia`:

```bash
mkdir -p aiverify-builds/m3-v2-query-duplication
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-v2-query-duplication/baseline-app-dev-debug.apk
shasum -a 256 \
  aiverify-builds/m3-v2-query-duplication/baseline-app-dev-debug.apk
stat -f '%z bytes' \
  aiverify-builds/m3-v2-query-duplication/baseline-app-dev-debug.apk
```

Result: `BUILD SUCCESSFUL in 6s`; 77 tasks (1 executed, 5 from cache,
71 up-to-date); real 6.78 s; 121,282,950 bytes; SHA-256
`7af65b50f282a2204595cb6e7a78a61a7c3370a06da2ee1306eb696982a1c957`.

Baseline deployment:

```bash
android run \
  --apks=/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-query-duplication/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Android CLI reported `Installation completed successfully` and
`Activation completed successfully`.

Defect injection and build:

```bash
git apply --check \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch
git apply \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchFragment.kt
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-v2-query-duplication/defect-app-dev-debug.apk
shasum -a 256 \
  aiverify-builds/m3-v2-query-duplication/defect-app-dev-debug.apk
stat -f '%z bytes' \
  aiverify-builds/m3-v2-query-duplication/defect-app-dev-debug.apk
```

Result: patched source SHA-256
`1dffe5a728827e511f88efec672694e177aa85dc0454466248b11a12ccc37eb1`;
`BUILD SUCCESSFUL in 6s`; 77 tasks (1 executed, 5 from cache,
71 up-to-date); real 7.00 s; 121,628,323 bytes; SHA-256
`f0a3a81272c6da61d5302024db47756c1de5f67b450cca7b3cb7f6a172be46de`.

Defect deployment:

```bash
android run \
  --apks=/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-query-duplication/defect-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Android CLI again reported successful installation and activation.

## Exact per-attempt setup

Before every formal attempt, the device was reset to the same light-mode app
state. The committed XML is identical to the historical query seed's prompt
suppression input and has SHA-256
`b1ec08c27a08386af03ae3841e923c55d9be82c6a49a520cfacf60be7b28484c`.

```bash
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push \
  /Users/peter/projects/ai_verfication/docs/runs/2026-07-15-m3-v2-query-duplication-reliability/setup-probes/issue54-prefs.xml \
  /data/local/tmp/issue54-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue54-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue54-prefs.xml \
  shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER \
  -n org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --device=emulator-5554 --pretty \
  -o=<run-root>/setup-probes/<lane>-ready-layout.json
```

All six ready layouts contained 23 nodes and the `nav_tab_search` target. The
first baseline and first defect also used an independent generic-plus-app gate:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.live_validation_gate \
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
directory to the Wikipedia host. This avoids the historical #44 discarded
invocation where a relative `PYTHONPATH=src` resolved under the host.

```bash
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-query-duplication-baseline-1 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-query-duplication-baseline-2 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-query-duplication-baseline-3 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-query-duplication-defect-1 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-query-duplication-defect-2 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
PYTHONPATH=/Users/peter/projects/ai_verfication/src /Users/peter/projects/ai_verfication/.venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-query-duplication-defect-3 --device emulator-5554 --workdir /Users/peter/hosts/wikipedia --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
```

The outer orchestration commands returned zero after persisting each attempt.
The retained child exit codes are 0 for the three passing controls and 1 for the
three accountable caught defects.

Partial aggregate generation:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml plan \
  --json-output docs/runs/2026-07-15-m3-v2-query-duplication-reliability/plan-after-query-duplication.json
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml progress \
  --json-output docs/runs/2026-07-15-m3-v2-query-duplication-reliability/progress.json
```

Strict final `summary` was not run because 12 v2 lanes remain pending.

## Restoration

After the last defect lane, the source patch was reversed, the exact baseline
checksum and clean Git state were reverified, and the fresh baseline APK was
reinstalled:

```bash
git apply -R --check \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch
git apply -R \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchFragment.kt
git status --short --branch
android run \
  --apks=/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-query-duplication/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

The restored source SHA-256 was
`324c78af401539508bdbdba117a1b6cd0c7fc8a52189880eff0e1c7b9da88f1f`;
the Wikipedia worktree was clean on `main`; Android CLI reported successful
baseline installation and activation. A final light-mode reset, 23-node layout,
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
  `/Users/peter/hosts/wikipedia/aiverify-builds/m3-v2-query-duplication/`
  because they total about 243 MB. Their absolute paths, exact sizes, and
  SHA-256 values are retained in `environment.json`.

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
- `plan-after-query-duplication.json`, `progress.json`, `environment.json`, this
  README, and the root checksum inventory.

## Operational interventions and known gaps

- There were no formal retries and no operational interventions. The longer
  defect-3 Journey (234.015 s of its 249.976 s total) completed under the
  runner's own timeout and was not interrupted.
- The Run Spec retains the comparison-pinned declarative host path
  `/Users/80268204/hosts/wikipedia`. The public runner's explicit
  `--workdir /Users/peter/hosts/wikipedia` selected the actual clean host for all
  six executions. The Run Spec and manifest were intentionally not edited.
- This seed used the available `aiverify_api35` Android 15 / API 35 AVD, matching
  historical query run #44. The already committed v2 ANR and oversized-state
  slices used a `medium_phone` Android 16 / API 36 AVD on another host. The final
  #57 audit must preserve this mixed-device identity and must not imply one
  homogeneous v2 device environment.
- No physical-device, cross-host, second-AVD, ColorOS, fully unattended, or
  visual-only/multimodal validation was performed. L3 is outside this L2 slice.
- The 12 device-originated `logcat.txt` checkpoint captures are retained
  byte-for-byte. Consequently, a repository-wide `git diff --cached --check`
  reports 4,860 trailing-whitespace lines in those immutable raw logs. The
  scoped check over authored source and run-record metadata passes; the raw
  evidence was not normalized after capture.
- This partial result does not claim the overall M3 v2 threshold passed; 12 lanes
  remain pending and the earlier ANR baseline lane remains exhausted.

## Verification

The committed evidence contract is covered by
`test_committed_v2_query_progress_has_matched_auditable_attempts`. It checks all
attempt checksums, passing gates, exact Journey action lineage, event and
checkpoint contract, pre/post-event query values, baseline/defect L2 outcomes,
the partial aggregate snapshot, environment disclosure, and root checksum.

TDD red command:

```bash
.venv/bin/pytest -q \
  tests/bench/test_m3_reliability.py::test_committed_v2_query_progress_has_matched_auditable_attempts
# expected RED while README.md was absent; 1 failed at FileNotFoundError
```

Final verification before review:

```bash
/usr/bin/time -p .venv/bin/pytest -o addopts='' -q \
  tests/bench/test_m3_reliability.py \
  tests/bench/test_run_record_checksums.py \
  tests/bench/test_goldset_config_change_02_query_duplication.py \
  tests/bench/test_live_validation_gate.py \
  tests/runner/test_cli.py tests/runner/test_evidence.py \
  tests/runner/test_journey.py tests/runner/test_system_events.py
# 150 passed in 2.20s; real 2.37s

.venv/bin/python -m compileall -q src tests
# exit 0

/usr/bin/time -p .venv/bin/pytest -o addopts='' -q
# 416 passed in 7.97s; real 8.19s

.venv/bin/pytest -o addopts='' --collect-only -q
# 416 tests collected in 0.10s

git diff --cached --check -- \
  tests/bench/test_m3_reliability.py \
  docs/runs/2026-07-15-m3-v2-query-duplication-reliability/README.md \
  docs/runs/2026-07-15-m3-v2-query-duplication-reliability/environment.json \
  docs/runs/2026-07-15-m3-v2-query-duplication-reliability/plan-after-query-duplication.json \
  docs/runs/2026-07-15-m3-v2-query-duplication-reliability/progress.json
# exit 0

for attempt in \
  docs/runs/2026-07-15-m3-v2-query-duplication-reliability/lanes/*/attempt-*
do
  PYTHONPATH=src .venv/bin/python \
    -m aiverify.bench.run_record_checksums --verify "$attempt" || exit
done
# six attempt inventories verified

PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-15-m3-v2-query-duplication-reliability
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-15-m3-v2-query-duplication-reliability
# checksum inventory verified; 147 covered files
```

The test suite produced no warnings in this environment.

## Review

The required parallel Standards and Spec reviews used fixed point `97f0a7c` and
inspected the complete 149-file change.

- **Standards: PASS.** No documented-standard violations were found. The
  reviewer verified every checksum inventory, parsed all 85 JSON files, 198
  JSONL rows, the preference XML, and all 24 PNGs, and confirmed the recorded
  inventory and evidence-discipline fields. One non-blocking judgment call was
  recorded: the new query evidence test repeats some committed-run audit
  scaffolding from the adjacent oversized-state test. The explicit seed-local
  checks are retained because the oracle and evidence contracts differ; a
  shared abstraction would currently obscure the acceptance evidence.
- **Spec: PASS.** Zero missing, partial, incorrect, or out-of-scope behaviors
  were found. The reviewer independently checked the six fresh identities,
  one accountable attempt per lane, passing preflights, retry bound, matched
  contract, baseline/defect L2 outcomes, duplicated-query evidence, partial
  aggregate, build/deploy/restoration record, and all checksums.

Review summary: one non-blocking Standards judgment, zero Spec findings.

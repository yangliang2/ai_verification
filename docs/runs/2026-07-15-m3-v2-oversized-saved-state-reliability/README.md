# M3 v2 oversized saved-state reliability re-baseline

Date: 2026-07-15 (Asia/Shanghai)

Issue: `#53` (parent `#48`)

Manifest: `bench/goldset/m3-reliability-slice-v2.yaml`

Device: `medium_phone`, `emulator-5554`, Android 16 / API 36

## Result

All six fresh oversized saved-state lanes completed on their first attempt and
were accountable. All three baseline controls produced no L1 failure. All three
injected-defect repetitions failed L1 with `crash_stability` and retained the
expected `TransactionTooLargeException: data parcel size 2110592 bytes` signal.

| Metric | Result |
|---|---:|
| Fresh lanes executed | 6/6 |
| Formal attempts | 6 |
| First-attempt accountable | 6/6 |
| Eventual accountable | 6/6 |
| Retries | 0 |
| Baseline controls passed | 3/3 |
| Defects caught | 3/3 |
| Total formal attempt time | 715.361 s |
| Operational interventions | 0 |

The evidence-derived full-v2 partial aggregate in `progress.json` is 30 planned,
18 pending, 11 first-attempt/eventual accountable, 5 passed controls, 6 caught
defects, one retry, and two preflight-environment failures. It includes the
previous committed ANR slice and is not a final M3 claim.

## Lane evidence

| Lane / attempt | Exit | Accountability / result | Duration |
|---|---:|---|---:|
| `v2-oversized-state-baseline-1/attempt-1` | 0 | accountable; L1 inconclusive; control passed | 107.935 s |
| `v2-oversized-state-baseline-2/attempt-1` | 0 | accountable; L1 inconclusive; control passed | 110.757 s |
| `v2-oversized-state-baseline-3/attempt-1` | 0 | accountable; L1 inconclusive; control passed | 120.292 s |
| `v2-oversized-state-defect-1/attempt-1` | 1 | accountable; L1 `crash_stability`; caught | 118.741 s |
| `v2-oversized-state-defect-2/attempt-1` | 1 | accountable; L1 `crash_stability`; caught | 122.373 s |
| `v2-oversized-state-defect-3/attempt-1` | 1 | accountable; L1 `crash_stability`; caught | 135.263 s |

Every attempt retained a passing runner live-validation gate, two PASSED Journey
actions, a pre-event checkpoint, the `app_to_background` system event, and a
post-event checkpoint. No accountable outcome was retried.

## Matched contract

Baseline and defect lanes used the same host source tree, Run Spec, package,
launch activity, Journey actions, sentinel `zzoversize`, system event, target
state, and checkpoint observations. The only intentional difference was the
source patch in `SearchActivity.onSaveInstanceState()`.

Each verdict records:

- Journey segment `wikipedia-process-death-03-oversized-saved-state-segment-0`.
- Two action results, both `PASSED`.
- `injected_events=[{"event":"app_to_background","args":{}}]`.
- Checkpoints `after-segment-0` and `after-event-0`.
- L1 inconclusive with no failed oracle for baseline, versus L1 fail /
  `crash_stability` for defect.

## Exact build and deployment commands

From `/Users/80268204/hosts/wikipedia`, baseline:

```bash
mkdir -p aiverify-builds/m3-v2-oversized-state
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-v2-oversized-state/baseline-app-dev-debug.apk
shasum -a 256 \
  aiverify-builds/m3-v2-oversized-state/baseline-app-dev-debug.apk
stat -f '%z bytes' \
  aiverify-builds/m3-v2-oversized-state/baseline-app-dev-debug.apk
```

Result: `BUILD SUCCESSFUL in 22s`; 77 tasks (1 executed, 5 from cache,
71 up-to-date); real 22.52 s; 121,205,472 bytes; SHA-256
`b89edc28d16955bd9d9980090e217127863c2691eb4549c2151d2fb6f5632029`.

Defect injection and build:

```bash
git apply --check \
  /Users/80268204/Projects/ai_verification/bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
git apply \
  /Users/80268204/Projects/ai_verification/bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
sha256sum app/src/main/java/org/wikipedia/search/SearchActivity.kt
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-v2-oversized-state/defect-app-dev-debug.apk
shasum -a 256 \
  aiverify-builds/m3-v2-oversized-state/defect-app-dev-debug.apk
stat -f '%z bytes' \
  aiverify-builds/m3-v2-oversized-state/defect-app-dev-debug.apk
```

Result: patched source SHA-256 `e2fce1985c97688472876663c600c0b325d3104f91b9661d368096fadebd828b`;
`BUILD SUCCESSFUL in 29s`; 77 tasks (1 executed, 5 from cache,
71 up-to-date); real 29.77 s; 121,550,865 bytes; SHA-256
`c7270130e27a6109c28d12160e52bb353ecff27da7d317691c5f1b4494b3e119`.

Literal baseline and defect deployments used the corresponding absolute APK
path in these commands:

```bash
android run \
  --apks=/Users/80268204/hosts/wikipedia/aiverify-builds/m3-v2-oversized-state/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon

android run \
  --apks=/Users/80268204/hosts/wikipedia/aiverify-builds/m3-v2-oversized-state/defect-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Both returned `Installation completed successfully` and `Activation completed
successfully`. Before formal baseline and defect execution, the independent
five-check gate passed `adb-device-present`, `boot-completed`,
`boot-animation-stopped`, `android-layout-json`, and `uiautomator-dump`.

## Exact runner commands

Each invocation below also records its literal lane ID:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-oversized-state-baseline-1 --device emulator-5554 --workdir /Users/80268204/hosts/wikipedia --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-oversized-state-baseline-2 --device emulator-5554 --workdir /Users/80268204/hosts/wikipedia --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-oversized-state-baseline-3 --device emulator-5554 --workdir /Users/80268204/hosts/wikipedia --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-oversized-state-defect-1 --device emulator-5554 --workdir /Users/80268204/hosts/wikipedia --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-oversized-state-defect-2 --device emulator-5554 --workdir /Users/80268204/hosts/wikipedia --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability --manifest bench/goldset/m3-reliability-slice-v2.yaml run-lane v2-oversized-state-defect-3 --device emulator-5554 --workdir /Users/80268204/hosts/wikipedia --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python
```

Partial aggregate generation:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml plan \
  --json-output docs/runs/2026-07-15-m3-v2-oversized-saved-state-reliability/plan-after-oversized-state.json
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v2.yaml progress \
  --json-output docs/runs/2026-07-15-m3-v2-oversized-saved-state-reliability/progress.json
```

## Restoration

```bash
git apply -R --check \
  /Users/80268204/Projects/ai_verification/bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
git apply -R \
  /Users/80268204/Projects/ai_verification/bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
sha256sum app/src/main/java/org/wikipedia/search/SearchActivity.kt
android run \
  --apks=/Users/80268204/hosts/wikipedia/aiverify-builds/m3-v2-oversized-state/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

The restored source SHA-256 was
`51231dffe24dbab3861db9858cbf423312e3107582f46d3da148941f2de207bc`,
identical to the pre-injection baseline. The final baseline deployment again
reported successful installation and activation.

## Artifact inventory

- 6 attempt directories and 6 attempt checksum manifests.
- 6 attempt records, passing gates, verdicts, and stdout/stderr pairs.
- 6 Journey event streams, raw results, normalized results, and action lineage.
- 12 checkpoint capture sets: before and after the system event for every lane.
- Under `lanes/`: 132 files — 72 JSON, 6 JSONL, 24 PNG, 24 text/log, and
  6 checksum manifests.
- `plan-after-oversized-state.json`, `progress.json`, `environment.json`, this
  README, and the root checksum inventory.

The APKs remain external because they total about 243 MB. Absolute paths,
sizes, and hashes are retained in `environment.json`.

## Known gaps

- No physical-device, cross-host, or second-AVD validation was performed.
- L2 passed during these runs but is not the target oracle; L3 is outside this
  slice.
- The Wikipedia host is an extracted source tree without `.git`; restoration is
  verified by the exact source checksum.
- This run does not repair the ANR slice's exhausted baseline preflight lane;
  that failure remains visible in the combined partial aggregate.

## Verification

The committed evidence contract is covered by
`test_committed_v2_oversized_state_progress_has_matched_auditable_attempts`.
It verifies the partial aggregate, six one-attempt lanes, passing runner gates,
matched Journey/system-event/checkpoint contract, baseline oracle results,
defect classifications, raw oversized-state log evidence, and every checksum.

```bash
.venv/bin/pytest -q \
  tests/bench/test_m3_reliability.py \
  tests/bench/test_run_record_checksums.py \
  tests/bench/test_goldset_process_death_03_oversized_saved_state.py \
  tests/runner/test_cli.py tests/runner/test_journey.py \
  tests/runner/test_system_events.py
# 131 passed; /usr/bin/time real 11.49 s

.venv/bin/python -m compileall -q src tests
# exit 0

.venv/bin/pytest -q
# 415 passed, 2 warnings; /usr/bin/time real 12.61 s

.venv/bin/pytest --collect-only -q
# 415 tests collected

.venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-15-m3-v2-oversized-saved-state-reliability
.venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-15-m3-v2-oversized-saved-state-reliability --verify
# checksum inventory verified; 136 covered files
```

The two warnings are existing `DeprecationWarning`s from
`src/aiverify/agent/oracle/l2.py:123` about future XML element truth-value
behavior.

TDD evidence: the new oversized-state committed-evidence test first failed
because this README did not yet exist, then passed after the record and root
checksum were generated. The earlier ANR snapshot test was changed from an
equality check against live full-v2 progress to monotonic assertions, so adding
later slices does not invalidate the historical ANR partial snapshot.

The required Standards and Spec review uses fixed point
`12ee4a6e50bb5a39cbc1c3c24dcc1eead4f4d7ee`. Both axes passed with no findings.
The Standards reviewer independently verified all root/attempt checksums, raw
JSON and PNG artifacts, exact build/deploy/restoration claims, external APK
hashes, source restoration, focused/full tests, and historical evidence
immutability. The Spec reviewer checked every #53 acceptance criterion directly
against the manifest and retained attempt evidence. Raw logcat lines contain
device-originated trailing spaces; they remain untouched as checksum-covered raw
evidence rather than being reformatted.

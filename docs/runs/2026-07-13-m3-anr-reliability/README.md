# M3 ANR Verification Agent Reliability Run

Date: 2026-07-13 (Asia/Shanghai)

Issue: `#42`

Manifest: `bench/goldset/m3-reliability-slice.yaml`
Device: `medium_phone` AVD, serial `emulator-5554`, Android 16 / API 36

## Result

The bounded six-lane slice completed fail-closed. All three baseline controls were
accountable and produced no L1 failure. One of three injected-defect lanes was
accountable and L1 caught the expected `crash_stability` ANR. The other two defect
lanes exhausted their single allowed retry without becoming accountable.

| Metric | Result |
|---|---:|
| Planned lanes | 6 |
| First-attempt accountable | 4 |
| Eventual accountable | 4 |
| Retries | 2 |
| Baseline controls passed | 3/3 |
| Defects caught among planned defect lanes | 1/3 |
| Total attempt time | 1535.477 s |
| Recorded operational interventions | 4 |

This is not a benchmark-wide detection-rate or false-positive-rate claim. See
`summary.md` and `summary.json` for the evidence-derived aggregate.

## Lane evidence

| Lane / attempt | Exit | Accountability / result | Duration |
|---|---:|---|---:|
| `anr-baseline-1/attempt-1` | 0 | accountable; L1 inconclusive, control passed | 136.470 s |
| `anr-baseline-2/attempt-1` | 0 | accountable; L1 inconclusive, control passed | 180.579 s |
| `anr-baseline-3/attempt-1` | 0 | accountable; L1 inconclusive, control passed | 163.889 s |
| `anr-defect-1/attempt-1` | 2 | non-accountable; `live_validation_preflight_failed` | 67.045 s |
| `anr-defect-1/attempt-2` | 2 | non-accountable; `checkpoint_capture_error` | 511.766 s |
| `anr-defect-2/attempt-1` | 2 | non-accountable; `journey_action_failed` | 208.358 s |
| `anr-defect-2/attempt-2` | 2 | non-accountable; `journey_action_failed` | 145.750 s |
| `anr-defect-3/attempt-1` | 1 | accountable; L1 fail, `crash_stability` caught | 121.620 s |

The caught lane contains two system log lines for the ANR, including an input
dispatch timeout after 5001 ms and `ANR in org.wikipedia.dev`.

## Exact commands

Environment and pre-build checks:

```bash
/Users/80268204/.local/bin/android --version
/Users/80268204/Library/Android/sdk/platform-tools/adb version
/Users/80268204/.local/bin/android emulator list
.venv/bin/python -m aiverify.bench.live_validation_gate \
  --device emulator-5554 \
  --android-bin /Users/80268204/.local/bin/android \
  --adb-bin /Users/80268204/Library/Android/sdk/platform-tools/adb
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchFragment.kt
```

Build and install (run from `/Users/80268204/hosts/wikipedia`):

```bash
./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-anr/baseline-app-dev-debug.apk
/Users/80268204/.local/bin/android app install \
  --apk aiverify-builds/m3-anr/baseline-app-dev-debug.apk
git apply /Users/80268204/Projects/ai_verification/bench/goldset/patches/wikipedia-coroutine-concurrency-03-main-thread-anr.patch
./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-anr/defect-app-dev-debug.apk
/Users/80268204/.local/bin/android app install \
  --apk aiverify-builds/m3-anr/defect-app-dev-debug.apk
```

Public reliability runner (lane ID varied across the six lanes):

```bash
.venv/bin/python -m aiverify.bench.m3_reliability plan
.venv/bin/python -m aiverify.bench.m3_reliability run-lane <lane-id> \
  --device emulator-5554 \
  --workdir /Users/80268204/hosts/wikipedia \
  --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python \
  --intervention "<intervention, when one occurred>"
.venv/bin/python -m aiverify.bench.m3_reliability summary \
  --json-output docs/runs/2026-07-13-m3-anr-reliability/summary.json \
  --markdown-output docs/runs/2026-07-13-m3-anr-reliability/summary.md
```

Restoration and integrity:

```bash
git apply -R /Users/80268204/Projects/ai_verification/bench/goldset/patches/wikipedia-coroutine-concurrency-03-main-thread-anr.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchFragment.kt
.venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-anr-reliability
.venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-anr-reliability
```

Host verification commands are recorded after their final run in the
`Verification` section below.

## Important command results

- Baseline build: `BUILD SUCCESSFUL in 6m 11s`; 77 actionable tasks (13 executed,
  64 up-to-date).
- Defect build: `BUILD SUCCESSFUL in 57s`; 77 actionable tasks (5 executed,
  72 up-to-date).
- Installed package: `org.wikipedia.dev`, versionCode `50594`.
- Baseline source SHA-256 before injection and after restoration:
  `324c78af401539508bdbdba117a1b6cd0c7fc8a52189880eff0e1c7b9da88f1`.
- Baseline APK: 120998321 bytes, SHA-256
  `12e0705ce900bdbce3b653a6cdfe85d90b3b22d207b3c206981f808752d975a1`.
- Defect APK: 121343736 bytes, SHA-256
  `0770fe4d419003820ef642131c91259645c3b11a3c4cc5c57f6cb82cc8a30260`.
- Tool versions: Android CLI `1.0.15498356`; adb `1.0.41` / platform-tools
  `37.0.0-14910828`; Python `3.12.13`; pytest `9.1.1`; Temurin OpenJDK
  `17.0.19+10`.

The two APKs remain outside the repository at
`/Users/80268204/hosts/wikipedia/aiverify-builds/m3-anr/` because their combined
size is about 242 MB. Their exact sizes and hashes above make the external build
outputs auditable. All runner evidence is stored in this committed run directory.

## Artifact inventory

- 8 attempt records and 8 attempt-level checksum manifests.
- 8 runner verdicts, 8 live-validation gate reports, and runner stdout/stderr.
- 7 Codex Journey event streams and 7 structured Journey results.
- 7 checkpoint evidence sets where capture completed, including layout JSON,
  screenshots, annotated screenshots, logcat, command records, and capture manifests.
- 12 PNG screenshots, 52 JSON files, 22 text/log files, and 7 JSONL streams before
  adding this README and the root checksum manifest.
- `summary.json` and `summary.md`, derived only from checksum-verified attempt evidence.
- `checksums.sha256`, covering the complete committed run record.

## Operational interventions and known gaps

- Defect attempt 1 initially failed preflight because Android CLI layout and direct
  UIAutomator dump were unavailable. The emulator and adb server were recovered,
  and an explicit host-GPU cold start plus fresh passing gate preceded the retry.
- The defect-induced ANR can make layout observation unavailable during the exact
  window when the Journey needs it. One retry failed checkpoint capture; two attempts
  were classified `journey_action_failed`. These are reliability findings, not defect
  misses, and the aggregate remains fail-closed at 4/6 eventual accountability.
- Recovery screenshots captured under `/tmp` were diagnostic-only and did not survive
  to the final run-record assembly. The durable per-attempt screenshots and logs are
  retained under `lanes/`.
- The Wikipedia host is an extracted source tree without `.git`; source restoration
  was therefore verified by the exact baseline file checksum rather than `git status`.
- No physical-device or cross-host validation was performed. L2 is not applicable to
  this no-system-event seed; L3/multimodal behavior is outside this slice.

## Verification

Commands and results:

```bash
.venv/bin/pytest -q tests/bench/test_m3_reliability.py \
  tests/bench/test_run_record_checksums.py \
  tests/bench/test_goldset_coroutine_03_anr.py \
  tests/runner/test_cli.py tests/runner/test_journey.py
# 69 passed

.venv/bin/python -m compileall -q src tests
# exit 0

.venv/bin/pytest -q
# 360 passed, 2 warnings; 3.64 s command wall time

.venv/bin/pytest --collect-only
# 360 tests collected in 0.17 s

.venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-anr-reliability
.venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-anr-reliability
# checksum inventory verified; 103 covered files
```

The two warnings are existing `DeprecationWarning`s at
`src/aiverify/agent/oracle/l2.py:123` about future Element truth-value behavior.

The required two-axis review used fixed point
`cf864917cf472d94a8ba8ac69ec34863109dd540` and `git diff --cached HEAD`.
The Standards review found one hard evidence-completeness blocker and two design
judgement calls; the Spec review found one blocker, one high, and two medium
findings. Remediation added the root checksum and this verification record,
fail-closed validation for accountability/metric/timing/oracle contradictions and
unknown failure reasons, a shared verified-attempt loader, an invalid-lineage test,
and removal of a workstation-specific Run Spec path change. The 69-test targeted
run and 360-test full run above were performed after those fixes.

One earlier targeted command named the ANR test file
`tests/bench/test_goldset_coroutine_concurrency_03_anr.py`; pytest rejected that
nonexistent path before collecting tests. The corrected command shown above uses
`tests/bench/test_goldset_coroutine_03_anr.py` and passed.

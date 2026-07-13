# M3 Oversized Saved-State Reliability Run

Date: 2026-07-13 (Asia/Shanghai)

Issue: `#43`

Manifest: `bench/goldset/m3-reliability-slice.yaml`
Device: `medium_phone` AVD, serial `emulator-5554`, Android 16 / API 36

## Result

The six new oversized saved-state lanes completed fail-closed. All three baseline
controls were accountable on their first attempt and produced no L1 failure. All
three injected-defect lanes were eventually accountable and L1 caught the expected
`crash_stability` failure with `TransactionTooLargeException: data parcel size
2110592 bytes`. One defect lane needed its single allowed retry after a layout
preflight failure.

| Incremental #43 metric | Result |
|---|---:|
| Planned lanes | 6 |
| First-attempt accountable | 5 |
| Eventual accountable | 6 |
| Retries | 1 |
| Baseline controls passed | 3/3 |
| Defects caught | 3/3 |
| Total attempt time | 984.020 s |
| Recorded operational interventions | 1 |

The deterministic aggregate includes both versioned M3 seeds and is derived from
checksum-verified evidence, not hand-entered outcome counts:

| Current 12-lane partial aggregate | Result |
|---|---:|
| Planned lanes | 12 |
| First-attempt accountable | 9 |
| Eventual accountable | 10 |
| Retries | 3 |
| Baseline controls passed | 6/6 |
| Defects caught among planned lanes | 4/6 |
| Total attempt time | 2519.497 s |
| Recorded operational interventions | 5 |

This remains a bounded partial aggregate, not a benchmark-wide detection-rate,
false-positive-rate, or throughput claim. See `summary.md` and `summary.json`.

## Lane evidence

| Lane / attempt | Exit | Accountability / result | Duration |
|---|---:|---|---:|
| `oversized-state-baseline-1/attempt-1` | 0 | accountable; L1 inconclusive, control passed | 164.600 s |
| `oversized-state-baseline-2/attempt-1` | 0 | accountable; L1 inconclusive, control passed | 132.427 s |
| `oversized-state-baseline-3/attempt-1` | 0 | accountable; L1 inconclusive, control passed | 150.755 s |
| `oversized-state-defect-1/attempt-1` | 1 | accountable; L1 fail, `crash_stability` caught | 209.210 s |
| `oversized-state-defect-2/attempt-1` | 1 | accountable; L1 fail, `crash_stability` caught | 152.065 s |
| `oversized-state-defect-3/attempt-1` | 2 | non-accountable; `live_validation_preflight_failed` | 42.264 s |
| `oversized-state-defect-3/attempt-2` | 1 | accountable; L1 fail, `crash_stability` caught | 132.699 s |

No accountable outcome was retried. The first failed attempt remains in the lineage
and is included in timing and failure-class accounting.

## Exact commands

Environment, host, and build checks:

```bash
/Users/80268204/.local/bin/android --version
adb version
.venv/bin/python --version
.venv/bin/pytest --version
java -version
codex --version
git apply --check bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchActivity.kt
```

Build and deploy (build commands run from `/Users/80268204/hosts/wikipedia`):

```bash
./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-oversized-state/baseline-app-dev-debug.apk
/Users/80268204/.local/bin/android run \
  --apks=aiverify-builds/m3-oversized-state/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
git apply /Users/80268204/Projects/ai_verification/bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-oversized-state/defect-app-dev-debug.apk
/Users/80268204/.local/bin/android run \
  --apks=aiverify-builds/m3-oversized-state/defect-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Public reliability runner (lane ID varied across the six new lanes):

```bash
.venv/bin/python -m aiverify.bench.m3_reliability plan
.venv/bin/python -m aiverify.bench.m3_reliability run-lane <lane-id> \
  --device emulator-5554 \
  --workdir /Users/80268204/hosts/wikipedia \
  --python-executable /Users/80268204/Projects/ai_verification/.venv/bin/python \
  --intervention "<intervention, only when one occurred>"
.venv/bin/python -m aiverify.bench.m3_reliability summary \
  --json-output docs/runs/2026-07-13-m3-oversized-saved-state-reliability/summary.json \
  --markdown-output docs/runs/2026-07-13-m3-oversized-saved-state-reliability/summary.md
```

Restoration and integrity:

```bash
git apply -R /Users/80268204/Projects/ai_verification/bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchActivity.kt
.venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-oversized-saved-state-reliability
.venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-oversized-saved-state-reliability
```

Final repository verification commands and results are recorded in `Verification`.

## Important command results

- Baseline build: `BUILD SUCCESSFUL in 2m 13s`; 77 actionable tasks (1 executed,
  5 from cache, 71 up-to-date).
- Defect build: `BUILD SUCCESSFUL in 2m 7s`; 77 actionable tasks (5 executed,
  72 up-to-date).
- Installed package: `org.wikipedia.dev`; launch activity
  `org.wikipedia.DefaultIcon`.
- Baseline source SHA-256 before injection and after restoration:
  `51231dffe24dbab3861db9858cbf423312e3107582f46d3da148941f2de207bc`.
- Defect source SHA-256:
  `e2fce1985c97688472876663c600c0b325d3104f91b9661d368096fadebd828b`.
- Baseline APK: 121205472 bytes, SHA-256
  `b89edc28d16955bd9d9980090e217127863c2691eb4549c2151d2fb6f5632029`.
- Defect APK: 121550865 bytes, SHA-256
  `c7270130e27a6109c28d12160e52bb353ecff27da7d317691c5f1b4494b3e119`.
- Tool versions: Android CLI `1.0.15498356`; adb `1.0.41` / platform-tools
  `37.0.0-14910828`; emulator `36.5.11`; Python `3.12.13`; pytest `9.1.1`;
  OpenJDK `17.0.19+10`; Codex CLI `0.144.1`.

The two APKs remain outside the repository at
`/Users/80268204/hosts/wikipedia/aiverify-builds/m3-oversized-state/` because their
combined size is about 243 MB. Their exact sizes and hashes above make the external
build outputs auditable. All runner evidence is stored in this run directory.

## Artifact inventory

- 7 attempt records and 7 attempt-level checksum manifests.
- 7 runner verdicts, 7 live-validation gate reports, and runner stdout/stderr.
- 6 Codex Journey event streams and 6 structured Journey results.
- 6 complete checkpoint evidence sets with layouts, screenshots, annotated
  screenshots, logcat, command records, and capture manifests.
- 5 setup-only probes under `setup-probes/`, clearly separated from accountable
  live attempts: one launcher-readiness screenshot and layout plus three independent
  generic gate reports.
- 25 PNG screenshots, 68 JSON files, 26 text/log files, and 6 JSONL streams before
  adding this README and the root checksum manifest.
- `summary.json` and `summary.md`, derived only from checksum-verified attempt evidence.
- `checksums.sha256`, covering the complete committed run record.

## Operational interventions and known gaps

- `oversized-state-defect-3/attempt-1` failed the mandatory preflight because
  `android layout` did not return a usable hierarchy. The app was force-stopped and
  the device returned Home; a fresh independent five-check gate passed before the
  one allowed retry. The setup gate is retained under `setup-probes/`.
- The older ANR slice still has two defect lanes that exhausted their retry without
  becoming accountable. Therefore the current cross-seed aggregate remains
  fail-closed at 10/12 eventual accountability and 4/6 caught among planned defect
  lanes, even though this incremental slice completed 6/6 and caught 3/3 defects.
- L2 passed in the six accountable runs, but L2 is not the target oracle for this
  seed; the accountable success criteria are the baseline's lack of L1 failure and
  the defect's L1 `crash_stability` signal.
- The Wikipedia host is an extracted source tree without `.git`; exact source-file
  checksums verify restoration.
- No physical-device or cross-host validation was performed. L3/multimodal behavior
  is outside this slice.

## Verification

Commands and results:

```bash
.venv/bin/pytest -q tests/bench/test_m3_reliability.py \
  tests/bench/test_run_record_checksums.py \
  tests/bench/test_goldset_process_death_03_oversized_saved_state.py \
  tests/runner/test_cli.py tests/runner/test_journey.py \
  tests/runner/test_system_events.py
# 80 tests collected; all passed

.venv/bin/python -m compileall -q src tests
# exit 0

/usr/bin/time -p .venv/bin/pytest -q
# 361 passed, 2 warnings; real 4.40 s

.venv/bin/pytest --collect-only
# 361 tests collected in 0.18 s

.venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-oversized-saved-state-reliability
.venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-oversized-saved-state-reliability
# checksum inventory verified; 134 covered files
```

The two warnings are existing `DeprecationWarning`s at
`src/aiverify/agent/oracle/l2.py:123` about future Element truth-value behavior.

The required two-axis review used fixed point
`60f99c44a441bd17896eea2a43aa8d88c2dfe597` and
`git diff --cached 60f99c44a441bd17896eea2a43aa8d88c2dfe597`.
The Standards axis initially found two evidence-completeness violations: the root
checksum and final verification results were not yet present, and one stale
six-lane phrase remained in `HANDOFF.md`; this finalization fixes all three items.
It found no code-smell judgement calls in the substantive manifest/test changes.
The Spec axis found the same missing-root-checksum blocker and no other missing,
incorrect, or out-of-scope behavior. Generating and verifying the root manifest
below resolves that finding.

# M3 Query-Duplication L2 Reliability Run

Date: 2026-07-13 (America/New_York)

Issue: `#44`

Manifest: `bench/goldset/m3-reliability-slice.yaml`

Device: `aiverify_api35` AVD, serial `emulator-5554`, Android 15 / API 35,
model `sdk_gphone64_arm64`

## Result

The six query-duplication lanes completed under the M3 fail-closed contract. All
three baseline controls were accountable on their first attempt and passed L2.
All three injected-defect lanes were eventually accountable and failed L2 with
the expected `state_loss` class. Their post-configuration-change evidence records
`search_src_text=zzsentinelqxzzsentinelqx`, while the matched baseline retains
`search_src_text=zzsentinelqx`.

One defect lane used its single policy retry after the Verification Agent Backend
returned two skipped Journey actions. The first attempt remains non-accountable
and is retained in the lineage.

| Incremental #44 metric | Result |
|---|---:|
| Planned lanes | 6 |
| First-attempt accountable | 5 |
| Eventual accountable | 6 |
| Retries | 1 |
| Baseline controls passed | 3/3 |
| Defects caught at L2 / `state_loss` | 3/3 |
| Total attempt time | 675.945 s |
| Recorded operational interventions | 2 |

The deterministic partial aggregate now covers three M3 seeds:

| Current 18-lane partial aggregate | Result |
|---|---:|
| Planned lanes | 18 |
| First-attempt accountable | 14 |
| Eventual accountable | 16 |
| Retries | 4 |
| Baseline controls passed | 9/9 |
| Defects caught among planned lanes | 7/9 |
| Total attempt time | 3195.442 s |
| Recorded operational interventions | 7 |

The two lanes preventing full accountability remain the previously committed ANR
defect lanes. They are not converted into misses or silently removed.

## Lane evidence

| Lane / attempt | Exit | Accountability / result | Duration |
|---|---:|---|---:|
| `query-duplication-baseline-1/attempt-1` | 0 | accountable; L2 pass | 103.869 s |
| `query-duplication-baseline-2/attempt-1` | 0 | accountable; L2 pass | 123.570 s |
| `query-duplication-baseline-3/attempt-1` | 0 | accountable; L2 pass | 100.712 s |
| `query-duplication-defect-1/attempt-1` | 1 | accountable; L2 fail / `state_loss` | 83.348 s |
| `query-duplication-defect-2/attempt-1` | 2 | non-accountable; `journey_action_failed` | 41.126 s |
| `query-duplication-defect-2/attempt-2` | 1 | accountable; L2 fail / `state_loss` | 122.683 s |
| `query-duplication-defect-3/attempt-1` | 1 | accountable; L2 fail / `state_loss` | 100.637 s |

Every formal attempt persisted a passing runner-enforced live-validation gate.
No accountable outcome was retried.

## Exact commands

Environment and host checks:

```bash
android emulator start aiverify_api35
android --version
android info
adb devices -l
adb version
java -version
codex --version
.venv/bin/python --version
.venv/bin/pytest --version
git apply --check bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchFragment.kt
```

Build and deploy commands, run from `/Users/peter/hosts/wikipedia`:

```bash
./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-query-duplication/baseline-app-dev-debug.apk
android run \
  --apks=aiverify-builds/m3-query-duplication/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon

git apply /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch
./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-query-duplication/defect-app-dev-debug.apk
android run \
  --apks=aiverify-builds/m3-query-duplication/defect-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Before each lane, the device was force-stopped, cleared, returned to light mode,
given the committed `setup-probes/issue44-prefs.xml`, and launched through the
MAIN/LAUNCHER component. The exact setup commands were:

```bash
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push \
  docs/runs/2026-07-13-m3-query-duplication-reliability/setup-probes/issue44-prefs.xml \
  /data/local/tmp/issue44-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue44-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue44-prefs.xml shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER \
  -n org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --device=emulator-5554 --pretty
```

Public reliability runner, with the lane ID varied across the six lanes:

```bash
PYTHONPATH=/Users/peter/projects/ai_verfication/src \
  .venv/bin/python -m aiverify.bench.m3_reliability run-lane <lane-id> \
  --device emulator-5554 \
  --workdir /Users/peter/hosts/wikipedia \
  --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python

PYTHONPATH=/Users/peter/projects/ai_verfication/src \
  .venv/bin/python -m aiverify.bench.m3_reliability summary \
  --json-output docs/runs/2026-07-13-m3-query-duplication-reliability/summary.json \
  --markdown-output docs/runs/2026-07-13-m3-query-duplication-reliability/summary.md
```

The defect-2 retry additionally persisted an independent passing generic gate:

```bash
PYTHONPATH=/Users/peter/projects/ai_verfication/src \
  .venv/bin/python -m aiverify.bench.live_validation_gate \
  --device emulator-5554 \
  --output docs/runs/2026-07-13-m3-query-duplication-reliability/setup-probes/query-defect-2-retry-gate.json
```

Host restoration and evidence integrity:

```bash
git apply -R /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchFragment.kt
android run \
  --apks=aiverify-builds/m3-query-duplication/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-query-duplication-reliability
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-query-duplication-reliability
```

## Important command results

- Baseline build: `BUILD SUCCESSFUL in 41s`; 77 actionable tasks, 13 executed.
- Defect build: `BUILD SUCCESSFUL in 18s`; 77 actionable tasks, 5 executed.
- Package: `org.wikipedia.dev`; launcher activity: `org.wikipedia.DefaultIcon`.
- Baseline source SHA-256 before injection and after restoration:
  `324c78af401539508bdbdba117a1b6cd0c7fc8a52189880eff0e1c7b9da88f1f`.
- Defect source SHA-256:
  `1dffe5a728827e511f88efec672694e177aa85dc0454466248b11a12ccc37eb1`.
- Baseline APK: 120998321 bytes, SHA-256
  `12e0705ce900bdbce3b653a6cdfe85d90b3b22d207b3c206981f808752d975a1`.
- Defect APK: 121343694 bytes, SHA-256
  `320d0d1333fcc35405a845c4c768230bb44cf65700c3a5f2be6285e8ea24720e`.
- Patch SHA-256:
  `245232245da04a3cc011f78a699427e2c866735412b4d3ba60c5b20832ef8211`.
- Run Spec SHA-256:
  `feb9597a8acc61352da90fbb4993fe950a30819404c2072a9aeeca4f828c61fb`.
- Android CLI `1.0.15498356`; adb `1.0.41`, platform-tools
  `37.0.0-14910828`; Codex CLI `0.144.1`; OpenJDK `17.0.19`; Python
  `3.11.15`; pytest `9.0.3`.

The APKs remain outside the repository under
`/Users/peter/hosts/wikipedia/aiverify-builds/m3-query-duplication/` because their
combined size is about 242 MB. Their exact sizes and hashes are recorded above.

## Artifact inventory

- 7 formal attempt records and 7 attempt-level checksum manifests.
- 7 formal runner verdicts and 7 runner-enforced live-validation gate reports.
- 7 Codex Journey event streams and 7 structured Journey results.
- 6 accountable attempts with both pre-event and post-event checkpoint evidence.
- 1 non-accountable Journey attempt retaining its pre-event checkpoint evidence.
- 26 PNG screenshots, 71 JSON files, 29 text/log files, 7 JSONL streams, and
  the committed preferences XML before adding this README and the root manifest.
- `summary.json` and `summary.md`, generated from all checksum-verified M3 evidence.
- `setup-probes/query-defect-2-retry-ready-layout.json` and
  `setup-probes/query-defect-2-retry-gate.json` for the bounded retry decision.
- `setup-probes/discarded-runner-invocations/` preserves one pre-lane invocation
  that never launched the runner because a relative `PYTHONPATH` resolved under
  the host directory. It is excluded from lane lineage and benchmark accounting.
- `checksums.sha256` covers the complete committed run record and excludes itself.

## Operational interventions and known gaps

- Before baseline-1, a relative `PYTHONPATH=src` caused the orchestration child
  process to fail before runner startup. The diagnostic directory was moved out of
  lane evidence into `setup-probes/discarded-runner-invocations/`; the formal
  attempt used an absolute repository `PYTHONPATH`.
- `query-duplication-defect-2/attempt-1` returned two skipped Journey actions and
  was classified non-accountable. App state was reset and an independent five-check
  gate passed before the one allowed retry. The original attempt remains retained.
- The older ANR slice still has two defect lanes that exhausted their retry. The
  18-lane aggregate therefore remains fail-closed at 16/18 eventual accountability,
  even though #44 itself completed 6/6.
- The host is an extracted source tree without `.git` metadata. Source and APK
  checksums document injection and restoration.
- Validation used one API 35 emulator. No physical device, cross-host, ColorOS,
  fully unattended Journey, or visual-only/multimodal validation was performed.

## Verification

Commands and results:

```bash
.venv/bin/pytest -q tests/bench/test_m3_reliability.py \
  tests/bench/test_goldset_config_change_02_query_duplication.py
# 35 tests collected; all passed

.venv/bin/python -m compileall -q src tests
# exit 0

/usr/bin/time -p .venv/bin/pytest -q
# 362 tests collected; all passed; real 5.53 s

.venv/bin/pytest --collect-only -q | \
  awk -F': ' '/: [0-9]+$/ {sum += $2} END {print sum}'
# 362

git diff --cached --check -- HANDOFF.md \
  bench/goldset/m3-reliability-slice.yaml \
  tests/bench/test_m3_reliability.py \
  docs/runs/2026-07-13-m3-query-duplication-reliability/README.md \
  docs/runs/2026-07-13-m3-query-duplication-reliability/summary.json \
  docs/runs/2026-07-13-m3-query-duplication-reliability/summary.md
# exit 0, no output; immutable raw logcat captures retain device-provided spacing

PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-query-duplication-reliability
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-query-duplication-reliability
# checksum inventory verified; 144 covered files
```

The required two-axis review used fixed point `7dd1bbe` and the complete staged
diff. The Standards axis found no hard violations and no material judgement-call
smells. The Spec axis found no missing or partial requirements, scope creep, or
incorrect behavior. Both reviewers explicitly confirmed the bounded retry,
fail-closed aggregate, durable evidence, and checksum coverage.

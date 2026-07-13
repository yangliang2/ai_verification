# M3 Search-Card Semantic L3 Reliability Run

Date: 2026-07-13 (America/New_York)

Issue: `#46`

Manifest: `bench/goldset/m3-reliability-slice.yaml`

Device: `aiverify_api35` AVD, serial `emulator-5554`, Android 15 / API 35,
model `sdk_gphone64_arm64`

## Result

This increment added six new live Search-card semantic lanes to the M3
denominator. All three baseline controls completed on their first attempt and
passed L3 without a defect-class hypothesis. Defect repetitions 1 and 2 completed
on their first attempt and failed L3 as `ui_rendering`. Their layouts retain the
same selected Search tab and `search_card` structure while
`search_text_view`/`search_icon` contain reading-history copy.

Defect repetition 3 was non-accountable on both permitted attempts. In each case
the Verification Agent Backend performed the correct UI interaction but returned
a paraphrased action name instead of the exact requested action. The runner
therefore failed closed with `journey_action_incomplete` before L1/L2/L3. A fresh
independent passing gate preceded attempt 2. The lane exhausted the bounded retry
policy and was not retried again.

| Incremental #46 metric | Result |
|---|---:|
| Planned live lanes | 6 |
| First-attempt accountable | 5 |
| Eventual accountable | 5 |
| Retries | 1 |
| Baseline controls passed | 3/3 |
| Accountable defects caught at L3 / `ui_rendering` | 2/2 |
| Planned defects caught | 2/3 |
| Total formal attempt time | 500.755 s |
| L3 judge time across accountable lanes | 97.269 s |
| Recorded operational interventions | 1 |

The evidence-derived aggregate now covers the complete five-seed, 30-lane M3
inventory:

| Current 30-lane aggregate | Result |
|---|---:|
| Planned lanes | 30 |
| First-attempt accountable | 24 |
| Eventual accountable | 27 |
| Retries | 6 |
| Baseline controls passed | 15/15 |
| Defects caught among planned lanes | 12/15 |
| Total attempt time | 4605.338 s |
| Evidence-derived L3 judge time | 97.269 s |
| Recorded operational interventions | 9 |

The aggregate misses the parent PRD's eventual-accountability threshold of at
least 29/30. The three non-accountable planned lanes are two earlier ANR defects
and Search-card defect repetition 3. They remain execution-reliability failures,
not benchmark misses. Issue #47 must publish this threshold result without
converting those lanes into oracle outcomes.

The historical fixed-evidence package under
`docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/` remains separate context.
Its 10 judge-only calls are not referenced by any M3 lane and do not enter the
30-lane denominator.

## Lane evidence

| Lane / attempt | Runner exit | Accountability / result | Total | L3 judge |
|---|---:|---|---:|---:|
| `search-card-baseline-1/attempt-1` | 0 | accountable; L3 pass | 70.648 s | 22.595 s |
| `search-card-baseline-2/attempt-1` | 0 | accountable; L3 pass | 78.385 s | 17.384 s |
| `search-card-baseline-3/attempt-1` | 0 | accountable; L3 pass | 75.804 s | 18.033 s |
| `search-card-defect-1/attempt-1` | 1 | accountable; L3 fail / `ui_rendering` | 66.710 s | 20.995 s |
| `search-card-defect-2/attempt-1` | 1 | accountable; L3 fail / `ui_rendering` | 74.180 s | 18.262 s |
| `search-card-defect-3/attempt-1` | 2 | non-accountable; `journey_action_incomplete` | 77.429 s | not run |
| `search-card-defect-3/attempt-2` | 2 | non-accountable; `journey_action_incomplete` | 57.599 s | not run |

Every formal attempt persisted a passing five-check runner-enforced live-validation
gate. No accountable outcome was retried. Each accountable L3 call reports
confidence `0.99`.

## Exact commands

Environment and identity checks:

```bash
android --version
android info
android layout --help
android screen --help
adb devices -l
adb version
java -version
codex --version
.venv/bin/python --version
.venv/bin/pytest --version
git -C /Users/peter/hosts/wikipedia rev-parse HEAD
git -C /Users/peter/hosts/wikipedia status --short
shasum -a 256 \
  /Users/peter/hosts/wikipedia/app/src/main/java/org/wikipedia/history/HistoryFragment.kt
```

Baseline build, run from `/Users/peter/hosts/wikipedia`:

```bash
mkdir -p aiverify-builds/m3-search-card-l3
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-search-card-l3/baseline-app-dev-debug.apk
android run \
  --apks=aiverify-builds/m3-search-card-l3/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Defect build and deploy:

```bash
git apply \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
shasum -a 256 app/src/main/java/org/wikipedia/history/HistoryFragment.kt
/usr/bin/time -p ./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-search-card-l3/defect-app-dev-debug.apk
android run \
  --apks=aiverify-builds/m3-search-card-l3/defect-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Common device setup before each lane:

```bash
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push \
  docs/runs/2026-07-13-m3-search-card-l3-reliability/setup-probes/issue46-prefs.xml \
  /data/local/tmp/issue46-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue46-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue46-prefs.xml shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER \
  -n org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --device=emulator-5554 --pretty
```

Public reliability runner, varying the lane ID:

```bash
PYTHONPATH=/Users/peter/projects/ai_verfication/src \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.m3_reliability run-lane <lane-id> \
  --device emulator-5554 \
  --workdir /Users/peter/hosts/wikipedia \
  --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python
```

Retry eligibility and defect-3 attempt 2:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.live_validation_gate \
  --device emulator-5554 \
  --output docs/runs/2026-07-13-m3-search-card-l3-reliability/setup-probes/defect-3-retry-gate.json

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability run-lane \
  search-card-defect-3 \
  --device emulator-5554 \
  --workdir /Users/peter/hosts/wikipedia \
  --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python \
  --intervention "Reset app state after Journey paraphrased the requested action, confirmed a fresh independent passing gate, and used the single policy retry"
```

Aggregate, host restoration, and integrity:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability summary \
  --json-output docs/runs/2026-07-13-m3-search-card-l3-reliability/summary.json \
  --markdown-output docs/runs/2026-07-13-m3-search-card-l3-reliability/summary.md

git -C /Users/peter/hosts/wikipedia apply -R \
  /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
shasum -a 256 \
  /Users/peter/hosts/wikipedia/app/src/main/java/org/wikipedia/history/HistoryFragment.kt
android run \
  --apks=/Users/peter/hosts/wikipedia/aiverify-builds/m3-search-card-l3/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon

PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-search-card-l3-reliability
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-search-card-l3-reliability
```

## Important command results

- Host commit: `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`; host worktree
  clean before injection and after restoration.
- Package: `org.wikipedia.dev`; launcher activity: `org.wikipedia.DefaultIcon`.
- Baseline build: `BUILD SUCCESSFUL in 6s`; 77 actionable tasks, 1 executed,
  5 from cache, 71 up-to-date; wall time 6.50 s.
- Defect build: `BUILD SUCCESSFUL in 37s`; 77 actionable tasks, 5 executed,
  72 up-to-date; wall time 37.82 s. Two existing Room/KSP warnings were emitted.
- Baseline/restored `HistoryFragment.kt` SHA-256:
  `127aece4c11055cbed05ccc7c966def1bdf49e2ff610062aa433532715cd4b85`.
- Defect source SHA-256:
  `1a0594d748220fe70ce4475dbaf9720dca7982da844ef33c299bafaa6195d74b`.
- Baseline APK: 121199720 bytes, SHA-256
  `8e52dce057377b6f1bebb21128af4064c69f9717e5484d084724668bbe66d548`.
- Defect APK: 121062887 bytes, SHA-256
  `6711e911634b22e6ce6ccbed5b740b5f347589840c2741a565e028307c17ff8e`.
- Patch SHA-256:
  `e86d87aa66a3681e98446fd75247160d9fd785f556298fc072c6b2a7e690d35f`.
- Run Spec SHA-256:
  `18b50d7f70dd589ed38eabb2ed8da387cb26c3b82b9d5a7cb1b45d999342b19b`.
- Product spec SHA-256:
  `93005acf1336d21558d40c273dd7a6af7a3e1afc7ade2336043121786e68f217`.
- Android CLI `1.0.15498356`; adb `1.0.41`, platform-tools
  `37.0.0-14910828`; Codex CLI `0.144.1`; OpenJDK `17.0.19`; Python
  `3.11.15`; pytest `9.0.3`.

The external APKs remain under
`/Users/peter/hosts/wikipedia/aiverify-builds/m3-search-card-l3/` because their
combined size is about 242 MB. Exact sizes and hashes are recorded above.

## L3 judge evidence and leak discipline

Every accountable attempt preserves the exact `l3-judge-call-1.prompt.md`, the
final judge JSON in `l3-judge-call-1.md`, and the Codex event stream. The prompt
contains the L3 product specification and exact observed final layout. It does not
contain `scenario.expected_behavior`, the injected patch, or a frozen judge answer.
The M3 evidence loader now verifies this contract and fails closed on missing or
mismatched call lineage, missing spec/layout observations, expected-behavior/patch
leakage, a frozen answer embedded in the prompt, a final judge output that differs
from `verdict.json`, missing/invalid/duplicated L3 judge timing, or judge timing on
a non-accountable attempt. The aggregate derives the 97.269 s judge total only
from validated accountable runner timing phases.

The L3 judge received text-layout and screenshot references but did not perform a
multimodal image interpretation. This remains a text-layout semantic L3 measurement.

## Artifact inventory

- 7 formal attempt records and 7 attempt-level checksum manifests.
- 7 runner verdicts, 7 passing runner-enforced live-validation gates, stdout/stderr,
  Codex Journey event streams, and structured Journey results.
- 5 accountable attempts with final layouts, screenshots, annotated screenshots,
  logcat, command records, capture manifests, exact L3 prompts, judge outputs, and
  judge event streams.
- 2 exhausted non-accountable Journey attempts with checkpoint diagnostics but no
  oracle outcome.
- Before adding this README and the root manifest: 117 files comprising 51 JSON,
  21 text/log, 14 PNG, 12 JSONL, 11 Markdown, 7 attempt-level SHA-256 manifests,
  and the setup preferences XML.
- `setup-probes/defect-3-retry-gate.json` preserves the independent passing retry
  gate; `issue46-prefs.xml` preserves exact prompt-suppression preferences.
- `summary.json` and `summary.md` are generated from checksum-verified evidence.
- Root `checksums.sha256` covers 118 files and excludes itself.

## Operational interventions and known gaps

- Defect-3 attempt 1 returned a paraphrased action name even though it performed the
  requested tap and inspection. The runner correctly rejected this as
  `journey_action_incomplete` rather than accepting a semantically similar report.
- App state was reset and an independent five-check gate passed before the only
  retry. Attempt 2 repeated the same action-name mismatch and exhausted the lane.
- No accountable outcome was retried, and the exhausted lane was not converted into
  a miss or catch.
- This produces 27/30 eventual accountability, below the parent PRD's 29/30 target.
  The final #47 report must publish that failure alongside the zero observed false
  positives among accountable controls and consistent catches among accountable
  defects.
- Historical fixed-evidence L3 repeatability remains outside the live denominator.
- Validation used one API 35 emulator. No physical-device, cross-host, ColorOS,
  fully unattended Journey, or visual-only/multimodal validation was performed.

## Verification

Commands and results:

```bash
.venv/bin/pytest -q tests/bench/test_m3_reliability.py \
  tests/test_codex_cli_provider.py \
  tests/bench/test_goldset_ui_rendering_02_search_card_copy_mismatch.py
# 53 tests collected; all passed; real 0.37 s

.venv/bin/python -m compileall -q src tests
# exit 0

/usr/bin/time -p .venv/bin/pytest -q
# 374 tests collected; all passed; real 5.68 s

.venv/bin/pytest --collect-only -q | \
  awk -F': ' '/: [0-9]+$/ {sum += $2} END {print sum}'
# 374

git diff --cached --check -- HANDOFF.md \
  bench/goldset/m3-reliability-slice.yaml \
  src/aiverify/bench/m3_reliability.py \
  src/aiverify/providers/codex_cli.py \
  tests/bench/test_m3_reliability.py \
  tests/test_codex_cli_provider.py \
  docs/runs/2026-07-13-m3-search-card-l3-reliability/README.md \
  docs/runs/2026-07-13-m3-search-card-l3-reliability/summary.json \
  docs/runs/2026-07-13-m3-search-card-l3-reliability/summary.md
# exit 0; immutable raw logcat captures retain device-provided spacing

PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-search-card-l3-reliability
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-search-card-l3-reliability
# checksum inventory verified; 118 covered files
```

The required two-axis review used fixed point `5c1c1d1`. The first pass found
three audit gaps: judge call IDs were not cross-matched, final judge output was not
tied back to the runner verdict, and judge time was manually transcribed rather
than evidence-derived. It also found a stale host path in `HANDOFF.md`. The
implementation and regression tests above resolve all four findings. Standards
re-review additionally required non-accountable attempts to contribute zero judge
time and the provider artifact contract to name persisted prompts; both were fixed
and covered before the final no-findings review.

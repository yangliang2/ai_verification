# M3 Swallowed-Back L2 Reliability Run

Date: 2026-07-13 (America/New_York)

Issue: `#45`

Manifest: `bench/goldset/m3-reliability-slice.yaml`

Device: `aiverify_api35` AVD, serial `emulator-5554`, Android 15 / API 35,
model `sdk_gphone64_arm64`

## Result

The six swallowed-Back lanes completed under the M3 fail-closed contract. All
three baseline controls eventually returned to the Search-tab surface and passed
L2 with `search_card` present. All three injected-defect lanes eventually remained
on the unintended SearchActivity surface and failed L2 with the expected
`state_loss` class; their after-event layouts retain `search_src_text=zznavbackqx`
and do not contain `search_card`.

Defect-1 used its single policy retry. Its first attempt reported the expected
swallowed-Back behavior as a Journey failure because the action text prematurely
asserted the destination. The Run Spec was corrected so the Journey executes the
two Back commands and stops at an observation point, while L2 alone owns the
`search_card` assertion. The original defect attempt remains non-accountable.

Code review then found that the three initially accountable baseline packages
still embedded the older destination-asserting Journey text, so they were not a
matched comparison with the corrected defect Journeys. Those packages were
invalidated as a protocol mismatch before publication and moved intact under
`superseded-protocol-evidence/`. They are excluded from formal M3 accounting and
retained only for audit. Fresh formal baseline attempt-1 packages use the same
observation-neutral action and terminal Back-command boundary as the defects.

| Incremental #45 metric | Result |
|---|---:|
| Planned lanes | 6 |
| First-attempt accountable | 5 |
| Eventual accountable | 6 |
| Retries | 1 |
| Baseline controls passed | 3/3 |
| Defects caught at L2 / `state_loss` | 3/3 |
| Total attempt time | 909.141 s |
| Recorded operational interventions | 1 |

The evidence-derived partial aggregate now covers four M3 seeds:

| Current 24-lane partial aggregate | Result |
|---|---:|
| Planned lanes | 24 |
| First-attempt accountable | 19 |
| Eventual accountable | 22 |
| Retries | 5 |
| Baseline controls passed | 12/12 |
| Defects caught among planned lanes | 10/12 |
| Total attempt time | 4104.583 s |
| Recorded operational interventions | 8 |

The two lanes preventing full accountability remain the previously committed ANR
defect lanes. They remain non-accountable rather than being counted as misses.

## Lane evidence

| Lane / attempt | Exit | Accountability / result | Duration |
|---|---:|---|---:|
| `swallowed-back-baseline-1/attempt-1` | 0 | accountable; L2 pass | 123.747 s |
| `swallowed-back-baseline-2/attempt-1` | 0 | accountable; L2 pass | 116.432 s |
| `swallowed-back-baseline-3/attempt-1` | 0 | accountable; L2 pass | 111.560 s |
| `swallowed-back-defect-1/attempt-1` | 2 | non-accountable; `journey_action_failed` | 118.625 s |
| `swallowed-back-defect-1/attempt-2` | 1 | accountable; L2 fail / `state_loss` | 125.043 s |
| `swallowed-back-defect-2/attempt-1` | 1 | accountable; L2 fail / `state_loss` | 171.034 s |
| `swallowed-back-defect-3/attempt-1` | 1 | accountable; L2 fail / `state_loss` | 142.700 s |

Every formal attempt persisted a passing runner-enforced gate. No accountable
formal outcome was retried. The four invalidated baseline packages predate the
matched-protocol correction and are not attempts in the formal lane lineage.

## Exact commands

Environment and host checks:

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
git apply --check bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchActivity.kt
```

Build and deploy commands, run from `/Users/peter/hosts/wikipedia`:

```bash
./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-swallowed-back/baseline-app-dev-debug.apk
android run --apks=aiverify-builds/m3-swallowed-back/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon

git apply /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
./gradlew assembleDevDebug --no-daemon
cp app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  aiverify-builds/m3-swallowed-back/defect-app-dev-debug.apk
android run --apks=aiverify-builds/m3-swallowed-back/defect-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
```

Common device setup before each lane:

```bash
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push \
  docs/runs/2026-07-13-m3-swallowed-back-reliability/setup-probes/issue45-prefs.xml \
  /data/local/tmp/issue45-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue45-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue45-prefs.xml shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER \
  -n org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --device=emulator-5554 --pretty
```

Public reliability runner, varying the lane ID:

```bash
PYTHONPATH=/Users/peter/projects/ai_verfication/src \
  .venv/bin/python -m aiverify.bench.m3_reliability run-lane <lane-id> \
  --device emulator-5554 \
  --workdir /Users/peter/hosts/wikipedia \
  --python-executable /Users/peter/projects/ai_verfication/.venv/bin/python

PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability summary \
  --json-output docs/runs/2026-07-13-m3-swallowed-back-reliability/summary.json \
  --markdown-output docs/runs/2026-07-13-m3-swallowed-back-reliability/summary.md
```

Retry eligibility was established through independent gate commands such as:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.live_validation_gate \
  --device emulator-5554 \
  --output docs/runs/2026-07-13-m3-swallowed-back-reliability/setup-probes/defect-1-retry-gate.json
```

Host restoration and integrity:

```bash
git apply -R /Users/peter/projects/ai_verfication/bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
shasum -a 256 app/src/main/java/org/wikipedia/search/SearchActivity.kt
android run --apks=aiverify-builds/m3-swallowed-back/baseline-app-dev-debug.apk \
  --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-swallowed-back-reliability
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-swallowed-back-reliability
```

## Important command results

- Baseline build: `BUILD SUCCESSFUL in 6s`; 77 actionable tasks, 1 executed and
  5 from cache.
- Defect build: `BUILD SUCCESSFUL in 51s`; 77 actionable tasks, 5 executed.
- Package: `org.wikipedia.dev`; launcher activity: `org.wikipedia.DefaultIcon`.
- Baseline source SHA-256 before injection and after restoration:
  `51231dffe24dbab3861db9858cbf423312e3107582f46d3da148941f2de207bc`.
- Defect source SHA-256:
  `751496c19d885c257984b3072acd61ce83d6a9a67c693fb2678e4351593ef8a6`.
- Baseline APK: 121205472 bytes, SHA-256
  `b89edc28d16955bd9d9980090e217127863c2691eb4549c2151d2fb6f5632029`.
- Defect APK: 121550738 bytes, SHA-256
  `5637601bee59c393a6282ed6a1012a7ea6d0ee2e1230afdf87cdfec9023ba017`.
- Patch SHA-256:
  `a77e846712252ccf5e3d9db5005e82e0b257512b9d540db0bb54d9a017589897`.
- Run Spec SHA-256 after observation-boundary correction:
  `898833ba843069cc4bc637c00a016929bbc055388e91045faf802686393c705f`.
- Android CLI `1.0.15498356`; adb `1.0.41`, platform-tools
  `37.0.0-14910828`; Codex CLI `0.144.1`; OpenJDK `17.0.19`; Python
  `3.11.15`; pytest `9.0.3`.

The external APKs remain under
`/Users/peter/hosts/wikipedia/aiverify-builds/m3-swallowed-back/` because their
combined size is about 243 MB. Their exact sizes and hashes are recorded above.

## Artifact inventory

- 7 formal attempt records and 7 attempt-level checksum manifests.
- 7 runner verdicts, 7 runner-enforced live-validation gates, stdout/stderr,
  Codex event streams, and structured Journey results.
- 6 accountable attempts with before/after boundary layouts, screenshots,
  annotated screenshots, logcat, command records, and capture manifests.
- 1 non-accountable Journey attempt retaining diagnostic checkpoint evidence.
- Four invalidated baseline packages are retained intact under
  `superseded-protocol-evidence/`: 74 files including their four attempt-level
  checksum manifests, 14 PNGs, 37 JSON files, 15 text/log files, and 4 JSONL
  streams.
- Across formal, superseded, setup, and summary evidence: 40 PNG screenshots,
  111 JSON files, 42 text/log files, 11 JSONL streams, and the preferences XML
  before adding this README and checksum manifests.
- Seven setup probes retain the transient null-root layout, failed/recovered gates,
  retry layouts, passing gates, and the exact prompt preferences.
- `summary.json` and `summary.md`, generated from checksum-verified M3 evidence.
- `checksums.sha256` covers the complete committed run record and excludes itself.

## Operational interventions and known gaps

- Before baseline-2, Android CLI returned one transient null-root layout. A later
  layout and five-check gate passed before formal attempt-1; the anomaly and
  recovery are retained under `setup-probes/`.
- The initial baseline-2 package returned two skipped actions. App state was
  reset; one setup gate still failed null-root, then a subsequent independent
  gate passed before the old protocol's retry. Both old baseline-2 packages now
  live only under `superseded-protocol-evidence/` and do not enter formal counts.
- Defect-1 attempt-1 showed the correct product defect but was non-accountable
  because the Journey action itself asserted the expected destination. The action
  was made observation-neutral so execution and L2 accounting remain separate;
  a fresh passing gate preceded the only retry.
- Although the invalidated baseline packages executed the same two Back commands,
  code review correctly treated their destination-asserting Journey text as a
  protocol mismatch that could censor a control failure. The formal baselines
  were therefore rebuilt with the observation-neutral action; regression tests
  now compare every final Journey action and terminal command to that Run Spec.
- The older ANR slice still has two defect lanes that exhausted their retry. The
  24-lane aggregate remains fail-closed at 22/24 eventual accountability even
  though #45 itself completed 6/6.
- Validation used one API 35 emulator. No physical-device, cross-host, ColorOS,
  fully unattended Journey, or visual-only/multimodal validation was performed.
- The host is an extracted source tree without `.git`; source/APK hashes document
  injection and restoration.

## Verification

Commands and results:

```bash
.venv/bin/pytest -q tests/bench/test_m3_reliability.py \
  tests/bench/test_goldset_navigation_02_back_button_swallowed.py
# 36 tests collected; all passed

.venv/bin/python -m compileall -q src tests
# exit 0

/usr/bin/time -p .venv/bin/pytest -q
# 363 tests collected; all passed; real 5.15 s

.venv/bin/pytest --collect-only -q | \
  awk -F': ' '/: [0-9]+$/ {sum += $2} END {print sum}'
# 363

git diff --cached --check -- HANDOFF.md \
  bench/goldset/m3-reliability-slice.yaml \
  bench/goldset/run-specs/wikipedia-navigation-02-back-button-swallowed.yaml \
  tests/bench/test_m3_reliability.py \
  tests/bench/test_goldset_navigation_02_back_button_swallowed.py \
  docs/runs/2026-07-13-m3-swallowed-back-reliability/README.md \
  docs/runs/2026-07-13-m3-swallowed-back-reliability/summary.json \
  docs/runs/2026-07-13-m3-swallowed-back-reliability/summary.md
# exit 0; immutable raw logcat captures retain device-provided spacing

PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-13-m3-swallowed-back-reliability
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-13-m3-swallowed-back-reliability
# checksum inventory verified; 218 covered files
```

The required two-axis review used fixed point `da8953c` and the complete staged
diff. Standards review found a stale HANDOFF test count and formatting-dependent
raw-string layout assertions; the count was corrected to 363 and the regression
now parses structured layout nodes. Spec review found that the initial baselines
used the old destination-asserting Journey while the defects used the corrected
neutral one. Those packages were excluded and retained under
`superseded-protocol-evidence/`; all three formal baselines were rerun with the
matched neutral protocol. Both review findings were resolved before commit.

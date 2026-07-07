# 2026-07-07 Wikipedia config-change query-duplication Run Record

Primary issue: [#15](https://github.com/yangliang2/ai_verification/issues/15)
— M2 config-change duplicated-state Goldset seed.

Parent milestone: [#13](https://github.com/yangliang2/ai_verification/issues/13).

## What This Proves

This run adds a real-world duplicated/over-restored state pattern to the Goldset.
The host surface is Wikipedia Android `SearchActivity` / `SearchFragment`, exposed
in Android CLI layout as `resource-id="search_src_text"`.

Matched pair, same app, same scenario, same `dark_mode` (`uiMode`) config-change
boundary:

| half | L1 | L2 | `search_src_text` before -> after | runner exit | runner time |
|---|---|---|---|---:|---:|
| baseline | inconclusive | pass | `zzsentinelqx` -> `zzsentinelqx` | 0 | 322s |
| defect | inconclusive | fail / `state_loss` | `zzsentinelqx` -> `zzsentinelqxzzsentinelqx` | 1 | 171s |

The current L2 schema still reports this as `state_loss`, but the defect evidence
records the important duplicated actual value:

`resource-id='search_src_text' attr='text': expected='zzsentinelqx', actual='zzsentinelqxzzsentinelqx'`

## Source Pattern

The real-world source pattern is `bench/goldset/candidates.md` C3:
Thunderbird/K-9 recipient text duplicated after configuration change, fixed by
replacing restored recipient text rather than appending it.

This seed maps that pattern onto Wikipedia SearchView query restore: the query is
present before the config change, and the injected post-restore hook appends the
restored query to itself after `uiMode` recreation.

## Scenario

1. Preseed host prompt prefs after `pm clear`.
2. Start `org.wikipedia.dev` via launcher alias `org.wikipedia.DefaultIcon`.
3. Tap Search tab, tap `search_card`.
4. Type sentinel `zzsentinelqx` into `search_src_text`.
5. Press system Back once to hide the soft keyboard while staying in SearchActivity.
6. Runner captures `after-segment-0`.
7. Runner injects `dark_mode` with `night=yes`.
8. Runner captures `after-event-0`.
9. L2 asserts `search_src_text.text == "zzsentinelqx"`.

Run preseeded default shared prefs:

```xml
<map>
    <boolean name="initialOnboardingEnabled" value="false" />
    <boolean name="exploreFeedUpdatePromptShown" value="true" />
    <boolean name="yearInReviewVisited" value="true" />
    <boolean name="isYearInReviewEnabled" value="false" />
    <boolean name="searchWidgetInstallPromptShown" value="true" />
</map>
```

## Commands

Baseline rebuild after restoring the host:

```bash
patch -R -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
```

Defect build:

```bash
patch --dry-run -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch
patch -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
```

Common device setup before each runner invocation:

```bash
adb -s emulator-5554 install -r /Users/80268204/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push /tmp/issue15-prefs.xml /data/local/tmp/issue15-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue15-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue15-prefs.xml shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER -n org.wikipedia.dev/org.wikipedia.DefaultIcon
```

Runner commands:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-config-change-02-query-duplication.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/2026-07-07-wikipedia-config-change-02-query-duplication/baseline/artifacts \
  --no-launch

PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-config-change-02-query-duplication.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/2026-07-07-wikipedia-config-change-02-query-duplication/defect/artifacts \
  --no-launch
```

## Results

Valid baseline:

- `baseline/runner-exit.txt`: `exit_status=0`, `duration_seconds=322`
- `baseline/verdict.json`: L1 inconclusive, L2 pass
- `baseline/artifacts/after-segment-0/layout.json`: `search_src_text=zzsentinelqx`
- `baseline/artifacts/after-event-0/layout.json`: `search_src_text=zzsentinelqx`

Valid defect:

- `defect/build-exit.txt`: `exit_status=0`, `duration_seconds=50`
- `defect/runner-exit.txt`: `exit_status=1`, `duration_seconds=171`
- `defect/verdict.json`: L1 inconclusive, L2 fail / `state_loss`
- `defect/artifacts/after-segment-0/layout.json`: `search_src_text=zzsentinelqx`
- `defect/artifacts/after-event-0/layout.json`: `search_src_text=zzsentinelqxzzsentinelqx`

Host was restored after the defect run:

- `baseline-rebuild/build-exit.txt`: `exit_status=0`, `duration_seconds=42`
- `baseline-rebuild/apk.sha256`: same checksum as `baseline/apk.sha256`

## Environment

- Host: `/Users/80268204/hosts/wikipedia`, tarball checkout of Wikimedia Android
  app commit `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- Package: `org.wikipedia.dev`
- Launcher alias: `org.wikipedia.DefaultIcon`
- APK path: `/Users/80268204/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk`
- Baseline APK SHA-256: `a5a5265b65c234ed05c84e4cd28fb319054d88fb19fd0bee54cf1e96ce6d472f`
- Defect APK SHA-256: `dbce90ccfbb7bff6c5cd2e4e647f767adecf9901ba0af136a8cede8bc4424edd`
- Patch SHA-256: `245232245da04a3cc011f78a699427e2c866735412b4d3ba60c5b20832ef8211`
- Run spec SHA-256: `30266cab97563ec874b6faa5c57ec8f0e0559c99a5cf1510458abcb792e8ac6a`
- Seed spec SHA-256: `2522ce3ffec7494ab3a946def553463c5e61bae19b0a507f23bca86689933c35`
- Baseline verdict SHA-256: `f7f2e25e032140c50b93873721e3ebcf10eade10cfdae5df46c72639b005fa0d`
- Defect verdict SHA-256: `1cfebb6dd785bea214d4e7dbe6f2d0b11cc0d2e1f9a7515a76bcdf5ebc7eb50b`
- Device: `emulator-5554`, AVD `medium_phone`, `sdk_gphone64_arm64`,
  Android 16 / API 36
- Android CLI: `1.0.15498356`
- adb: `1.0.41`, platform-tools `37.0.0-14910828`
- Codex CLI: `0.142.5`
- Python: `3.12.13`
- pytest: `9.1.1`

## Implementation Mapping

- Seed spec:
  `bench/goldset/specs/wikipedia-config-change-02-query-duplication.md`
- Run spec:
  `bench/goldset/run-specs/wikipedia-config-change-02-query-duplication.yaml`
- Defect patch:
  `bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch`
- Frozen live fixtures:
  `bench/goldset/fixtures/wikipedia-config-change-02-query-duplication/{control,defect}-{before,after}-layout.json`
- Regression test:
  `tests/bench/test_goldset_config_change_02_query_duplication.py`
- Runner hardening surfaced by this run:
  `src/aiverify/runner/evidence.py` retries transient empty Android CLI layout
  dumps and bounds screenshot/logcat capture with timeouts.
- Evidence unit tests:
  `tests/runner/test_evidence.py`

## Artifact Inventory

- `baseline/verdict.json`, `defect/verdict.json` — final valid verdicts
- `{baseline,defect}/artifacts/after-segment-0/` — pre-event checkpoint:
  `layout.json`, `screen.png`, `screen-annotated.png`, `logcat.txt`,
  `commands.json`
- `{baseline,defect}/artifacts/after-event-0/` — post-`dark_mode` checkpoint:
  same shape
- `{baseline,defect}/artifacts/wikipedia-config-change-02-query-duplication-segment-0/`
  — Codex JSONL events and structured journey result
- `baseline/apk.sha256`, `defect/apk.sha256`, `baseline-rebuild/apk.sha256`
- `checksums.sha256` — SHA-256 for all 135 evidence files in this run record

Discarded attempts kept for audit:

- `baseline-attempt-l1-anr/`: L2 pass but L1 fail from SearchActivity ANR while
  the soft keyboard/focus path was still active. The scenario now presses Back
  before the config-change boundary.
- `baseline-attempt-driver-tooling/`: Codex driver returned a schema-valid
  FAILED/SKIPPED result without executing shell commands; not used as evidence.
- `defect-attempt-launcher/`: prelaunch readiness matched launcher "Search"
  instead of app `nav_tab_search`; not used as evidence. The valid rerun used a
  stricter resource-id based readiness condition.

## Known Gaps

- The emulator is API 36 (`medium_phone`), not the earlier API 35 AVD used for
  some M1 runs.
- `SearchActivity` dark-mode recreation can be slow on this host. The valid
  baseline after-event checkpoint took 46.541s; the valid defect after-event
  checkpoint took 21.210s.
- Android CLI layout capture intermittently returns empty stdout with
  `ERROR: null root node returned by UiTestAutomationBridge`; evidence capture now
  retries those transient dumps.

# 2026-07-08 Wikipedia ui-rendering-02 search card copy mismatch Run Record

Primary issue: [#17](https://github.com/yangliang2/ai_verification/issues/17)
- M2 second L3 semantic Goldset seed.

Parent scoping issue: [#13](https://github.com/yangliang2/ai_verification/issues/13).

## What This Proves

This run adds a second L3 text-layout semantic seed. The host surface is the
Wikipedia bottom Search tab's `search_card`.

Matched pair, same app, same event-less scenario:

| half | L1 | L2 | L3 | search card copy | runner exit | runner time |
|---|---|---|---|---|---:|---:|
| baseline | inconclusive | inconclusive / n/a | pass | `Search Wikipedia` | 0 | 68s |
| defect | inconclusive | inconclusive / n/a | fail / `ui_rendering` | `Track what you've been reading here.` | 1 | 83s |

The defect preserves the same `search_card`, `search_text_view`, and `search_icon`
nodes. Only the rendered copy is wrong, so L1/L2 are intentionally not useful and L3
must compare observed UI text against `scenario.l3_spec`.

## Scenario

1. Preseed host prompt prefs after `pm clear`.
2. Start `org.wikipedia.dev` via launcher alias `org.wikipedia.DefaultIcon`.
3. Runner taps bottom `nav_tab_search`.
4. Runner stops on the Search tab and confirms `search_card` is visible.
5. Runner captures `after-segment-0`.
6. L3 judge evaluates the final layout against the product spec.

Run preseeded default shared prefs:

```xml
<map>
    <boolean name="initialOnboardingEnabled" value="false" />
    <boolean name="exploreFeedUpdatePromptShown" value="true" />
    <boolean name="yearInReviewVisited" value="true" />
    <boolean name="isYearInReviewEnabled" value="false" />
    <boolean name="searchWidgetInstallPromptShown" value="true" />
    <boolean name="hybridSearchOnboardingShown" value="true" />
</map>
```

## Commands

Baseline build:

```bash
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
```

Baseline device setup:

```bash
adb -s emulator-5554 install -r /Users/80268204/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push /tmp/issue17-prefs.xml /data/local/tmp/issue17-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue17-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue17-prefs.xml shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER -n org.wikipedia.dev/org.wikipedia.DefaultIcon
```

Baseline runner:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-ui-rendering-02-search-card-copy-mismatch.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/baseline/artifacts \
  --no-launch
```

Defect build:

```bash
patch --dry-run -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
patch -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
```

Defect runner:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-ui-rendering-02-search-card-copy-mismatch.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/defect/artifacts \
  --no-launch
```

Host restore:

```bash
patch -R -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
git hash-object /Users/80268204/hosts/wikipedia/app/src/main/java/org/wikipedia/history/HistoryFragment.kt
patch --dry-run -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch
```

## Results

Valid baseline:

- `baseline/build-exit.txt`: `exit_status=0`, `duration_seconds=12`
- Gradle: `BUILD SUCCESSFUL in 12s`, 77 tasks up-to-date
- `baseline/runner-exit.txt`: `exit_status=0`, `duration_seconds=68`
- `baseline/verdict.json`: L1 inconclusive, L2 inconclusive / not applicable, L3 pass
- `baseline/artifacts/after-segment-0/layout.json`: `nav_tab_search` selected,
  `search_card` visible, `search_text_view=Search Wikipedia`, `search_icon`
  content description `Search Wikipedia`

Valid defect:

- `defect/build-exit.txt`: `exit_status=0`, `duration_seconds=111`
- Gradle: `BUILD SUCCESSFUL in 1m 49s`, 77 tasks: 5 executed, 72 up-to-date
- `defect/runner-exit.txt`: `exit_status=1`, `duration_seconds=83`
- `defect/verdict.json`: L1 inconclusive, L2 inconclusive / not applicable,
  L3 fail / `ui_rendering`
- `defect/artifacts/after-segment-0/layout.json`: `nav_tab_search` selected,
  `search_card` visible, `search_text_view=Track what you've been reading here.`,
  `search_icon` content description `Track what you've been reading here.`

Host restore:

- `baseline-rebuild/build-exit.txt`: `exit_status=0`, `duration_seconds=65`
- Gradle: `BUILD SUCCESSFUL in 1m 5s`, 77 tasks: 1 executed, 5 from cache, 71 up-to-date
- Restored `HistoryFragment.kt` git blob hash:
  `74784e065ea3882e5364fd500a8e7eafc0a60c41`
- `patch --dry-run` for the defect patch succeeds after restore.

## Environment

- Host: `/Users/80268204/hosts/wikipedia`, Wikimedia Android commit
  `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- Package: `org.wikipedia.dev`
- Launcher alias: `org.wikipedia.DefaultIcon`
- APK path: `/Users/80268204/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk`
- Baseline APK SHA-256: `9ea99071db203dae64fd371ad6d904183b6d705e1059f29998f8bbda62cdf75a`
- Defect APK SHA-256: `855fecca1d94683deae25d4fb4620ef041b7e2faa06e600f7b5c2477be355e3f`
- Baseline-rebuild APK SHA-256: `feddcf5e29f5182bfc5c58ec42472358332d6a4e72b362ff397c51c56a445d3b`
- Device: `emulator-5554`, AVD `medium_phone`, `sdk_gphone64_arm64`,
  Android 16 / API 36
- Android CLI: `1.0.15498356`
- adb: `1.0.41`, platform-tools `37.0.0-14910828`
- Codex CLI: `0.142.5`
- Python: `3.12.13`
- pytest: `9.1.1`

## Implementation Mapping

- Seed spec:
  `bench/goldset/specs/wikipedia-ui-rendering-02-search-card-copy-mismatch.md`
- Run spec:
  `bench/goldset/run-specs/wikipedia-ui-rendering-02-search-card-copy-mismatch.yaml`
- Defect patch:
  `bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch`
- Frozen live fixtures:
  `bench/goldset/fixtures/wikipedia-ui-rendering-02-search-card-copy-mismatch/{baseline,defect}-final-layout.json`
  and `{baseline,defect}-l3-response.md`
- Regression test:
  `tests/bench/test_goldset_ui_rendering_02_search_card_copy_mismatch.py`

## Artifact Inventory

- `baseline/verdict.json`, `defect/verdict.json` - final valid verdicts
- `{baseline,defect}/artifacts/after-segment-0/` - final checkpoint:
  `layout.json`, `screen.png`, `screen-annotated.png`, `logcat.txt`, `commands.json`
- `{baseline,defect}/artifacts/l3-judge/` - Codex CLI L3 judge response and event stream
- `{baseline,defect}/artifacts/wikipedia-ui-rendering-02-search-card-copy-mismatch-segment-0/`
  - Codex JSONL events and structured journey result
- `{baseline,defect,baseline-rebuild}/apk.sha256`
- Build logs, runner stdout/stderr, setup command outputs, prelaunch layouts
- `checksums.sha256` - SHA-256 manifest covering 109 evidence files in this run record

Discarded probing attempt retained for audit:

- `discarded-searchactivity-empty-state-attempt/`: initial #17 surface tried
  SearchActivity's `search_empty_message`, but the accessibility layout exposed only
  the toolbar/search input after launch, so L3 correctly returned inconclusive. This
  was not used as matched-pair evidence. The issue and implementation were updated to
  use the stable Search tab `search_card` surface.

## Key SHA-256 Values

- Seed spec: `93005acf1336d21558d40c273dd7a6af7a3e1afc7ade2336043121786e68f217`
- Run spec: `b81263f0a653c53ffe6d0e1fc258cd3cbc17461ad458fc7ecf43611b677ed74c`
- Patch: `e86d87aa66a3681e98446fd75247160d9fd785f556298fc072c6b2a7e690d35f`
- Baseline layout fixture: `ccea901308c024bd43b5873e512e9ac07ab800099cd61020b154d80b3ee9a910`
- Defect layout fixture: `b39978183e73f6bbc7f9101a297dd9d156f5d9a9a1b08db1e6e5752d6621696d`
- Baseline L3 response fixture: `4a27bdf2be889715db71bc37aaaa3a20c401be316b6a14bbfd1f05d0c0b24134`
- Defect L3 response fixture: `67b10fc013a1fec88ec12d36b75ca5b4c3be1fe67b55e5c4d13075351e8c15ef`
- Baseline verdict: `1bb06e598b0698c2fbb626431ae5c836900aaa57e8014f0d7f8ae3d2d2b92c53`
- Defect verdict: `da62d765c466f5bb728f4ef1119c5005ba4a4dd6fb37731aed3829e289843f91`

## Known Gaps

- This is still a text-layout semantic L3 seed. It does not prove visual-only or
  multimodal L3 reliability.
- Unlike #14, this issue ran one live L3 judge call per half; it does not measure
  repeatability for `ui-rendering-02`.
- The emulator is API 36 (`medium_phone`).
- The first attempted SearchActivity empty-state surface was discarded because the
  target text was not visible in the final accessibility layout.

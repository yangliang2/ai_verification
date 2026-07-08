# 2026-07-07 Wikipedia navigation back-button swallowed Run Record

Primary issue: [#16](https://github.com/yangliang2/ai_verification/issues/16)
- M2 navigation Back-button Goldset seed.

Parent scoping issue: [#13](https://github.com/yangliang2/ai_verification/issues/13).

## What This Proves

This run adds a non-crashing navigation-state defect to the Goldset. The host
surface is Wikipedia Android `SearchActivity`, reached from the bottom Search tab.

Matched pair, same app, same scenario, same `dark_mode` observation boundary:

| half | L1 | L2 | Back result before `dark_mode` | runner exit | runner time |
|---|---|---|---|---:|---:|
| baseline | inconclusive | pass | returned to Search tab, `search_card` visible | 0 | 235s |
| defect | inconclusive | fail / `state_loss` | stuck in SearchActivity, `search_src_text` visible | 1 | 296s |

The current L2 schema still reports this as `state_loss`, but the evidence is a
navigation-state mismatch:

`resource-id='search_card': node disappeared after operation; before resource-id='<absent>', expected resource-id='search_card'`

## Source Pattern

The real-world source pattern is `bench/goldset/candidates.md` N3: Tusky search
Back behavior was swallowed/inconsistent, requiring an extra Back press after
searching. The fix routed hardware/system Back directly instead of allowing
SearchView focus/collapse state to consume it.

This seed maps that pattern to Wikipedia SearchActivity: the soft-keyboard Back
path is allowed first, then the first Activity-level Back callback is swallowed
by the injected defect.

## Scenario

1. Preseed host prompt prefs after initial app-data setup.
2. Start `org.wikipedia.dev` via launcher alias `org.wikipedia.DefaultIcon`.
3. Tap Search tab, tap `search_card`.
4. Type sentinel `zznavbackqx` into `search_src_text`.
5. Press system Back once to hide the soft keyboard while staying in SearchActivity.
6. Press system Back a second time; this should leave SearchActivity.
7. Runner captures `after-segment-0`.
8. Runner injects `dark_mode` with `night=yes`.
9. Runner captures `after-event-0`.
10. L2 asserts `search_card.resource-id == "search_card"`.

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
adb -s emulator-5554 push /tmp/issue16-prefs.xml /data/local/tmp/issue16-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue16-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue16-prefs.xml shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER -n org.wikipedia.dev/org.wikipedia.DefaultIcon
```

Baseline runner:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-navigation-02-back-button-swallowed.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/2026-07-07-wikipedia-navigation-02-back-button-swallowed/baseline/artifacts \
  --no-launch
```

Defect build:

```bash
patch --dry-run -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
patch -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
```

Valid defect setup used the already-installed defect APK and did not repeat
`pm clear` after the discarded prelaunch ANR attempt. It force-stopped the app,
reset night mode, launched the app, confirmed `nav_tab_search`, and cleared
logcat immediately before the runner.

Defect runner:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-navigation-02-back-button-swallowed.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/2026-07-07-wikipedia-navigation-02-back-button-swallowed/defect/artifacts \
  --no-launch
```

Host restore:

```bash
patch -R -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
patch --dry-run -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch
git hash-object /Users/80268204/hosts/wikipedia/app/src/main/java/org/wikipedia/search/SearchActivity.kt
```

## Results

Valid baseline:

- `baseline/build-exit.txt`: `exit_status=0`, `duration_seconds=31`
- Gradle: `BUILD SUCCESSFUL in 29s`, 77 actionable tasks up-to-date
- `baseline/runner-exit.txt`: `exit_status=0`, `duration_seconds=235`
- `baseline/verdict.json`: L1 inconclusive, L2 pass
- `baseline/artifacts/after-segment-0/layout.json`: `search_card` present
- `baseline/artifacts/after-event-0/layout.json`: `search_card` present
- Driver observation: first Back hid the keyboard and stayed in SearchActivity;
  second Back returned to the Search tab with `search_card` visible.

Valid defect:

- `defect/build-exit.txt`: `exit_status=0`, `duration_seconds=136`
- Gradle: `BUILD SUCCESSFUL in 2m 13s`, 77 tasks: 5 executed, 72 up-to-date
- `defect/runner-exit.txt`: `exit_status=1`, `duration_seconds=296`
- `defect/verdict.json`: L1 inconclusive, L2 fail / `state_loss`
- `defect/artifacts/after-segment-0/layout.json`: `search_src_text=zznavbackqx`, `search_card` absent
- `defect/artifacts/after-event-0/layout.json`: `search_src_text=zznavbackqx`, `search_card` absent
- Driver observation: after the second Back, SearchActivity was still visible.

Host restore:

- `baseline-rebuild/build-exit.txt`: `exit_status=0`, `duration_seconds=1127`
- Gradle: `BUILD SUCCESSFUL in 18m 47s`, 77 tasks: 2 executed, 4 from cache, 71 up-to-date
- Restored source hash:
  `736ac92bbff4f2892de419209c3e52e7fe77a772`
- `patch --dry-run` for the defect patch succeeds after restore, confirming the
  source tree is back at the unpatched baseline.
- `baseline-rebuild/apk.sha256` differs from `baseline/apk.sha256`; this run
  does not rely on APK byte identity as restore proof.

## Environment

- Host: `/Users/80268204/hosts/wikipedia`, tarball checkout of Wikimedia Android
  app commit `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- Package: `org.wikipedia.dev`
- Launcher alias: `org.wikipedia.DefaultIcon`
- APK path: `/Users/80268204/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk`
- Baseline APK SHA-256: `a5a5265b65c234ed05c84e4cd28fb319054d88fb19fd0bee54cf1e96ce6d472f`
- Defect APK SHA-256: `7daae989caa89762764197aec264a9c2cfde457554c3efb96bcd7079aa969e8b`
- Baseline-rebuild APK SHA-256: `9ea99071db203dae64fd371ad6d904183b6d705e1059f29998f8bbda62cdf75a`
- Patch SHA-256: `a77e846712252ccf5e3d9db5005e82e0b257512b9d540db0bb54d9a017589897`
- Run spec SHA-256: `40967f0397d5c3df6324093eaa46139fbbb4a8894430a86873204ae249251a2a`
- Seed spec SHA-256: `03866f5e09aae16d680e4f1e29940094c02fe03480efaa4c4ab18a204fead380`
- Baseline verdict SHA-256: `e5be4d3fb5f7aa7ba150be5e587fd610602693980ff1077e9d4f12e9520d4c56`
- Defect verdict SHA-256: `942a2567a5e5e03b2a8b5cbbcb79b36f7ede118b955e609299d8eb50bfeaadf9`
- Device: `emulator-5554`, AVD `medium_phone`, `sdk_gphone64_arm64`,
  Android 16 / API 36
- Android CLI: `1.0.15498356`
- adb: `1.0.41`, platform-tools `37.0.0-14910828`
- Codex CLI: `0.142.5`
- Python: `3.12.13`
- pytest: `9.1.1`

## Implementation Mapping

- Seed spec:
  `bench/goldset/specs/wikipedia-navigation-02-back-button-swallowed.md`
- Run spec:
  `bench/goldset/run-specs/wikipedia-navigation-02-back-button-swallowed.yaml`
- Defect patch:
  `bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch`
- Frozen live fixtures:
  `bench/goldset/fixtures/wikipedia-navigation-02-back-button-swallowed/{control,defect}-{before,after}-layout.json`
- Regression test:
  `tests/bench/test_goldset_navigation_02_back_button_swallowed.py`

## Artifact Inventory

- `baseline/verdict.json`, `defect/verdict.json` - final valid verdicts
- `{baseline,defect}/artifacts/after-segment-0/` - pre-`dark_mode`
  checkpoint: `layout.json`, `screen.png`, `screen-annotated.png`,
  `logcat.txt`, `commands.json`
- `{baseline,defect}/artifacts/after-event-0/` - post-`dark_mode`
  checkpoint: same shape
- `{baseline,defect}/artifacts/wikipedia-navigation-02-back-button-swallowed-segment-0/`
  - Codex JSONL events and structured journey result
- `baseline/apk.sha256`, `defect/apk.sha256`, `baseline-rebuild/apk.sha256`
- `checksums.sha256` - SHA-256 manifest for this run record

Discarded attempt kept for audit:

- `defect-attempt-prelaunch-anr/`: the first defect setup after `pm clear`
  launched MainActivity but the app hit a startup ANR before the runner began and
  was killed by Android. This was not used as evidence. The valid defect run
  relaunched the same installed defect APK, confirmed `nav_tab_search`, and
  cleared logcat immediately before the runner.

## Known Gaps

- The emulator is API 36 (`medium_phone`), not the earlier API 35 AVD used for
  some M1 runs.
- The first defect prelaunch after `pm clear` hit a startup ANR unrelated to the
  Back seed path. It is retained as a discarded setup attempt.
- The host restore APK SHA differs from the original baseline APK SHA even after
  source restore; use the restored source hash and patch dry-run, not APK byte
  identity, as the restore proof for this run.
- Current L2 verdict schema reports the navigation-state assertion failure as
  `state_loss`; this issue intentionally did not broaden the taxonomy.

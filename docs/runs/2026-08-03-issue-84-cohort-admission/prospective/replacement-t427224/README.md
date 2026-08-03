# T427224 — Polish Read More lifecycle admission preflight

Candidate: T427224 (approved addendum rank 5, G-08 deterministic
ordering/deduplication)

Frozen source base: `79ef892e5e88dfea705350bbfa1be2ee14458b47`

## Fixture and oracle

Fixture source:
`bench/m6/admission-fixtures/prospective/replacement-t427224/M6T427224ReadMoreLifecycleTest.kt`

Fixture SHA-256:
`f187237847f36e24ba88a9775795896fdb93d95f3b286d8a67fdd9d3dce55573`

The reporter screenshot is preserved at
`external-snapshots/T427224-Duplicate_related_articles.png` with SHA-256
`6cd078bdf06625febacb4c9f8b4bb47f852facac22bd7868795ae32d875bba5a`. It shows
the three related-page identities `(2039) Payne-Gaposchkin`, `Annie Jump
Cannon`, and `Harvard College Observatory` twice.

The fixture constructs a Polish `PageViewModel` and exercises the two
production command generators that can contribute Read More entries:
`JavaScriptActionHandler.setFooter()` and `appendReadMode()`. It projects the
recorded three-item identity set across those lifecycle commands and requires
three total occurrences, not six.

## Commands and results

Build (exact frozen checkout):

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@17 /usr/bin/time -p \
  ./gradlew :app:assembleDevDebugAndroidTest
```

Result: exit 0; `BUILD SUCCESSFUL in 1s`; 83 actionable tasks (4 executed,
79 up-to-date); wall/user/sys `1.99s / 0.55s / 0.06s`.

Install and test:

```bash
adb -s emulator-5554 install -r \
  app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk

/usr/bin/time -p adb -s emulator-5554 shell am instrument -w \
  -e class org.wikipedia.m6.M6T427224ReadMoreLifecycleTest \
  org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Result: 1 test, 1 expected failure; instrumentation `0.038s`; shell
wall/user/sys `1.39s / 0.00s / 0.00s`.

Machine result:

```text
M6_T427224_RESULT lang=pl recorded_identities=3 unique_identities=3 footer_calls=2 read_more_commands=2 item_counts=[3, 3] projected_occurrences=6 expected_unique_occurrences=3
```

The assertion fails with expected `3` versus actual `6`, providing a stable
G-08 admission signal on the frozen base.

APK identity:

- AndroidTest APK (fixture build):
  `147ff6fafbbbebe472b170cde201a6c7307c5d76124f292f6e2fb9d031bfe866`

## Artifact inventory

- `assemble-androidTest.log` — exact Gradle output and timing
- `adb-install-test.txt` — bounded test APK install
- `instrumentation.txt` — accountable runner output
- `logcat-full.txt` — machine result, assertion, and runner summary
- `../external-snapshots/T427224-Duplicate_related_articles.png` — reporter
  screenshot (inventory path from the run root)

## Claim boundary

This is a deterministic command/lifecycle oracle tied to production seams. It
does not claim a live PCS response replay, a full WebView render, or an OEM/
device-specific reproduction. No upstream source tree, task, branch, commit,
PR, or external repository state was changed.

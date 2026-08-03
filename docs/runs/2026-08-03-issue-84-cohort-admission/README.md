# Issue #84 — M6 cohort admission preflight

Date: 2026-08-03 (America/New_York)

## Scope and claim boundary

This run record captures the authorized, pre-formal-lane admission work for the
M6 six-case qualification cohort. The maintainer approved:

- three historical and three prospective slots;
- the published replacement order;
- G-03/G-04/G-06/G-08 coverage;
- a local-only claim boundary; and
- isolated upstream checkout, dependency resolution, build, and test actions
  that do not change upstream state.

No formal M6 lane was started. No upstream task, assignment, comment, branch,
commit, pull request, or repository state was changed. Temporary fixture copies
exist only in isolated local worktrees.

Project source base:
`7c9ce3f9c594c20cc33aea29cfa3468ad1f1323d`

Upstream source repository:
`https://github.com/wikimedia/apps-android-wikipedia`

Frozen prospective base:
`79ef892e5e88dfea705350bbfa1be2ee14458b47`

## Admission outcome

The historical track is ready for freezing. All three exact historical pairs
compile the same fixture, reject the expected behavior on the declared pre-fix
revision, and pass it on the declared fixed revision.

The prospective track is **not** ready for freezing:

| Candidate | Approved position | Preflight result | Admission disposition |
| --- | --- | --- | --- |
| T431797 | primary P-01 | live locale switch did not reproduce the reported stale article chrome, search, or bottom navigation | exclude |
| T429913 | primary P-02 | bounded registered-offline cleanup removed all seeded rows/files and completed successfully | exclude; reporter's 4.39 GB category remains unbounded |
| T424161 | primary P-03 | PR 6575 was merged and its merge commit is already an ancestor of the frozen base | exclude as already fixed before admission |
| T426527 | replacement rank 1 | reporter traced the behavior to power saving; the time-bounded campaign is over | exclude as non-reproducible/currently inapplicable |
| T419910 | replacement rank 2 | 273 local pages load and sample deterministically; the remaining phase is live network/server behavior | exclude; no stable local failure oracle |
| T425733 | replacement rank 3 | first onboarding page is black while the second is light under a light system theme | **admissible G-04 failure oracle** |
| T426893 | replacement rank 4 | gallery media-list exposes four offline-header slots but image metadata exposes none | **admissible G-06 bounded failure oracle** |
| T427224 | replacement rank 5 | the three recorded Polish related-page identities are projected twice across footer setup and lazy append | **admissible G-08 bounded failure oracle** |

All three prospective slots now have stable, machine-checkable failing oracles:
G-04 (T425733), G-06 (T426893), and G-08 (T427224). The six-slot manifest is
not frozen yet; it must still pass the schema, overlap, checksum, and
replacement-ledger admission checks.

The approved addendum for T426893 (G-06) and T427224 (G-08) is documented in
`ADDENDUM.md`; both candidates received only the authorized isolated local
preflight. No upstream task, assignment, comment, branch, commit, pull
request, or repository state was changed.

## Environment

- host: macOS 26.3, Apple Silicon
- Android CLI: 1.0.15498356
- Android Debug Bridge: 1.0.41 / 37.0.0-14910828
- Android SDK: `/opt/homebrew/share/android-commandlinetools`
- JDK: OpenJDK 17.0.19 (Homebrew)
- emulator: `emulator-5554`, `sdk_gphone64_arm64`, Android 15 / API 35,
  fingerprint
  `google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys`
- app package: `org.wikipedia.dev`
- app version: `50600-dev-2026-08-03` (`versionCode=50600`)
- prospective Gradle/Kotlin: 9.6.1 / 2.3.21
- H-01 Gradle/Kotlin: 9.5.0 / 2.3.20
- H-02 Gradle/Kotlin: 8.10.2 / 1.9.24
- H-03 Gradle/Kotlin: 8.9 / 1.9.23
- installed SDK build-tools observed: 34.0.0 and 35.0.0

## Exact historical-pair results

Fixtures in `bench/m6/admission-fixtures/historical/` were copied byte-for-byte
into both isolated revisions for each pair. The project copies are the durable
fixture identities; no fixture was committed upstream.

### H-01 — T425894 / PR 6580

- pre-fix: `b88c6a672e18167727fcc9d913c9ed57e50e03ce`
- fixed: `996ad8592fbd41e59ea195da72a3e9a728181006`
- fixture SHA-256:
  `d7d4b7412554020f82bf2a362c02d9bcc69eaa568ac50d8f1db8ad988a02b327`
- pre-fix: 1 test, 1 expected failure, JUnit 1.587s
- fixed: 1 test, 1 pass, JUnit 1.366s
- pre-fix failure: three definition nodes exposed the CSS/style payload; the
  log records
  `<style data-mw-deduplicate="TemplateStyles:r886049734">...`
- first/fixed build wall durations: 436.95s / 86.82s

### H-02 — T379777 / PR 5342

- pre-fix: `675b930624c80498b3d3881592ac1c3f179a2709`
- fixed: `c7250ce14feaa24e52d3a2468fb86b15fa56cfff`
- fixture SHA-256:
  `8a0f41f25f8fe44810826780b9cc8ce519d57b78c2078515504a161c224eda92`
- pre-fix: 3 tests, 3 expected failures, JUnit 2.540s
- fixed: 3 tests, 3 passes, JUnit 2.706s
- the pre-fix failures independently identify English history,
  reading-list, and open-tab suggestions leaking into an eswiki search
- initial build wall: 348.24s; recorded pre/fixed accountable invocation walls:
  73.44s / 74.91s

### H-03 — T382892 / PR 5203

- pre-fix: `d67ec44adc1d8c4d8dc7dcb736c0faa9f1b6934c`
- fixed: `fdc4ffb9ef3be93a96500bf630057c1e66ac7b8f`
- fixture SHA-256:
  `2c1c552745faabcf3c4e3c0c7322fb264a4b21f12394f33caa27bb9aaf37088d`
- pre-fix: 1 test, 1 expected failure, JUnit 0.578s
- fixed: 1 test, 1 pass, JUnit 0.569s
- pre-fix failure:
  `Link-success and language-change callbacks must not collide.. Actual: 1`
- recorded invocation walls: 16.17s / 73.93s
- first install attempt was non-accountable:
  `INSTALL_FAILED_VERSION_DOWNGRADE`; the bounded fallback explicitly allowed
  downgrade installation before rerunning the same test

### Historical command forms

The following commands were run from each exact isolated worktree, with the
corresponding fixture class and worktree path substituted:

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@17 /usr/bin/time -p \
  ./gradlew :app:assembleDevDebug :app:assembleDevDebugAndroidTest

android run --device emulator-5554 \
  --apks app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  --activity org.wikipedia.main.MainActivity

adb -s emulator-5554 install -r \
  app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk

/usr/bin/time -p adb -s emulator-5554 shell am instrument -w \
  -e class org.wikipedia.m6.M6H0X...Test \
  org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

H-03's one bounded downgrade recovery used:

```bash
adb -s emulator-5554 install -r -d \
  app/build/outputs/apk/dev/debug/app-dev-debug.apk
```

JUnit and bounded logcat outputs are under
`historical/h-01/`, `historical/h-02/`, and `historical/h-03/`.

## Prospective base build

Command:

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@17 /usr/bin/time -p \
  ./gradlew :app:assembleDevDebug :app:assembleDevDebugAndroidTest
```

Result:

- exit 0; `BUILD SUCCESSFUL in 3m 25s`
- 101 actionable tasks: 95 executed, 6 from cache
- wall/user/sys: 205.24s / 1.77s / 0.29s
- app APK SHA-256:
  `e603547b55294f08dce23601a651bb0c68e160d3d4f3c871984ee2b85914d686`

Install/launch:

```bash
android run --device emulator-5554 \
  --apks app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  --activity org.wikipedia.main.MainActivity
```

Result: install and activation succeeded for `org.wikipedia.dev`.

## Prospective candidate evidence

### T431797 — locale switch

The Android 15 emulator was configured with `zh-Hans-CN,en-US`. An English
article remained open while Chinese became the primary system locale. Returning
to the app produced Chinese article controls and search chrome:
`主题`, `保存`, `在条目内查找`, `搜索维基百科`, `目录`, and `语言`.

After completing onboarding, the main bottom navigation was also Chinese:
`首页`, `已保存`, `搜索`, `活动`, and `更多`.

Evidence:

- `prospective/baseline/p01-live-switch-layout.json`
- `prospective/baseline/p01-live-switch-screen.png`
- `prospective/baseline/p01-live-switch-dumpsys.txt`
- `prospective/baseline/p01-bottom-nav-chinese-layout.json`
- `prospective/baseline/p01-bottom-nav-chinese-screen.png`

This is manual API-35 emulator evidence, not an OEM/Pixel 9 matrix. It is enough
to show that the reported stale chrome is not reproducible on the frozen base;
it does not claim universal locale correctness.

### T429913 — registered offline cleanup

Fixture:
`bench/m6/admission-fixtures/prospective/p-02/M6P02OfflineCleanupTest.kt`

Fixture SHA-256:
`42077e0ee95d39cf4a202b6ea0e43127be8141cbbe8b805dddc1b617e2ca0cf6`

The fixture seeds 24 pages, 96 registered offline objects, 192 content/metadata
files, and 6,294,584 bytes. It then invokes the production
`ReadingListPageDao.markPagesForOffline(..., false, ...)` path and the real
WorkManager/SavedPageSyncService cleanup.

Accountable command:

```bash
/usr/bin/time -p adb -s emulator-5554 shell am instrument -w \
  -e class org.wikipedia.m6.M6P02OfflineCleanupTest \
  org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Result:

- 1 test, 1 pass; runner 2.547s; wall 3.97s
- worker state `SUCCEEDED`
- files: 192 to 0
- offline objects: 96 to 0
- bytes: 6,294,584 to 0
- fixture elapsed: 2,292ms

Two non-accountable setup attempts remain in the record:

1. Android CLI multi-APK install rejected duplicate split definitions with
   `INSTALL_FAILED_INVALID_APK`.
2. The first fixture binary used a Kotlin expression-body `@After`, which
   compiled to a non-void JVM method and caused runner initialization failure.
   The fixture was corrected before the accountable run.

The bounded pass does not explain or reproduce the reporter's 4.39 GB, Redmi
behavior, real large downloads, or unregistered app-data categories.

### T419910 — Saved/Discover large corpus

Fixture:
`bench/m6/admission-fixtures/prospective/replacement-t419910/M6T419910DiscoverCorpusPreflightTest.kt`

Fixture SHA-256:
`d17d86b0cb5937527d302708fb822345cda53c393a1a68ee35b597ca24efec11`

Command:

```bash
/usr/bin/time -p adb -s emulator-5554 shell am instrument -w \
  -e class org.wikipedia.m6.M6T419910DiscoverCorpusPreflightTest \
  org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Result:

- 1 test, 1 pass; runner 0.361s; wall 1.62s
- corpus/loaded: 273 / 273
- configured sample: 5
- load/sample/readiness: 10ms / 1ms / 1ms
- network phase exercised: false

Production code samples only five saved pages before sequential
`searchMoreLike` calls. A deterministic local corpus therefore does not
reproduce the task; the remaining live-network phase cannot be frozen without
recorded server behavior. This is G-06/network-performance work, not a G-08
deterministic concurrency oracle.

### T425733 — onboarding theme

Fixture:
`bench/m6/admission-fixtures/prospective/replacement-t425733/M6T425733OnboardingThemeTest.kt`

Fixture SHA-256:
`36485f95b5cbf6a40c6dca19eb7f36451fc8a9e551960067c8b02dc63c377cbe`

Command:

```bash
/usr/bin/time -p adb -s emulator-5554 shell am instrument -w \
  -e class org.wikipedia.m6.M6T425733OnboardingThemeTest \
  org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Result:

- 1 test, 1 expected failure; runner 1.482s; wall 2.74s
- expected system/app theme: `LIGHT`
- first-screen edge luminance: 0.0
- second-screen edge luminance: 1.0
- delta: 1.0
- assertion:
  `fresh-install onboarding screens must both use the light paper color`

Screenshots were visually inspected:

- `prospective/replacement-t425733/first.png`: black first page
- `prospective/replacement-t425733/second.png`: light second page

This is a stable, machine-checkable G-04 failing oracle and is eligible for a
prospective slot after the replacement transition is frozen.

### T426893 — gallery metadata offline-cache seam

Fixture:
`bench/m6/admission-fixtures/prospective/replacement-t426893/M6T426893GalleryMetadataOfflineTest.kt`

Fixture SHA-256:
`cf723d68747df12cb00a1f472c4230c90eb00a2bb3fb0478f04192c4971410e1`

Accountable commands:

```bash
./gradlew :app:assembleDevDebugAndroidTest

adb -s emulator-5554 install -r \
  app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk

/usr/bin/time -p adb -s emulator-5554 shell am instrument -w \
  -e class org.wikipedia.m6.M6T426893GalleryMetadataOfflineTest \
  org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Results:

- AndroidTest build exit 0; 83 actionable tasks (all up-to-date); wall 0.55s
- combined approved-candidate test APK SHA-256:
  `147ff6fafbbbebe472b170cde201a6c7307c5d76124f292f6e2fb9d031bfe866`
- 1 test, 1 expected failure; runner 0.028s; wall 1.24s
- result: `media_list_header_slots=4 image_info_header_slots=0 expected_min=3`
- assertion: image metadata does not expose the save/lang/title headers required
  by the offline-cache contract

This is a bounded production-seam oracle: Retrofit reflection observes the
actual `RestService.getMediaList` and `Service.getImageInfo` declarations. It
does not claim an OEM storage failure, a live Wikimedia response, or a full
offline gallery/WebView reproduction. The full accountable output is under
`prospective/replacement-t426893/`, including the raw logcat line and test
runner failure.

### T427224 — Polish Read More lifecycle deduplication

Fixture:
`bench/m6/admission-fixtures/prospective/replacement-t427224/M6T427224ReadMoreLifecycleTest.kt`

Fixture SHA-256:
`f187237847f36e24ba88a9775795896fdb93d95f3b286d8a67fdd9d3dce55573`

The external reporter screenshot is preserved at
`external-snapshots/T427224-Duplicate_related_articles.png` (SHA-256:
`6cd078bdf06625febacb4c9f8b4bb47f852facac22bd7868795ae32d875bba5a`). It shows
the same three Polish related-page identities twice:
`(2039) Payne-Gaposchkin`, `Annie Jump Cannon`, and `Harvard College
Observatory`.

Accountable commands:

```bash
./gradlew :app:assembleDevDebugAndroidTest

adb -s emulator-5554 install -r \
  app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk

/usr/bin/time -p adb -s emulator-5554 shell am instrument -w \
  -e class org.wikipedia.m6.M6T427224ReadMoreLifecycleTest \
  org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Results:

- AndroidTest build exit 0; 83 actionable tasks; wall 1.99s
- test APK SHA-256:
  `147ff6fafbbbebe472b170cde201a6c7307c5d76124f292f6e2fb9d031bfe866`
- 1 test, 1 expected failure; runner 0.038s; wall 1.39s
- result: `lang=pl recorded_identities=3 unique_identities=3
  footer_calls=2 read_more_commands=2 item_counts=[3, 3]
  projected_occurrences=6 expected_unique_occurrences=3`
- assertion: the three recorded identities are projected twice across the
  production footer setup and lazy append commands

This is a deterministic command/lifecycle oracle tied to
`JavaScriptActionHandler.setFooter()` and `appendReadMode()`. It is not a live
PCS response replay and does not claim visual or device-specific reproduction;
the screenshot is retained as the external reporter artifact. Full logs are in
`prospective/replacement-t427224/`.

## External snapshots and read-only candidate discovery

`external-snapshots/` contains the exact public task HTML, GitHub PR metadata,
and open-PR searches used for admission decisions. Important facts:

- PR 6575 merged on 2026-05-08 as
  `c46e647f55d88ee117619111c43124789264e16d`; that merge commit is an
  ancestor of the frozen prospective base.
- T426893 is Open/Low, unassigned, and has no matching open PR in the official
  upstream repository.
- T427224 is Open/Low, unassigned, and has no matching open PR in the official
  upstream repository.
- T381534 was not proposed because it remains assigned to WRai-WMF even though
  its two implementation PRs are closed.
- T419101 was not proposed because its saved-page ordering behavior is the same
  remote timestamp defect already addressed by PR 6575 in the frozen base.
- T392440 and T350895 were not proposed because their reporters/team could not
  provide a stable reproduction order.

The two approved additions received isolated fixture/build/instrumentation
preflight only. No upstream task, assignment, comment, branch, commit, pull
request, or repository state was changed.

## Artifact inventory

| Path | Contents |
| --- | --- |
| `historical/h-01/` | pre/fixed JUnit and logcat for T425894 |
| `historical/h-02/` | pre/fixed JUnit and per-source logcat for T379777 |
| `historical/h-03/` | pre/fixed JUnit and logcat for T382892 |
| `prospective/baseline/` | base build/install, device, locale layouts, dumpsys, screenshots |
| `prospective/p-02/` | three fixture attempts, build/install/instrumentation/logcat/timing |
| `prospective/replacement-t419910/` | build/install/instrumentation/logcat/timing |
| `prospective/replacement-t425733/` | build/install/instrumentation/logcat/timing and two screenshots |
| `prospective/replacement-t426893/` | build/install/instrumentation/logcat for gallery metadata oracle |
| `prospective/replacement-t427224/` | build/install/instrumentation/logcat for Polish Read More oracle |
| `external-snapshots/` | official task HTML, PR JSON, PR-search JSON, and T427224 reporter screenshot |
| `ADDENDUM.md` | proposed candidate-pool amendment and decision boundary |
| `.gitattributes` | preserve raw generated whitespace without `diff --check` false positives |
| `checksums.sha256` | deterministic SHA-256 inventory generated after this README |

## Known gaps and next gate

- A frozen six-slot manifest does not yet exist; the next gate is manifest/schema
  validation and freeze review.
- All three prospective replacement slots now have admissible bounded failing
  oracles (T425733/G-04, T426893/G-06, T427224/G-08).
- T426893 and T427224 were approved for isolated local preflight only; neither
  has any upstream state change.
- No physical device, OEM matrix, long-duration storage pressure, production
  network replay, or authenticated account flow was exercised.
- H-03 required one bounded install downgrade recovery.
- T429913's reporter-scale data and T419910's live network phase remain
  intentionally outside the local claim.
- The prospective base was locally modified only with test fixtures; no
  upstream source commit was produced.

The next gate is creation and validation of the six-slot manifest. It can freeze
only if the three historical pairs, the three prospective failure oracles, and
all schema, overlap, checksum, and replacement-ledger checks pass.

## Evidence integrity commands

```bash
git diff --check

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.run_record_checksums \
  docs/runs/2026-08-03-issue-84-cohort-admission

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.run_record_checksums --verify \
  docs/runs/2026-08-03-issue-84-cohort-admission
```

Result before the next evidence commit:

- `git diff --check`: exit 0
- inventory generation: exit 0; artifact count recorded in `checksums.sha256`
- inventory verification: exit 0; `checksum inventory verified`

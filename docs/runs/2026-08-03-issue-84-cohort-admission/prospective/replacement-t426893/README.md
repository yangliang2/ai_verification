# T426893 — gallery metadata offline-cache admission preflight

Candidate: T426893 (approved addendum rank 4, G-06 resource/storage)

Frozen source base: `79ef892e5e88dfea705350bbfa1be2ee14458b47`

## Fixture and oracle

Fixture source:
`bench/m6/admission-fixtures/prospective/replacement-t426893/M6T426893GalleryMetadataOfflineTest.kt`

Fixture SHA-256:
`cf723d68747df12cb00a1f472c4230c90eb00a2bb3fb0478f04192c4971410e1`

The test reflects the production Retrofit declarations. The media-list method
has four `@Header` parameters, while `Service.getImageInfo` has none. The
bounded contract requires at least the save/lang/title header slots on both
paths so an already cached gallery image can be reopened without a second
metadata network request.

## Commands and results

Build (exact frozen checkout):

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@17 /usr/bin/time -p \
  ./gradlew :app:assembleDevDebugAndroidTest
```

Result: exit 0; `BUILD SUCCESSFUL in 472ms`; 83 actionable tasks (all
up-to-date); wall/user/sys `0.55s / 0.48s / 0.04s`.

Install and test:

```bash
adb -s emulator-5554 install -r \
  app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk

/usr/bin/time -p adb -s emulator-5554 shell am instrument -w \
  -e class org.wikipedia.m6.M6T426893GalleryMetadataOfflineTest \
  org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Result: 1 test, 1 expected failure; instrumentation `0.028s`; shell
wall/user/sys `1.24s / 0.00s / 0.00s`.

Machine result:

```text
M6_T426893_RESULT media_list_header_slots=4 image_info_header_slots=0 expected_min=3
```

The failing assertion is the expected admission signal: image metadata does
not expose the three offline-cache header slots.

APK identities:

- app APK (frozen-base build):
  `e603547b55294f08dce23601a651bb0c68e160d3d4f3c871984ee2b85914d686`
- AndroidTest APK (combined approved-candidate fixture build):
  `147ff6fafbbbebe472b170cde201a6c7307c5d76124f292f6e2fb9d031bfe866`

## Artifact inventory

- `assemble-androidTest.log` — exact Gradle output and timing
- `adb-install-test.txt` — bounded test APK install
- `instrumentation.txt` — accountable runner output
- `logcat-full.txt` — `M6_T426893_RESULT`, assertion, and runner summary
- `android-run-app.log` — app launch/install preflight record
- `logcat.txt` — selected logcat capture from the app preflight

## Claim boundary

This is a local source-shape/production-seam oracle. It does not claim a live
Wikimedia response, OEM storage layout, network interception trace, or full
offline gallery UI reproduction. No upstream source tree, task, branch, commit,
PR, or external repository state was changed.

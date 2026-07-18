# M4 T426553 prospective tracer (in progress)

## Upstream task snapshot

Fetched `https://phabricator.wikimedia.org/T426553` on 2026-07-18. The page reported `Open, Needs Triage` and `Assigned To: None`. The task was not edited and no upstream interaction was performed.

## Frozen source and implementation

- Isolated worktree: `/Users/peter/hosts/wikipedia-t426553`
- Frozen base: `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- Final candidate commit: `eeb74c820cab750187492f4c68791442da42c8f5`
- Changed seam: `app/src/main/java/org/wikipedia/page/LinkHandler.kt`
- Regression test: `app/src/test/java/org/wikipedia/util/UriUtilTest.kt`

The candidate keeps the href percent-encoded until URI parsing so encoded query values containing an embedded URL and fragment are not converted into structural separators.

## Verification evidence

```sh
./gradlew --offline --no-daemon :app:testFdroidDebugUnitTest \
  --tests org.wikipedia.util.UriUtilTest.testEncodedExternalQueryValueRemainsEncodedWhenParsedAsUri
```

Result: 1 test, 0 failures, 0 errors, 34.936s. Report: `app/build/test-results/testFdroidDebugUnitTest/TEST-org.wikipedia.util.UriUtilTest.xml`.

Full `UriUtilTest` rerun: 11 tests, 0 skipped, 0 failures, 0 errors, 1.351s; Gradle build completed successfully in 9s.

```sh
./gradlew --no-daemon :app:assembleFdroidDebug
```

Initial candidate APK SHA-256: `bb3370a58ea86b93b96537b1acca78af83f49eef9203ae9d2e5868371ddd8fd8`. After adding the debug-only Journey seam, final candidate APK SHA-256 is `2c281135efe47d9742cbd9089bde1e446cb2020aff3abe5232179e12b5603819`; package `org.wikipedia`; version `50594-fdroid-2026-07-18`.

Deployment: `adb -s emulator-5554 install -r .../app-fdroid-debug.apk` returned `Success`; `dumpsys package` reports versionCode `50594`, versionName `50594-fdroid-2026-07-18`.

Device navigation smoke setup: `adb -s emulator-5554 shell am start -a android.intent.action.VIEW -d 'https://de.wikipedia.org/wiki/Wichlinghausen' org.wikipedia` launched `org.wikipedia/.page.PageActivity`. This confirms the frozen candidate accepts the task's fixed article URL; the in-page escaped-link click and external-intent capture remain outstanding.

Artifacts: `artifacts/article-page.png` and `artifacts/window.xml` capture the loaded article page after dismissing the first-run introduction dialog. The UI dump confirms `org.wikipedia:id/page_web_view` is present; WebView link text is not exposed to the accessibility tree, so the target escaped-link click still needs a scripted WebView/Journey seam.

## Remaining acceptance gaps

Device deployment and the primary Journey have not yet been run; a separate Verification Agent conclusion and complete regression matrix are still required before closing issue #63.

## Debug intent Journey seam

For the debug candidate, `DebugLinkInjectionActivity` accepts `href`, `title`, and `text` extras and feeds them through the real `LinkHandler.onMessage()` boundary. The exact injection command was:

```sh
adb -s emulator-5554 shell am start -n org.wikipedia/.page.DebugLinkInjectionActivity \
  --es href 'https://nwbib.de/search?nwbibspatial=https%3A%2F%2Fnwbib.de%2Fspatial%23Q1310002' \
  --es title 'Literatur über Wichlinghausen' --es text 'Literatur'
```

The logcat oracle recorded exactly `INJECTED_EXTERNAL_URI=https://nwbib.de/search?nwbibspatial=https%3A%2F%2Fnwbib.de%2Fspatial%23Q1310002`, proving the encoded query value survives the production parser. The seam is debug-only and the activity exits immediately in non-debug builds.

## Independent Verification Agent

An independent `codex exec` session produced `verification-agent/codex-journey-result.json` with exactly one conclusion: `locally_supported`. It independently installed the APK, launched the injection activity, and observed the exact expected URI in logcat. Its input contained only the Journey contract and persisted APK path; it omitted task identifiers, issue URLs, developer reasoning, and fix history.

The regression injection matrix was also exercised through the same seam for internal title, fragment, diff, mailto, and protocol-relative inputs. Only the protocol-relative external case emits `INJECTED_EXTERNAL_URI`; internal, fragment, diff, and mailto routes intentionally take their corresponding non-external handlers. Raw observations are in `verification-agent/regression-observations.txt`.

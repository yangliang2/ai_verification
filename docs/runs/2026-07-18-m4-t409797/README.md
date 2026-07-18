# M4 T409797 replacement case

## Eligibility and source

- Upstream task: T409797, “Some lego messages in the Activity screen”; snapshot 2026-07-18: Open, unassigned, Android backlog.
- Replacement reason: T337177 failed admission because the current-base image journey could not produce a valid oracle; see `../2026-07-18-m4-t337177-exclusion/README.md`.
- Isolated worktree: `/Users/peter/hosts/wikipedia-t409797`
- Frozen base: `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- Candidate commit: `cd57c06f0804c8411ec182e99751fceb5cf7a86f`

## Candidate behavior

The Activity modules now use invariant labels (`Edits this month`, `Edits last month`, `Total edits`, `Thanks`, `Edits`, and `Views on articles you've edited`) instead of plural resources selected from the displayed count. This removes runtime concatenation assumptions about number placement and morphology.

## Build and deployment

- Command: `./gradlew --offline --no-daemon :app:assembleFdroidDebug`
- Result: BUILD SUCCESSFUL, 66 actionable tasks, 23s.
- APK: `app/build/outputs/apk/fdroid/debug/app-fdroid-debug.apk`
- APK SHA-256: `a67fb37b68847ded17c975410d81d27078f8ba17582d9b476f8bd70556179dfe`
- Package/version: `org.wikipedia`, `50594-fdroid-2026-07-18`
- Install: `adb -s emulator-5554 install -r ...` → `Success`
- Installed identity: `versionCode=50594`, `versionName=50594-fdroid-2026-07-18`.

## Primary Journey and conclusion

- Journey: complete first-run setup, open bottom-navigation `Activity`, and inspect the rendered Activity state.
- Observed UI: `Log in or create an account to view your activity on the Wikipedia app`.
- Oracle: target count-dependent Activity labels were not rendered because the unauthenticated fixture has no Activity data.
- Local conclusion: `non_accountable` (the candidate build and source are valid, but this device/content condition cannot adjudicate the target behavior).

## Known gap

The current emulator’s unauthenticated Activity screen did not provide a data fixture for the exact T409797 labels. No account or upstream interaction was introduced. This is recorded as a fail-closed non-accountable case, not as evidence that the upstream task is fixed.

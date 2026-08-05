# #112 runtime-probe admission preflight

This is a preflight-only record for the next bounded runtime probe. It does
not start a formal lane, install an APK, drive the emulator, or produce a
runtime finding.

## Result

Admission is **rejected before formal invocation**:

- `admitted=false`
- `formal_denominator=false`
- `side_effects=false`
- The Android CLI, API-35 AVDs, and one connected emulator are available.
- The existing lifecycle fixture builds successfully, but it is not the
  synchronous-weather target.
- The target `bench/discovery-fixtures/synchronous-weather` is source-only: it
  has no Gradle project and no Android manifest. Substituting the lifecycle
  fixture would change the target and is not allowed.

## Exact commands and results

Commands ran in the clean `m7-112-runtime-admission` worktree at commit
`13f9b3031a9a948a48e493470c8f1fcf1a6f0977`.

```text
android --version
1.0.15498356

android info
sdk: /opt/homebrew/share/android-commandlinetools
version: 1.0.15498356

android emulator list
aiverify_issue70_api35
aiverify_api35
aiverify_tablet_api35

adb devices -l
emulator-5554 device product:sdk_gphone64_arm64 model:sdk_gphone64_arm64 device:emu64a

android describe --project_dir bench/fixtures/lifecycle-recovery-app
gradlew completed successfully

./bench/fixtures/lifecycle-recovery-app/gradlew --offline -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug
BUILD SUCCESSFUL in 2s
33 actionable tasks: 33 executed

shasum -a 256 bench/fixtures/lifecycle-recovery-app/app/build/outputs/apk/debug/app-debug.apk
80588d561622dba6c586d4ff033697a95f211065d361a30afeb3b727bde8bc9c

target fixture shape check
AndroidManifest.xml: missing
Gradle project: missing
```

Tool/runtime: Android CLI `1.0.15498356`, SDK path above, API-35 emulator
serial `emulator-5554`, Gradle offline build. No `android run`, APK install,
Journey, screenshot, layout, logcat, or manual UI action was performed.

## Durable artifacts and next gate

- `preflight.json`: machine-readable admission decision and identities.
- The next implementation must add a buildable Android adapter for the frozen
  synchronous-weather source fixture, then freeze the runtime manifest, APK,
  Run Spec, oracle, abort boundary, and evidence identity before any formal
  device side effect.
- The existing lifecycle fixture remains only a build-system reference; it is
  not evidence for the weather-service temporal risk.

Claim boundary: environment admission only. This record makes no Android
runtime, ANR, defect-detection, benchmark-rate, or project-completeness claim.

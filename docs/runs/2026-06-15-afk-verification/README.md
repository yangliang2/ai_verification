# 2026-06-15 AFK Verification Run Record

This record was added after the initial issue closure comments to make the AFK pass auditable without relying on chat history.

Related GitHub Issues:
- Parent PRD: https://github.com/yangliang2/ai_verification/issues/1
- Completed AFK implementation issues: #2, #3, #4, #5, #6, #7
- Left open by design: #8, #9

## Scope

Completed the agent-ready MVP implementation slice from PRD #1:
- Prove the Wikipedia Android host can build and deploy through Android CLI.
- Add runner contracts for Run Spec, Codex CLI backend, Android evidence checkpoints, Journey segment boundaries, system event injection, and L2 smoke verdicts.
- Stop before HITL Goldset semantic work (#8/#9).

## Environment

Repository:
- Workspace: `/Users/peter/projects/ai_verfication`
- Host app: `/Users/peter/hosts/wikipedia`
- Host app commit: `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`

Tools:
- Android CLI: `1.0.15498356`
- Codex CLI: `codex-cli 0.139.0`
- ADB: `Android Debug Bridge version 1.0.41`, `37.0.0-14910828`
- Java: `openjdk version "17.0.19" 2026-04-21`
- Gradle: `9.5.1`
- Emulator/device: `emulator-5554 device`

Gradle details:
```text
Gradle 9.5.1
Kotlin:        2.3.20
Groovy:        4.0.29
Launcher JVM:  17.0.19 (Homebrew 17.0.19+0)
OS:            Mac OS X 26.3 aarch64
```

## Commands And Results

Host clone:
```bash
mkdir -p /Users/peter/hosts
git clone --depth 1 https://github.com/wikimedia/apps-android-wikipedia /Users/peter/hosts/wikipedia
```

Host build:
```bash
cd /Users/peter/hosts/wikipedia
./gradlew assembleDevDebug --no-daemon
```

Observed result:
```text
> Task :app:packageDevDebug
> Task :app:assembleDevDebug
> Task :app:createDevDebugApkListingFileRedirect

BUILD SUCCESSFUL in 9m 48s
77 actionable tasks: 77 executed
Configuration cache entry stored.
```

APK discovery:
```bash
find /Users/peter/hosts/wikipedia/app/build/outputs -name '*.apk' -print
```

Result:
```text
/Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk
```

Device check:
```bash
adb devices
```

Result:
```text
List of devices attached
emulator-5554	device
```

APK metadata:
```bash
/opt/homebrew/share/android-commandlinetools/build-tools/36.0.0/aapt dump badging \
  /Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk | \
  rg "package:|application-label:|launchable-activity"

/opt/homebrew/share/android-commandlinetools/cmdline-tools/latest/bin/apkanalyzer manifest application-id \
  /Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk
```

Result:
```text
package: name='org.wikipedia.dev' versionCode='50594' versionName='50594-dev-2026-06-15' platformBuildVersionName='16' platformBuildVersionCode='36' compileSdkVersion='36' compileSdkVersionCodename='16'
application-label:'Wikipedia Dev'
org.wikipedia.dev
```

Android CLI deploy:
```bash
android run \
  --apks=/Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  --device=emulator-5554 \
  --activity=org.wikipedia.DefaultIcon
```

Result:
```text
App loaded: org.wikipedia.dev
Debuggable: true
Selected component: org.wikipedia.DefaultIcon
Installing APKs: /Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk
Installation completed successfully
Executing: Launching Activity for org.wikipedia.dev
Activation completed successfully
```

Evidence capture:
```bash
mkdir -p /tmp/aiverify-wikipedia-smoke-20260615
android layout --device=emulator-5554 --pretty -o=/tmp/aiverify-wikipedia-smoke-20260615/layout.json
android screen capture -o=/tmp/aiverify-wikipedia-smoke-20260615/screen.png
android screen capture --annotate -o=/tmp/aiverify-wikipedia-smoke-20260615/screen-annotated.png
adb -s emulator-5554 logcat -d -t 200 > /tmp/aiverify-wikipedia-smoke-20260615/logcat-tail.txt
```

Observed capture results:
```text
Layout tree written to /tmp/aiverify-wikipedia-smoke-20260615/layout.json
Screenshot written to /tmp/aiverify-wikipedia-smoke-20260615/screen.png
Screenshot written to /tmp/aiverify-wikipedia-smoke-20260615/screen-annotated.png
```

Layout content check:
```bash
rg -n "Wikipedia|All the world's knowledge|Learn more" \
  docs/runs/2026-06-15-afk-verification/artifacts/layout.json
```

Result:
```text
11:    "content-desc": "Wikipedia",
21:    "text": "Wikipedia is a free online encyclopedia with 65 million articles collaboratively written and maintained in more than 300 languages by a community of volunteers.",
26:    "text": "Learn more about Wikipedia",
```

Local test verification:
```bash
.venv/bin/pytest
```

Result:
```text
........................................................................ [ 42%]
........................................................................ [ 84%]
..........................                                               [100%]
170 passed in 4.95s
```

Package metadata parse check:
```bash
.venv/bin/python -c "import tomllib, pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text()); print('pyproject ok')"
```

Result:
```text
pyproject ok
```

## Implementation Mapping

#3 Run Spec dry-run:
- `src/aiverify/runner/run_spec.py`
- `tests/runner/test_run_spec.py`

#4 Codex CLI backend contract:
- `src/aiverify/runner/codex_backend.py`
- `src/aiverify/runner/journey_result_schema.json`
- `tests/runner/test_codex_backend.py`

#5 Android evidence checkpoints:
- `src/aiverify/runner/evidence.py`
- `tests/runner/test_evidence.py`
- Real artifacts in `docs/runs/2026-06-15-afk-verification/artifacts/`

#6 Journey segment boundaries:
- `src/aiverify/runner/journey.py`
- `src/aiverify/runner/system_events.py`
- `src/aiverify/harness/device/controller.py`
- `tests/runner/test_journey.py`
- `tests/runner/test_system_events.py`
- `tests/harness/test_device_controller.py`

#7 L2 verdict from Android layout JSON:
- `src/aiverify/runner/verdict.py`
- `tests/runner/test_verdict.py`

Packaging hardening:
- `pyproject.toml` now includes package data for planner, oracle, and runner JSON schemas.

Documentation and agent setup:
- `AGENTS.md`
- `CONTEXT.md`
- `docs/agents/`
- `docs/adr/0001-android-cli-first-execution-base.md`
- `docs/adr/0002-codex-cli-as-verification-agent-backend.md`

## Artifact Inventory

Repo-local artifacts:

| Artifact | Size/type | SHA-256 |
| --- | --- | --- |
| `artifacts/layout.json` | JSON, 796B | `37197e3baa39e125dad0570eaeff3cb91b2871e9a08c085e846bbf856a8f7a27` |
| `artifacts/logcat-tail.txt` | ASCII text, 31K | `6bf9a9efc4715030abb1e08c2bbc76185766431259cb703a5b72f34d99022b14` |
| `artifacts/screen.png` | PNG, 1080x2400 | `a6638daac63c571c52d0a5534f17200235f72143cc1cb5e9a38fb81143c3dc4f` |
| `artifacts/screen-annotated.png` | PNG, 1080x2400 | `59cbdd8f3312d2bd594838489291aa2cf42d24523c6a5a0388421b98abe6c466` |

External artifact not copied into this repo because of size:

| Artifact | Size | SHA-256 |
| --- | --- | --- |
| `/Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk` | 115M | `cf882666ecab7b4ad3362e5580ef3e692062d3958045b103e0c43a6014ee32e9` |

## Known Gaps

- This run record was created retroactively after the original issue closing comments.
- The full Gradle stdout/stderr stream was not persisted at execution time; this record contains the observed success tail and measured duration.
- Evidence screenshots/logcat were originally captured under `/tmp` and then copied into `docs/runs/2026-06-15-afk-verification/artifacts/`.
- #8 and #9 were intentionally not implemented; they require human Goldset semantic work.
- The runner contracts are tested and the Android host deploy path is real-emulator verified, but a full defect-injected Goldset end-to-end run is still pending #8/#9.

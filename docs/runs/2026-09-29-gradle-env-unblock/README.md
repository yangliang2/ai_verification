# 2026-09-29 Corporate-network Gradle unblock (m7 lane)

Issue: #226 (test-side hardening that follows from this record)

## Scope

Host-only environment work that removed the last blocker for
`tests/bench/test_m7_runtime_probe.py` on a corporate-network macOS host.
No repository code changes were made. Three stacked environment blockers were
diagnosed and fixed:

1. The Gradle wrapper distribution download is blocked by the corporate TLS gateway.
2. AGP 9.0.1 plugin and dependencies are absent from the local Gradle cache.
3. `apkanalyzer` (Android SDK cmdline-tools) is missing from `PATH`.

## Blockers, Root Causes, Fixes

### 1. Gradle 9.1.0 distribution download (PKIX)

- Symptom: `./gradlew` fails fetching `gradle-9.1.0-bin.zip`; the redirect chain
  `services.gradle.org` -> `github.com/gradle/gradle-distributions` ->
  `release-assets.githubusercontent.com` fails TLS with `PKIX path building failed`.
- Root cause: the corporate gateway (`CN=WebGW, O=G-BSM, L=oppoit, C=CN`)
  performs TLS interception on `github.com`; the Temurin 17 default truststore
  does not contain the corporate CA.
- Fix: one-time download using the pre-existing user truststore
  `$HOME/.gradle/cacerts-with-webgw` (created by the user's other working line
  on 2026-09-29; gateway leaf fingerprint verified against the system CA):

  ```bash
  JAVA_TOOL_OPTIONS="-Djavax.net.ssl.trustStore=$HOME/.gradle/cacerts-with-webgw -Djavax.net.ssl.trustStorePassword=changeit" \
    ./gradlew --version
  ```

- Result: `gradle-9.1.0-bin.zip` (134,528,013 bytes) plus extracted distribution
  and `.zip.ok` in `~/.gradle/wrapper/dists/gradle-9.1.0-bin/9agqghryom9wkf8r80qlhnts3/`.
  Subsequent wrapper runs hit the cache; no trust configuration is needed again.

### 2. AGP 9.0.1 and dependencies absent from the Gradle cache

- Symptom: offline build fails with
  `Plugin [id: 'com.android.application', version: '9.0.1'] was not found`
  (cached versions were 8.13.2 / 8.2.2 / 8.9.2 / 9.2.1).
- Root cause: `bench/fixtures/lifecycle-recovery-app` pins AGP `9.0.1`
  (`gradle/libs.versions.toml`); it had never been downloaded on this host.
- Fix: one online pre-warm build (with the same truststore) populated
  `~/.gradle/caches`:

  ```bash
  JAVA_TOOL_OPTIONS="-Djavax.net.ssl.trustStore=$HOME/.gradle/cacerts-with-webgw -Djavax.net.ssl.trustStorePassword=changeit" \
    ./gradlew --no-daemon -p . :app:assembleDebug -PtemporalDelayMs=0
  ```

- Result: `BUILD SUCCESSFUL in 15m 42s`. Both variants then rebuilt in a fully
  simulated test environment (no truststore, `--offline`): 2m06s and 2s, both
  below the 300s manifest timeout.

### 3. `apkanalyzer` not on PATH

- Symptom: after the build succeeded, the m7 admission test crashed with
  `FileNotFoundError: [Errno 2] No such file or directory: 'apkanalyzer'`.
- Root cause: `src/aiverify/bench/m7_runtime_probe.py:852,880` (and
  `src/aiverify/bench/m8_formal.py:233,246`) call the binary bare. The host has
  it at `$HOME/Library/Android/sdk/cmdline-tools/latest/bin/apkanalyzer`, which
  is not on `PATH`. Historical runs resolved it from a Homebrew
  `android-commandlinetools` install (`docs/runs/2026-06-15-afk-verification/`,
  `bench/m9/m9-recovery-project-qualification-v2.json`) that has since been
  uninstalled. Test-side hardening is tracked in #226.
- Fix: appended `$ANDROID_HOME/cmdline-tools/latest/bin` to `PATH` in
  `~/.bash_profile`, `~/.zshrc`, and `~/.zprofile` (backups taken first).
- Result: `which apkanalyzer` resolves in fresh bash/zsh login shells; m7 passes
  end-to-end from a fresh login shell.

## Verification Commands And Results

```bash
# m7 lane (temporary PATH while dotfiles were not yet updated)
PATH="$PATH:$HOME/Library/Android/sdk/cmdline-tools/latest/bin" \
  .venv/bin/python -m pytest tests/bench/test_m7_runtime_probe.py
```

Result: `7 passed in 19.05s`.

```bash
# offline variant rebuilds (no truststore, simulating the test environment)
cd bench/fixtures/lifecycle-recovery-app
./gradlew --offline -p . :app:assembleDebug -PtemporalDelayMs=250   # BUILD SUCCESSFUL in 2m 6s
./gradlew --offline -p . :app:assembleDebug -PtemporalDelayMs=0     # BUILD SUCCESSFUL in 2s
```

```bash
# full suite (with PATH fix)
.venv/bin/python -m pytest
```

Result: 1536 collected; progress line = 1484 passed (`.`) + 52 skipped (`s`),
0 failed / 0 error.  Counting note: `addopts = "-q"` plus a command-line `-q`
becomes `-qq`, which suppresses the final summary line; the counts above come
from the progress-line characters and were cross-checked against
`pytest --collect-only` -> `1536 tests collected`.

```bash
# full suite re-run after this run record and the README note landed, with
# pytest's own summary line (no extra -q) and the exit code captured
.venv/bin/python -m pytest
```

Result: `1484 passed, 52 skipped, 3 warnings in 1649.97s (0:27:29)`,
exit code 0 - same totals as the quiet run above, now with a summary line.

```bash
# end-to-end from a fresh login shell, no manual PATH
bash -l -c 'cd <repo> && .venv/bin/python -m pytest tests/bench/test_m7_runtime_probe.py'
```

Result: `7 passed in 32.71s`.

## Artifacts

- `artifacts/prewarm-0.log` - online pre-warm build (AGP 9.0.1 download, `BUILD SUCCESSFUL`)
- `artifacts/offline-verify.log` - offline rebuilds of both fixture variants
- `artifacts/full-suite-verify.log` - full-suite run (progress line, 0 failed)
- `artifacts/full-suite-final.log` - full-suite re-run with summary line (exit 0)
- `checksums.sha256` - checksums for the artifacts above

## Environment

- macOS (darwin 26.1), Python 3.12.13, pytest 9.1.1, Temurin 17.0.19
- Gradle wrapper 9.1.0; fixture AGP 9.0.1, compileSdk 36, build-tools 36.0.0
- Android SDK at `$HOME/Library/Android/sdk` (cmdline-tools `latest`)
- Device/emulator not used (admission is device-independent)

## Host Changes (this machine)

- `~/.gradle/wrapper/dists/gradle-9.1.0-bin/` - distribution cached
- `~/.gradle/caches/modules-2/files-2.1/` - AGP 9.0.1 + dependencies cached
- `~/.bash_profile`, `~/.zshrc`, `~/.zprofile` - PATH extended
  (pre-change backups in `/tmp/dotfile-backup-20260929/`, ephemeral)
- Not touched: system truststore (read-only), repository files, proxies

## Compliance Notes

- TLS verification was never disabled: the corporate CA is trusted as a
  legitimate issuer via the pre-existing user truststore, with full chain
  validation (verified with `openssl verify`).
- All downloads came from official distribution endpoints
  (services.gradle.org, dl.google.com, Maven Central / Google Maven).
- No files left the machine.

## Gaps / Follow-ups

- Other hosts need the same one-time cache warm-up (blockers 1-2) and PATH
  configuration (blocker 3) unless the hardening in #226 lands.
- Re-run the online pre-warm after any fixture AGP/SDK version bump.
- The project-scope manifest (`synchronous-weather-project`) was not exercised
  on hardware; its device-side lanes remain out of scope here.

# Issue 69 network-reliability verification run

Date: 2026-07-19

Issue: `yangliang2/ai_verification#69`

Bounded conclusion: `locally_supported`

The matched baseline completed the deterministic online, offline/cache, timeout,
bounded retry, cancellation, response-ordering, and recovery contract without a
target-package crash, ANR, blank state, or error state. The injected candidate
completed the same Journey and the oracle detected both seeded faults:
`retry_storm` and `stale_response_overwrite`.

This is one local slice result. It is not a detection-rate, Goldset-wide,
production-networking, or upstream-acceptance claim.

## Provenance and identity

- Host: `https://github.com/wikimedia/apps-android-wikipedia`
- Host commit: `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- Fixture: `issue-69-network-v1`
- Shared Journey SHA-256:
  `d9ff0cdec1734f3c2cf6fba05035b2bc53c579aacf9760bba61fb9c3afd4c415`
- Device: `emulator-5554`, AVD `aiverify_api35`, API 35
- Device fingerprint:
  `google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys`
- App: `org.wikipedia.dev`, activity
  `org.wikipedia.dev.NetworkReliabilityFixtureActivity`
- App version: code `50594`, name `50594-dev-2026-07-19`
- Baseline APK SHA-256:
  `8f66479b4943e7605297368b2e78ff258682d7f786f259b4d35e4a1c45283aeb`
- Candidate APK SHA-256:
  `55a7fa39248229bafdd82f45c6144c103ec380bb715308b6387e8ce75f57959f`
- Effective Execution Identity: `effective-execution-identity.json`, referenced
  directly by both accepted `journey-result.json` records. It binds consumed Run
  Spec bytes, host worktrees/patches, APKs, target, tools, and both agent roles'
  backend/model/observation source.

The installed APK pulled from the emulator matched the corresponding local APK
for both roles. The APKs are 115–116 MiB and remain outside the repository at
`/Users/peter/hosts/wikipedia/aiverify-builds/issue-69-network-reliability/`;
their identities and installed-copy checks are durable in `evidence-summary.json`
and `artifacts/identity-and-tools.log`.

## Verification commands and results

The host patches were checked against a clean checkout at the pinned host commit:

```sh
git -C /Users/peter/hosts/wikipedia apply --check \
  /Users/peter/projects/ai_verification-issue-69/bench/goldset/patches/wikipedia-network-reliability-01-baseline-fixture.patch
git -C /Users/peter/hosts/wikipedia apply --check \
  /Users/peter/projects/ai_verification-issue-69/bench/goldset/patches/wikipedia-network-reliability-01-candidate.patch
```

Both returned zero. The two host worktrees were built with:

```sh
./gradlew assembleDevDebug --no-daemon
```

The final audited builds were successful: baseline in 5 seconds and candidate
in 6 seconds, each with 77 actionable tasks up-to-date. The clean initial build
of each variant also succeeded in 2 minutes 7 seconds with 77 tasks.

Each APK was installed and launched with the Android CLI, using the role-specific
APK path and the same component/device:

```sh
android run --device=emulator-5554 \
  --apks=<role>-app-dev-debug.apk \
  --activity=org.wikipedia.dev.NetworkReliabilityFixtureActivity
```

The Journey used Android CLI layout dumps as the primary checkpoint oracle,
`adb shell input tap` for the eight declared actions, and
`DeviceSystemEventInjector` for `network_off`, `network_on`, and every explicit
wait/postcondition. Exact action order is in the two run specs; observed
postconditions and layout paths are in each accepted attempt's `transcript.log`.
The baseline accepted run is attempt 2 and the candidate accepted run is attempt
1. Both `journey-result.json` files report 8/8 action records `PASSED`.

The local oracle was run with:

```sh
PYTHONPATH=src uv run --extra dev python \
  -m aiverify.bench.network_reliability \
  --baseline docs/runs/2026-07-19-issue-69-network-reliability/baseline/evidence-bundle.json \
  --candidate docs/runs/2026-07-19-issue-69-network-reliability/candidate/evidence-bundle.json \
  --output docs/runs/2026-07-19-issue-69-network-reliability/oracle-conclusion.json
```

It exited 0 with baseline `pass`, candidate `fail`, and candidate faults
`retry_storm` plus `stale_response_overwrite`. A separate Verification Agent
re-derived the result from the raw layouts/logs and emitted exactly one
machine-readable conclusion: `verification-agent/conclusion.json`.

Repository verification:

```sh
PYTHONPATH=src uv run --extra dev pytest -o addopts='' -q \
  tests/bench/test_network_reliability.py \
  tests/runner/test_run_spec.py tests/runner/test_system_events.py
PYTHONPATH=src uv run --extra dev pytest -o addopts='' -q
uv run --extra dev python -m compileall -q src tests
git diff --check -- . \
  ':(exclude)docs/runs/2026-07-19-issue-69-network-reliability/**'
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-19-issue-69-network-reliability
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-19-issue-69-network-reliability --verify
```

Results: targeted tests 114 passed in 0.21 seconds; full suite 577 passed in
16.92 seconds; compileall and the scoped source diff check returned zero. Raw
Android/build/test artifacts are excluded from the whitespace check because they
preserve source-tool output byte-for-byte and are covered by the checksum manifest.
Python was 3.11.15 and
pytest was 9.0.3. Android CLI was 1.0.15498356, adb was 37.0.0, Gradle was
9.5.1, Kotlin was 2.3.20, and Java was 17.0.19.

## Artifact inventory

- `artifacts/build/`: final baseline and candidate Gradle logs.
- `artifacts/tests/`: targeted/full pytest logs and static/oracle command log.
- `artifacts/tdd/`: 22 red/green or strengthening cycles, including the live
  crash-marker false-positive regression and malformed-evidence fail-closed case.
- `artifacts/identity-and-tools.log`: APK install/pull hashes, package/version,
  device identity, and tool versions.
- `baseline/attempt-2/` and `candidate/attempt-1/`: accepted raw layout trees,
  structured logcat, system-event transcripts, and annotated recovery screenshots.
- `baseline/attempt-1/`: quarantined exploratory evidence; it is not consumed by
  either bundle or conclusion because the action driver duplicated the online tap.
- `baseline/evidence-bundle.json` and `candidate/evidence-bundle.json`: normalized
  machine-readable oracle inputs.
- `oracle-conclusion.json`: final local fail-closed verdict.
- `oracle-conclusion-initial-false-positive.json`: retained diagnostic proving the
  original generic `AndroidRuntime` crash matcher was rejected and regression-tested.
- `verification-agent/`: the independent agent's single conclusion and audit notes.
- `evidence-summary.json`: concise matched identity and outcome inventory.
- `effective-execution-identity.json`: checksum-bound attempt and agent identity.
- `checksums.sha256`: SHA-256 inventory for every other run-record file.

The two accepted recovery screenshots were visually inspected and show populated
`recovered-v3` content. Layout trees provide the semantic evidence at every
checkpoint; screenshots were intentionally not duplicated for every state.

## Known gaps and risks

- The fixture is deterministic and debug-only. It validates this harness/oracle
  slice, not real Wikipedia networking or arbitrary timing behavior.
- APK binaries are external because of their size; their absolute location and
  local/installed SHA-256 identities are recorded above.
- The accepted transcripts preserve observed commands/results rather than shell
  tracing every `adb input` command. The immutable run specs, layout sequence,
  structured app markers, and system-event postconditions provide the audit chain.
- The first baseline attempt is quarantined, not silently discarded. Only baseline
  attempt 2 and candidate attempt 1 feed the evidence bundles.

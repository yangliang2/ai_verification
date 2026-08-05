# #112 M7-R1 bounded synchronous-critical-path runtime probe

This run is the first local Android runtime slice after M7's offline
qualification.  It binds the frozen `synchronous-weather-v1` source fixture to
the buildable `TemporalActivity` adapter, a matched 250 ms delay/control pair,
the existing Run Spec, runner, terminal `ExecutionRecord`, effective execution
identity, evidence checkpoints, and the bounded temporal oracle.

## Result

Admission passed and the formal population is exactly six Change Mode lanes:

| cell | repetitions | accountable | local oracle conclusion |
| --- | ---: | ---: | --- |
| change-defect (250 ms dependency delay) | 3 | 3/3 | 3/3 `locally_supported` |
| change-control (0 ms dependency delay) | 3 | 3/3 | 3/3 `locally_rejected` |

All six lanes used one attempt and zero retries.  Each lane has a terminal
`ExecutionRecord`, complete `execution-provenance.json`, runner `verdict.json`,
and an auditor-only `oracle.json` written only after the terminal identity was
validated.  The oracle observed the expected `main` caller thread and
`fixture-data` summary; defect latency was 251–253 ms against the preregistered
200 ms bound, while control latency was 0 ms.

## Exact commands and environment

Commands were run from the clean `m7-112-runtime-admission` worktree at source
commit `0da6d57a5245e9f916d9508d779d5f8a01ff140b`; the implementation files were
then present as the uncommitted input captured by each lane's host patch.

```text
android --version
1.0.15498356

adb version
Android Debug Bridge version 1.0.41
Version 37.0.0-14910828

adb devices -l
emulator-5554 device product:sdk_gphone64_arm64 model:sdk_gphone64_arm64 device:emu64a

./bench/fixtures/lifecycle-recovery-app/gradlew --offline -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug -PtemporalDelayMs=250
BUILD SUCCESSFUL in 409ms; 34 actionable tasks (1 executed, 5 from cache, 28 up-to-date)

./bench/fixtures/lifecycle-recovery-app/gradlew --offline -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug -PtemporalDelayMs=0
BUILD SUCCESSFUL in 377ms; 34 actionable tasks (1 executed, 5 from cache, 28 up-to-date)

uv run --with jsonschema --with pyyaml python -m compileall -q src tests/bench/test_m7_runtime_probe.py
uv run --with pytest --with jsonschema --with pyyaml pytest -q tests/bench/test_m7_runtime_probe.py
5 passed

uv run --with pytest --with jsonschema --with pyyaml pytest -q
exit 0; 766 tests collected and passed

uv build --wheel --out-dir /tmp/m7-wheel
Successfully built aiverify-0.1.0-py3-none-any.whl
wheel SHA-256: d908c524545ec1cc6683c003425088b7367b30376470a77c5577d6c2fa93eb21
```

For each lane the harness first recorded an Android CLI admission deployment
(`android run --device=emulator-5554 --apks=<immutable-admitted-apk>
--activity=dev.aiverify.lifecyclefixture.TemporalActivity --type=ACTIVITY`),
then invoked the existing Python runner.  The runner's Codex journey used
`codex-cli 0.144.6`; its exact JSONL events and invocation identity are under
each lane directory.  The target was API 35 AVD `aiverify_api35`, model
`sdk_gphone64_arm64`, locale `zh-Hans-CN`, portrait.  The fixture declares no
`android.permission.INTERNET`; network state was not toggled.

## Evidence inventory

The machine-readable admission and population receipt is
[`preflight.json`](preflight.json).  `lanes-v3/` contains six lane directories,
each with:

- `execution-record.json` and `execution-provenance.json`;
- `live-validation-gate.json`, `admission-deployment.json`, and the consumed
  Run Spec snapshot;
- `verdict.json`, Codex journey result/events/identity, and action lineage;
- one screenshot (`screen.png`), layout dump (`layout.json`), logcat capture
  (`logcat.txt`), capture manifest, and commands receipt;
- auditor `oracle.json` and lane `checksums.sha256`.

There are 6 screenshots, 6 layouts, 6 logcats, 6 terminal records, and 6
effective identity receipts.  `build/` contains the two immutable admitted APK
snapshots:

- defect: `edb5ef838baaf81379b3a0b9c4e2f99441a6342c7a80dd9831092ab7f801c0fb`;
- control: `efed5750572e7c81a74664458bbd903bd4a2a3e2cd1ef49c18ccab835964763d`.

The built Python wheel is [`aiverify-0.1.0-py3-none-any.whl`](aiverify-0.1.0-py3-none-any.whl)
with SHA-256 `d908c524545ec1cc6683c003425088b7367b30376470a77c5577d6c2fa93eb21`.

The root `checksums.sha256` binds this README, `preflight.json`, snapshots,
and all lane evidence.  The lane checksums remain separately authoritative for
the runner-owned evidence directories.

## Fail-closed observations and gaps

Two earlier attempts are retained outside the formal population in `lanes/`
and `lanes-v2/`: six lanes rejected before device invocation because the APK
identity changed across a fresh Gradle rebuild; six lanes rejected because the
runner's live gate correctly found no installed app; and six lanes rejected
because putting runner artifacts inside the worktree caused host identity
drift.  The final run addresses these by reusing immutable admission snapshots,
staging the app before the existing gate, and running with an artifact root
outside the worktree before copying the completed evidence here.

This is a local fixture result only.  It does not claim ANR rate, false-positive
rate, OEM/SystemUI behavior, physical-device coverage, project-mode coverage,
or general Android detection capability.  No upstream project state was
changed.

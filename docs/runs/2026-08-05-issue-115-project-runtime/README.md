# #115 M7-R2 bounded Project Mode synchronous-critical-path runtime probe

This run closes the runtime seam that remained after the offline M7
qualification and M7-R1 Change Mode slice.  A complete `ProjectTarget` packet
with no diff is passed through context expansion, synchronous-risk derivation,
Attack Plan admission, Run Spec compilation, Android execution, and the same
bounded temporal oracle used by #112.

## Result

The formal population is exactly six Project Mode lanes: three defect and three
matched control repetitions.  All six are terminal and accountable, with one
attempt per lane and zero retries.

| cell | repetitions | accountable | local oracle conclusion | observation |
| --- | ---: | ---: | --- | --- |
| `project-defect` | 3 | 3/3 | 3/3 `locally_supported` | 250 ms delay; main-thread latency 250–255 ms |
| `project-control` | 3 | 3/3 | 3/3 `locally_rejected` | 0 ms delay; 0 ms latency |

Every formal lane has a terminal `ExecutionRecord`, complete
`execution-provenance.json`, runner verdict, Codex journey identity, one
screenshot, layout dump, logcat, oracle, and lane checksum inventory.  The
three initial `gpt-5` alias attempts are retained under `lanes-v1/` as
non-accountable fail-closed evidence and are excluded from the denominator;
the backend reported the Codex model-cache schema error before a formal result.

## Project Mode and leakage boundary

`project-target.json` is a validated `ProjectTarget` with no `diff`, `diff_ref`,
or outcome field.  Admission re-runs both project campaign entries through
`ProjectTarget → Quality Context Graph → Risk Hypothesis → Attack Plan → Run
Spec`, and checks that the compiled and frozen Run Specs have no diff or
outcome labels.  The machine-readable result is in
[`project-leakage-audit.json`](project-leakage-audit.json).

The auditor-only runtime manifest binds the matched build variants and does not
feed their labels or expected outcomes to the verifier-facing project packet.

## Exact commands and environment

Commands were run from the clean `m7-115-project-runtime` worktree at the
merged M7-R1 source (`59ea195`).  The formal run used the immutable APK
snapshots captured by the admission preflight and the Codex CLI backend model
`gpt-5.6-sol`.

```text
uv run --with pytest --with jsonschema --with pyyaml pytest -q \
  tests/bench/test_m7_runtime_probe.py tests/bench/test_m6_cohort.py \
  tests/discovery/test_campaign.py
30 passed

uv run --with ruff ruff check src/aiverify/bench/m7_runtime_probe.py
all checks passed

./bench/fixtures/lifecycle-recovery-app/gradlew --offline \
  -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug \
  -PtemporalDelayMs=250
BUILD SUCCESSFUL in 515ms; 34 actionable tasks (1 executed, 5 from cache, 28 up-to-date)

./bench/fixtures/lifecycle-recovery-app/gradlew --offline \
  -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug \
  -PtemporalDelayMs=0
BUILD SUCCESSFUL in 496ms; 34 actionable tasks (1 executed, 5 from cache, 28 up-to-date)

uv run --with pytest --with jsonschema --with pyyaml pytest -q
768 passed in 23.34s
```

Runtime environment: Android CLI `1.0.15498356`; adb `1.0.41`, platform
`37.0.0-14910828`; Codex CLI `0.144.6`, model `gpt-5.6-sol`; uv `0.11.7`;
the `uv run` test/build environment uses CPython `3.11.15`.  Target device is
`emulator-5554`, AVD `aiverify_api35`, API 35, model
`sdk_gphone64_arm64`, locale `zh-Hans-CN`, portrait.  APK manifest permission
inspection found only `android.permission.WAKE_LOCK`; no network state was
toggled.

## Evidence inventory and checksums

- [`runtime-probe.json`](../../../bench/runtime-probes/synchronous-weather-project/runtime-probe.json)
  — frozen Project Mode manifest and campaign contract.
- `manifest/` — committed snapshots of the runtime manifest, ProjectTarget,
  neutral spec, and both no-diff Run Specs consumed by the run.
- [`preflight.json`](preflight.json) — source, target, campaign, tool, device,
  build, APK, Run Spec, lane, and formal-population receipt.
- [`project-leakage-audit.json`](project-leakage-audit.json) — no-diff and
  no-outcome-label checks for the verifier-facing ProjectTarget path.
- `lanes-v2/` — six formal lane directories, each containing the terminal
  record, effective identity, deployment/live gate, Run Spec snapshot, verdict,
  Codex events/identity, screenshot, layout, logcat, oracle, and checksums.
- `lanes-v1/` — three excluded non-accountable attempts and their partial
  receipts, retained for auditability.
- `build/project-defect.apk` SHA-256
  `b8776969282e9fea84056614222b5de1b2183bc0bbffe5ce24588406ec6134f4`.
- `build/project-control.apk` SHA-256
  `3efb8acdce28829b1987dd9713a9a924c369a5ff5a03616561781fd5a0a202b0`.
- `aiverify-0.1.0-py3-none-any.whl` SHA-256
  `0a8cbc37d5c0fbc8de04d9de586288d48ccf32c3707734d4ab444afa3aedc0bc`.

The root `checksums.sha256` binds this README, preflight, leakage audit,
manifest snapshots, APK snapshots, the Python wheel, and all formal evidence
(139 entries).  Each formal lane
has a separate checksum inventory.  The original runtime capture was under
`/private/tmp/m7-r2-project-runtime-v2.JdhdFe`; the committed lane/build files
are byte-for-byte copies.  No external project state was changed.

## Claim boundary

This is bounded local support for one complete ProjectTarget packet, the
synchronous weather adapter, one API-35 emulator profile, and the preregistered
200 ms main-thread temporal contract.  It does not claim project completeness,
ANR rate, false-positive rate, OEM/SystemUI or physical-device behavior, a
combined Change/Project denominator, general Android coverage, or upstream
acceptance.

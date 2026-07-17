# Issue #60 — ExecutionRecord and fail-closed system events

Issue: [#60](https://github.com/yangliang2/ai_verification/issues/60), child
of [#58](https://github.com/yangliang2/ai_verification/issues/58).

## Outcome

The public Run Spec runner now establishes one durable `ExecutionRecord` before
preflight or device/host side effects, atomically finalizes every handled path,
and treats a durable `in_progress` record as abandoned and non-accountable.
System-event exceptions, subprocess timeouts, non-zero exits, and stable
event-specific postcondition failures all converge on canonical
`system_event_error`; later Journey segments and L1/L2/L3 accounting stop.

The controlled API 35 emulator probes passed the required pair:

- Successful rotate: final relative-path `success-attempt-4`, attempt ID
  `23d392d5-b9e5-4b60-8bf5-08c399c4e66d`, completed/accountable, outer exit 0,
  `accelerometer_rotation=0`, `user_rotation=1`, portrait 1080×2400 before and
  landscape 2400×1080 after, L1 inconclusive / L2 pass / L3 not run.
- Forced event failure: `failed-attempt`, attempt ID
  `498b3cba-1515-4ba5-97d7-02d6d454cf2a`, adb return 255, canonical
  `system_event_error`, interrupted/non-accountable, outer exit 2, only
  `after-segment-0` retained, no `after-event-0`, and L1/L2/L3 all `not_run`.

`success-attempt-3` is the primary visual success evidence because both its
portrait and landscape frames are complete and coherent. The final attempt 4
proves the relative artifact-path regression fix; its post-event frame is
normal, while its pre-event screenshot contains a transient black/partially
rendered app frame. That visual anomaly is disclosed rather than hidden and did
not affect the layout-based action, rotation postcondition, or event accounting.

## Attempt lineage

| Directory | Attempt ID | Lifecycle / reason | Exit | Result |
| --- | --- | --- | ---: | --- |
| `success-attempt` | `cff4d1b1-5cc4-4c11-9e67-a33248472dac` | interrupted / `journey_backend_error` | 2 | Preserved discovery attempt; relative Codex result path exposed a cwd bug. |
| `success-attempt-2` | `54b53211-be1a-4eab-aa24-82fa63555ce2` | completed | 0 | First successful rotate with an absolute artifact path. |
| `success-attempt-3` | `ab86e8c1-fe25-43b4-bcc8-fc4349cfefae` | completed | 0 | Successful rotate with direct Journey/checkpoint record references; primary visual pair. |
| `failed-attempt` | `498b3cba-1515-4ba5-97d7-02d6d454cf2a` | interrupted / `system_event_error` | 2 | Deliberate unknown permission, pre-event evidence only, no oracle accounting. |
| `success-attempt-4` | `23d392d5-b9e5-4b60-8bf5-08c399c4e66d` | completed | 0 | Final relative-path success after the backend path fix. |

Every retry used a new directory and UUID. No prior `execution-record.json`,
verdict, gate, or artifact directory was overwritten.

## Implementation mapping

- `src/aiverify/runner/execution_record.py`: exclusive durable establishment,
  invariant validation, atomic terminal replace, create-only JSON artifacts,
  and abandonment/accountability helpers.
- `src/aiverify/runner/cli.py`: establishes before preflight; finalizes success,
  preflight rejection, interruption, setup/Journey/oracle/output errors; keeps
  oracle outcomes absent for non-accountable paths; directly references retained
  evidence.
- `src/aiverify/runner/journey.py`: canonical `system_event_error` propagation
  with partial flow and pre-event checkpoint retention.
- `src/aiverify/runner/system_events.py`, `src/aiverify/harness/device/{adb.py,controller.py}`:
  bounded adb subprocesses, non-zero checking, and stable postconditions for
  rotation, dark mode, network requested state, permission revocation,
  background kill, and process death.
- `src/aiverify/bench/m3_reliability.py`: schema-v2 attempt metadata binds
  `attempt_id + execution-record.json`; the record is authoritative, terminal
  contradictions fail closed, and schema-v1 historical evidence remains
  verdict-compatible.
- `src/aiverify/runner/codex_backend.py`: resolves output paths before moving the
  subprocess into the host workdir.
- Tests: `tests/runner/test_execution_record.py`, `test_cli.py`,
  `test_codex_backend.py`, `test_journey.py`, `test_system_events.py`,
  `tests/harness/test_device_controller.py`, and
  `tests/bench/test_m3_reliability.py`.

## Exact verification commands and results

Issue-focused suite:

```bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p \
  .venv/bin/pytest -p no:cacheprovider -o addopts='' -q \
  tests/runner/test_execution_record.py \
  tests/runner/test_cli.py \
  tests/runner/test_codex_backend.py \
  tests/runner/test_journey.py \
  tests/runner/test_system_events.py \
  tests/harness/test_device_controller.py \
  tests/bench/test_m3_reliability.py \
  tests/bench/test_m3_rebaseline_audit.py
```

```text
235 passed in 7.06s
real 7.26
```

Complete suite:

```bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p \
  .venv/bin/pytest -p no:cacheprovider -o addopts='' -q
```

```text
479 passed in 12.12s
real 12.28
```

Static and immutability checks:

```bash
.venv/bin/python -m compileall -q src tests
git diff --check -- \
  CONTEXT.md HANDOFF.md src tests \
  docs/runs/2026-07-17-issue-60-execution-record-system-event/README.md \
  docs/runs/2026-07-17-issue-60-execution-record-system-event/environment.json \
  docs/runs/2026-07-17-issue-60-execution-record-system-event/probe-summary.json \
  docs/runs/2026-07-17-issue-60-execution-record-system-event/process-results.md \
  docs/runs/2026-07-17-issue-60-execution-record-system-event/success-run-spec.yaml \
  docs/runs/2026-07-17-issue-60-execution-record-system-event/failed-run-spec.yaml
git diff --exit-code d237db60364903619eddf312888c86e20a7bce40 -- \
  bench/goldset/m3-reliability-slice.yaml \
  bench/goldset/m3-reliability-slice-v2.yaml \
  docs/runs/2026-07-13-m3-*-reliability \
  docs/runs/2026-07-15-m3-v2-*-reliability
PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums \
  --verify docs/runs/2026-07-17-issue-60-execution-record-system-event
```

All exited 0. The focused M3 reliability/rebaseline subset was also independently
run by the integration agent: 82 passed in 6.83s. Historical M3 and M3 v2
manifests/evidence have no diff from the fixed point. Raw generated logcat and
JSONL evidence is preserved byte-for-byte and checksummed; it is intentionally
excluded from the whitespace-only source/document check above.

The exact public runner commands and process outputs are in
[`process-results.md`](process-results.md). No host build or install ran for this
issue; the already-installed Wikipedia package was reused.

## Environment and app identity

- macOS 26.3 arm64; Python 3.11.15; pytest 9.0.3; git 2.50.1; OpenJDK 17.0.19.
- Codex CLI 0.144.5; Android CLI 1.0.15498356; adb 1.0.41 / platform-tools
  37.0.0-14910828.
- Emulator `emulator-5554`, AVD `aiverify_api35`, API 35, fingerprint recorded
  in [`environment.json`](environment.json).
- Wikipedia host clean at `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`;
  package `org.wikipedia.dev`, activity `org.wikipedia.DefaultIcon`, version
  `50594-dev-2026-07-13` (`versionCode=50594`).
- Local APK: 121,628,105 bytes,
  SHA-256 `a3060b8c00b7addec0aa17685df0ea96892b5097289e3b51a863b6234468c2bc`.
  Installed base APK SHA-256:
  `8084dee23f7b06099b2cbfa4dc38e5ca6623a26f4519a3c222368fb2fc997dea`.

The differing local/installed APK byte hashes are recorded without asserting
they are the same artifact. Complete model/source/APK/deployment identity is
explicitly deferred to #61.

## Manual and API-35 verification

- Visually inspected success attempt 3 portrait and landscape screenshots:
  Wikipedia Community/Home feed remained coherent; dimensions changed from
  1080×2400 to 2400×1080.
- Visually inspected failure pre-event screenshot: coherent portrait Wikipedia
  Community/Home feed. Confirmed there is no post-event checkpoint directory.
- Visually inspected final relative-path success attempt 4; disclosed its
  transient pre-event black/partial frame and normal post-event landscape frame.
- API-35 network postcondition probe captured original `wifi_on=1` and
  `mobile_data=1`, observed `0/0` after `svc ... disable`, observed `1/1` after
  enable, and restored the captured original state.
- Final device restoration re-read: `accelerometer_rotation=1`,
  `user_rotation=0`, night mode `no`, `wifi_on=1`, `mobile_data=1`.

## Artifact inventory and checksums

The record contains both Run Specs, five immutable attempt directories, five
ExecutionRecords, gates, verdicts, Codex event streams/results, layout dumps,
checkpoint manifests/commands/logcat, and 14 screenshots. `probe-summary.json`
is the compact outcome index. `checksums.sha256` covers all 80 other files and
is verified with the repository checksum tool.

## Known gaps and claim boundary

- This is one controlled API 35 emulator pair, not a physical-device,
  cross-application, ColorOS, or benchmark-wide reliability claim.
- `app_to_background` and `app_to_foreground` currently validate process exit
  only. A stable foreground-state contract needs bounded polling instead of a
  one-shot parse of transient `dumpsys activity` internals.
- Network postconditions prove synchronous requested settings (`wifi_on` and
  `mobile_data`), not carrier reachability or Internet connectivity.
- The successful L2 verdict intentionally has zero product assertions; this
  probe verifies event dispatch/postcondition/evidence/accountability, not a
  Wikipedia behavior claim.
- Complete effective model/source/APK/deployment identity and a fresh 30-lane
  v3 audit remain out of scope here and are tracked by #61 and #62.

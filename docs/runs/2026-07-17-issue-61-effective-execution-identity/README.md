# Issue #61 effective execution identity

This run record validates the public Run Spec runner's checksum-bound effective
execution identity on a real API 35 emulator. The primary attempt completed and
is accounting-eligible without manual identity backfill.

## Result

- Attempt: `c4c22d1d-d44f-42a6-ad1f-2a45ea16b796`
- ExecutionRecord: schema v2, `completed`, exit `0`, accounting eligible
- Duration: 36.015 seconds
- Host: clean `wikimedia/apps-android-wikipedia` commit
  `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- APK: one pre-deploy artifact; local and installed SHA-256 both
  `a3060b8c00b7addec0aa17685df0ea96892b5097289e3b51a863b6234468c2bc`
- Deployment: Android CLI exit `0`, package `org.wikipedia.dev`, component
  `org.wikipedia.dev/org.wikipedia.DefaultIcon`
- Device: `emulator-5554`, API 35, AVD `aiverify_api35`
- Journey driver: Codex CLI 0.144.5, requested and effective model both
  `gpt-5.6-sol`; effective identity observed from the invocation's Codex session
  `turn_context`
- L3 judge: explicitly not applicable because the scenario has no L3 spec
- Provenance: independent reload audit passed for SHA-256
  `a3963cea6f637a0cab6784e9b25c3da93144d388f8bd75bdf5a380383803b31a`
- Tamper probe: recomputing the outer manifest checksum after changing captured
  host status was still rejected with `host status checksum mismatch`
- Visual check: `success-attempt/artifacts/after-segment-0/screen.png` shows a
  fully rendered Wikipedia Community home surface with visible navigation and
  content; no crash, blank frame, or system dialog is present.

## Artifact inventory

- `run-spec.yaml`: exact public runner input
- `success-attempt/execution-record.json`: authoritative attempt envelope
- `success-attempt/execution-provenance.json`: complete identity manifest
- `success-attempt/identity/`: consumed Run Spec snapshot and host patch bytes
- `success-attempt/live-validation-gate.json`: preflight result
- `success-attempt/verdict.json`: accountable oracle output
- `success-attempt/artifacts/issue-61-effective-execution-identity-segment-0/`:
  Codex event stream, identity receipt, action lineage, and structured result
- `success-attempt/artifacts/after-segment-0/`: screenshot, annotated screenshot,
  layout, logcat, commands, and capture manifest
- `environment.json`: host, tool, host-app, and emulator inventory
- `probe-summary.json`: concise machine-readable probe and audit result
- `process-results.md`: exact commands and important outputs
- `checksums.sha256`: SHA-256 inventory for every other committed run artifact

## Verification

The focused identity/runner/audit suite collected 184 tests and passed. The
complete repository suite collected 511 tests and passed in 14.93 seconds
(`user 5.54`, `sys 2.72`). `git diff --check` and Python bytecode compilation
also passed. See `process-results.md` for the exact commands.

## Known gaps and scope

- The scenario intentionally has no L3 semantic-judge specification, so the L3
  role is recorded as not applicable rather than invoked. Separate provider
  tests cover L3 effective-model receipt capture and mismatch rejection.
- Historical M3/M3 v2 packages were not rewritten. Schema-v1 ExecutionRecords
  remain readable and honestly have no newly backfilled identity.
- The Codex source session remains in the user's external Codex session store;
  the durable receipt retains its SHA-256 and the minimal contemporaneous
  `session_meta`/`turn_context` observation needed for audit, avoiding a copy of
  the potentially sensitive full session transcript.


# Issue #61 effective execution identity

This run record validates the public Run Spec runner's checksum-bound effective
execution identity on a real API 35 emulator. The primary attempt completed and
is accounting-eligible without manual identity backfill.

## Result

- Final attempt: `294732cf-1198-4a3d-9783-de7f94c208c0`
- ExecutionRecord: schema v2, `completed`, exit `0`, accounting eligible
- Duration: 72.597 seconds
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
  `87c4c7088549fdd9073ec85f7c96fbee01eb9662405973999733771055a2b79f`
- Mutation audit: all four origin, Run Spec, deployment command, and role-cwd
  mutations were rejected even after their outer checksums were recomputed
- Visual check: `success-attempt-2/artifacts/after-segment-0/screen.png` shows a
  fully rendered Wikipedia Community home surface with visible navigation and
  content; no crash, blank frame, or system dialog is present.

## Artifact inventory

- `run-spec.yaml`: exact public runner input
- `success-attempt-2/execution-record.json`: final authoritative attempt envelope
- `success-attempt-2/execution-provenance.json`: final complete identity manifest
- `success-attempt-2/identity/`: consumed Run Spec snapshot and host patch bytes
- `success-attempt-2/live-validation-gate.json`: preflight result
- `success-attempt-2/verdict.json`: accountable oracle output
- `success-attempt-2/artifacts/issue-61-effective-execution-identity-segment-0/`:
  Codex event stream, identity receipt, action lineage, and structured result
- `success-attempt-2/artifacts/after-segment-0/`: screenshot, annotated screenshot,
  layout, logcat, commands, and capture manifest
- `environment.json`: host, tool, host-app, and emulator inventory
- `probe-summary.json`: concise machine-readable probe and audit result
- `audit-mutations.py`: executable four-dimension mutation audit
- `process-results.md`: exact commands and important outputs
- `checksums.sha256`: SHA-256 inventory for every other committed run artifact

## Verification

The focused identity/runner/audit suite collected 188 tests and passed. The
complete repository suite collected 515 tests and passed in 13.51 seconds
(`user 5.86`, `sys 2.93`). `git diff --check` and Python bytecode compilation
also passed. See `process-results.md` for the exact commands.

## Known gaps and scope

- The scenario intentionally has no L3 semantic-judge specification, so the L3
  role is recorded as not applicable rather than invoked. Separate provider
  tests cover L3 effective-model receipt capture and mismatch rejection.
- Historical M3/M3 v2 packages were not rewritten. Schema-v1 ExecutionRecords
  remain readable and honestly have no newly backfilled identity.
- `success-attempt/` is the pre-review success retained for audit history.
  `success-attempt-2/` is authoritative because it was produced after closing
  the dual-review findings and includes pre-agent/final drift checks.
- The durable receipt retains only the minimal contemporaneous
  `session_meta`/`turn_context` observation and its checksum; it contains no
  private external session path or full session transcript.

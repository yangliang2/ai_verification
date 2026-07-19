# Independent audit task contract

The primary agent dispatched the following requirements through the
collaboration interface:

- Work read-only; do not edit repository files.
- Inspect the final baseline/attempt-2 and candidate/attempt-2 lanes,
  artifacts/matched-input-audit.json, the fixture/oracle code, and the
  independent-conclusion schema.
- Verify lane checksums, provenance bindings, run-relative ExecutionRecord
  references, lifecycle receipts, backup/clear/restore/cleanup receipts,
  checkpoint UI, logcats, archived/source/installed APK identity, Journey
  prompts, normalized Run Spec identity, and the exact candidate difference.
- Decide fail closed whether the disclosed docs/runs host.patch difference
  contaminates matched executable or Journey inputs.
- Treat the clean-host Codex usage-limit retry as non-accountable and never as
  product evidence.
- Return exactly one JSON object satisfying
  bench/capability-slices/lifecycle-recovery/independent-conclusion-schema.json.

The collaboration transport does not expose a byte-for-byte raw dispatch
transcript. This file records the retained task contract and does not claim to
be a raw transport transcript.

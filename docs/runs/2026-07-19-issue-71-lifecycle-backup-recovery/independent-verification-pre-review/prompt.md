You are the separate Verification Agent for GitHub issue #71. Work read-only.

Read these authoritative inputs from the repository root:

- `docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/issue-71.json`
- `bench/capability-slices/lifecycle-recovery/spec.md`
- `bench/capability-slices/lifecycle-recovery/contract.json`
- `bench/capability-slices/lifecycle-recovery/run-specs/baseline.yaml`
- `bench/capability-slices/lifecycle-recovery/run-specs/candidate.yaml`
- both final attempts under
  `docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/{baseline,candidate}/attempt-1/`

Independently audit the acceptance criteria. Do not trust summaries alone. At a
minimum, verify both `checksums.sha256` inventories; runner and ExecutionRecord
completion; provenance and APK hashes; identical Journey actions/events/assertions;
rotation, disjoint process IDs, local backup transport, package backup success,
restore token and restore success; checkpoint layout values; L1/L2 verdicts; and
the dedicated lifecycle oracle outputs. Confirm the candidate host patch is the
declared one-line migration-guard defect. Treat missing or contradictory evidence
as non-accountable.

Return exactly one JSON object matching the supplied output schema. The single
top-level `conclusion` concerns whether the local evidence supports issue #71's
implemented capability, including correct baseline restoration and accountable
candidate rejection. `locally_supported` is permitted only if every acceptance
criterion is locally evidenced. `locally_rejected` means complete evidence shows
the implementation fails the issue. `non_accountable` means required evidence is
missing or contradictory.

Do not make detection-rate, Goldset, compatibility-matrix, cloud-provider, or
upstream acceptance claims. Do not modify any repository or device state.

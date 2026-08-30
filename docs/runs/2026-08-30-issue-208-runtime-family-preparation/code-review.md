# Issue #208 — Standards and Spec Review

The implementation was reviewed with two independent passes at fixed point
`6c03f89` and implementation checkpoint `a201f54`, followed by the
remediations listed below. The final focused and repository-wide suites were
run after those remediations.

## Standards review

The review checked the family API, stage receipts, source/mapping boundary,
failure accounting, public command surface, and repository evidence rules
against `CONTEXT.md`, ADR-0005, and the runtime calibration contract.

Findings and disposition:

- The stage accepts already-materialized lane inputs, while the CLI obtains
  them through an explicit provider before writing the family stage start
  receipt. This is now documented as the source-authority boundary: the
  provider returns exact materialized inputs and does not build, inspect, or
  admit APKs. The family stage itself starts before any lane build and owns
  all build, receipt, artifact, and gate effects.
- The released #206 mapping records the same ChangeTarget source path for
  lanes 01/02. The family implementation deliberately keeps the independent
  worktree check and rejects that strict production input rather than
  weakening the acceptance invariant. This remains a documented operational
  gap requiring a fresh per-lane source mapping; substitute tests do not
  claim strict production admission.
- Shared-health reproof is fail-closed: the built-in candidate, mapping,
  vault, signer, tool, source, and recipe checks always run; an optional
  callback can only add a check and cannot replace them. Callback exceptions
  abort the family.
- Generic lane exceptions no longer fabricate a started build or attempt.
  Build counts are carried by the lane result and persisted row, and the
  interruption path intentionally remains abandoned without a terminal
  receipt.
- The canonical implementation is
  `aiverify.bench.runtime_family_preparation`. The small compatibility import
  and vocabulary aliases are retained for callers migrating from the
  one-lane preparation module; they contain no independent behavior.

## Spec review

- The initial recording tests primarily exercised a custom family preparer.
  `test_default_preparer_records_one_public_lane_handoff_per_build` now
  exercises the public default lane-to-`prepare_runtime_case` handoff with a
  recording substitute and verifies frozen order, explicit substitute policy,
  and preservation of an extra APK output. Real Gradle/tool execution remains
  outside this recording-fake issue scope.
- APK artifact discovery now scans every non-symlink APK below each source
  worktree before and after the one-lane handoff, so failed builds preserve
  all real outputs instead of two hard-coded names.
- Terminal verification now recomputes every persisted family gate from the
  candidate, mapping release, rows, receipts, and live sealed files. It also
  verifies the frozen signer metadata and exact lane artifact roots, rather
  than trusting stored `passed` values.
- The complete success, lane-local continuation, shared abort, interruption,
  byte equality/inequality, metadata, identity, signing, vault, environment,
  attempt, runtime-effect, mapping-handoff, and source gates are covered by
  public-interface tests. Failed gates preserve sealed artifacts and use only
  the four permitted row statuses.
- The durable README, machine-readable verification record, this review, and
  the checksum inventory are committed under this run directory.

## Review conclusion

The recording implementation satisfies the four-lane orchestration and
fail-closed persistence contract. Strict production preparation remains
correctly blocked by the independently identified #206 ChangeTarget path
collision until a fresh mapping/materialization is supplied; no test result
is presented as a real APK or device admission.

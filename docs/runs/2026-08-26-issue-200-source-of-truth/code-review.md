# Issue #200 two-axis code review

Review fixed point: `843c84e40197f3d401b5cd07ef6355e4d476d1a7` (the
pre-implementation branch tip). The review covered the complete implementation
diff from that point plus the final working-tree changes.

## Standards

The standards review initially found three issues:

- artifact `kind` and `path` were checked independently, allowing a manifest
  path permutation;
- the run record had a stale/untracked checksum inventory;
- the README listed this review artifact before it existed.

All three were resolved. `EXPECTED_ARTIFACT_PATHS` is now enforced for both
candidate manifests and terminal receipts in
`src/aiverify/bench/runtime_calibration.py`; the public tests cover candidate
and receipt path rebinding. The run record now includes this file and a
regenerated, verified `checksums.sha256`.

Final standards checks: no outstanding findings. Ruff, Python compilation,
`git diff --check`, the focused contract suite, and the full repository suite
all pass as recorded in `README.md` and `verification.json`.

## Specification

The specification review initially found three implementation gaps:

- claim-boundary exclusions and scope were only required to be non-empty;
- non-common JSON Schema properties were unconstrained `{}` values;
- the durable checksum/review artifacts were not yet complete.

All three were resolved. The V1 claim-boundary values are frozen in code and
covered by a rebinding regression test. All eight schemas now describe their
complete top-level fields and nested object/array types and constraints, and
their canonical schema identities are frozen and checked before documents are
validated against them. The final candidate manifest binds the updated raw and
canonical schema digests.

Final specification audit: no outstanding findings. The candidate accepts
only the frozen 28-artifact V1 set, rejects stable invalid-input reasons before
runtime side effects, and the serialized public-command tests cover acceptance,
rejection, interruption/abandonment, and receipt tampering.

## Review conclusion

Standards: 0 outstanding findings. Specification: 0 outstanding findings.
Worst final issue: none identified.

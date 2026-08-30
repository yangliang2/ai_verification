# Issue #206 code review

Review fixed point: ea50276099b592c7ae52bb77125294b54a913371

Reviewed through implementation commit b374b3a. Sources were the issue body,
AGENTS.md, CONTEXT.md, docs/agents/domain.md, ADRs 0003–0005,
docs/opencalc-runtime-calibration-v1.md, the three changed implementation
surfaces, and their tests.

## Standards

### Findings

No unresolved standards findings.

The implementation follows the repository's existing immutable dataclass,
canonical-digest, stable-error, and staged-receipt patterns. The release
writer validates before output, fsyncs the temporary bytes, commits by
exclusive hard link, and refuses replacement. The driver-facing serializer is
separate from source-authority and reducer views. The tests exercise public
release/stage APIs and preserve the no-build/no-device/no-model boundary.

Checks supporting this review:

- Ruff 0.16.5: passed for all changed Python files.
- mypy 2.3.1 with the repository's --ignore-missing-imports setting for the
  changed mapping module: no issues.
- compileall: passed.
- git diff --check: passed.
- Full suite: 1,395 passed, 1 skipped, 0 failed/errors.

### Remediation recorded during review

The first focused run exposed one standards/contract defect at
runtime_mapping.py:1647: full equality of the discovery hypothesis and plan
objects treated target-specific ChangeTarget delta/contract IDs as if they
were shared neutral fields. Commit 05d47e1 compares an explicit neutral
semantic projection while retaining the package's target-specific binding.
Commit 24ffd6d adds matching discovery-result-kind validation. Commit
9865162 terminalizes ordinary unexpected admission exceptions.

## Specification

### Criterion disposition

| # | Criterion | Disposition and evidence |
|---:|---|---|
| 1 | Four opaque lanes, frozen order and meanings | Satisfied by RUNTIME_LANE_IDS, RUNTIME_LANE_MEANINGS, release constructor, and focused lane-order assertions. |
| 2 | Source-rich package, blind projection, Run Spec, setup, and driver-plan cross-binding | Satisfied by RuntimeLaneBinding and _candidate_lane_binding, including raw/canonical digests, paths, shapes, and source request identity. |
| 3 | Four terminal admissions and leakage checks before release | Satisfied by _validate_discovery_result, re-derived leakage audits, exact cardinality/order, zero build/device/model side effects, and the final staged release. |
| 4 | One append-only atomic sealed_blind → mapping_released release | Satisfied by RuntimeMappingRelease and write_runtime_mapping_release; the final mapping and stage-terminal receipts are committed. |
| 5 | No partial, duplicate, missing, reordered, replaceable, or post-hoc release | Satisfied by strict four-item constructors, exclusive hard-link creation, order/uniqueness checks, and rejection tests. |
| 6 | Only Source Authority before preparation and pure reducer after terminal execution | Satisfied by RuntimeMappingRelease.consume: existing SourceAuthority gets the source-only view; reducer access requires typed terminal evidence; all others reject. |
| 7 | Unauthorized/digest/mutation/meaning failures remain candidate-bound | Satisfied by strict parsing, candidate identity and artifact re-verification, optional discovery re-release comparison, and tamper tests. |
| 8 | Opaque, structurally uniform driver-visible inputs | Satisfied by to_driver_visible(), leakage checks over all candidate driver documents, fixed document shape, and uniform-shape validation. |
| 9 | Source requests verifiable by existing source-authority seam without device/model work | Satisfied at this stage by the typed SourceAuthorityMapping.verify_with() hook and no resolve_host call; the focused test records all four request verifications. Concrete build/materialization consumption belongs to the subsequent preparation stage. |
| 10 | Contract/integration tests and committed run evidence | Satisfied by 55 focused tests, 1,396-test full report, staged receipts, mapping release, this review, and checksums.sha256. |

### Spec findings

No unresolved specification findings. The release is deliberately limited to
admission and disclosure; it does not claim APK preparation, runtime behavior,
device evidence, oracle reduction, or a formal benchmark result.

## Review process and final counts

Two parallel read-only review workers were started for the Standards and Spec
axes as required by the review workflow. Both stalled before producing a
report, so they were closed. The main review performed the two-axis inspection
above and ran the listed checks. Review findings: 1 implementation defect
found and fixed during review; 0 open blockers, 0 open major findings, 0 open
minor findings. Worst remaining severity: none.

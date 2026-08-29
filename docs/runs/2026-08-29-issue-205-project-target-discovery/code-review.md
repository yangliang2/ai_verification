# Issue #205 review record

Review fixed point: `343cf27`
Review axes: repository standards and issue specification.

## Standards review

The standards review found five issues, all remediated in the implementation:

- Project result identity normalized away the candidate identity; project
  normalization now preserves candidate/pair/receipt identities while only
  removing environment-specific paths and context-acquisition identity.
- The existing `OpenCalcDiscoveryError` compatibility alias was restored
  exactly, with the new ProjectTarget error as a subclass.
- Clone cleanup could have removed a caller-owned directory; materialization
  now atomically claims an absent child path and cleanup removes only a path
  claimed by this admission run.
- Malformed serialized ProjectTarget data could leak an internal exception;
  parsing now maps malformed targets to the public package-schema error.
- Discovery docstrings and terminology were updated to describe both target
  kinds and the model-free admission boundary.

## Specification review

The specification review found four issues, all remediated:

- The symmetry test compared only a subset of neutral semantics; it now
  compares the full neutral hypothesis and failure-chain semantics while
  keeping source and target identities distinct.
- A materialization could drift after Context Acquisition; the admission path
  now revalidates each synthetic worktree immediately after acquisition and
  again before projection.
- Serialized policy and field drift could be omitted from a forged package;
  ProjectTarget deserialization now compares the complete expected serialized
  representation and rejects exploration-policy drift.
- The runtime-build worktree boundary is explicit in the package and receipt
  (`runtime_build_worktree: false`), with the side-effect test proving that
  admission invokes only Git subprocesses. Runtime build/device/model work
  remains outside this issue's claim boundary.

## Disposition

The remediations are covered by the final focused and full-suite verification
record. No unresolved review finding remains in the working tree.

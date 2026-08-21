# Issue #185 — safely materialize one provenance-bound curated candidate

Status: implementation and hermetic validation are complete on
`issue-185-curated-candidate-materialization`. This is an M0.1 source-preparation
slice only. It does not make a Behavior-Layer Defect detection, Android runtime,
or benchmark claim.

## Source identity and result

- Issue: [#185](https://github.com/yangliang2/ai_verification/issues/185).
- Base revision: `aa55648c7a5f5b0da3599792273e62218b571583`.
- Base tree: `0df050a3327d4126c5bca8438d2e85b11fb26233`.
- Tested implementation revision:
  `fc66675687c83fefb6762f2dac85aca6ed7b63b8`.
- Tested implementation tree:
  `72b3d88c0cfd5681ef1a9638f285d587d4f673e3`.

The new `aiverify.injection` seam accepts one audit-side, `curated`
`InjectionCandidate`. Its `BaselineProvenance` binds origin, full commit, and a
content-based source-tree SHA-256; its `SourceDelta` binds exactly one unified
diff's UTF-8 bytes and SHA-256; and its `FaultOperator` binds versioned
applicability and safety-boundary metadata. The materializer creates a fresh
detached Git worktree at the declared commit, verifies the baseline source
identity before applying the delta, and reports separate baseline, patch,
result-tree, canonical-diff, result, and receipt identities.

Success is `materialized`. Invalid input, unavailable or mismatched baseline
provenance, non-applicable patches, unsafe worktree roots, and source-identity
failures return a deterministic `rejected` receipt with a stable reason code
and no materialized result or worktree data. The caller checkout is never
checked out, reset, or patched.

Cleanup requires the exact receipt, a matching owned-marker document, the same
Git common directory, a registered detached worktree at the recorded baseline,
and an unchanged resulting source-tree identity. It refuses arbitrary paths,
existing checkouts, repurposed worktrees, and altered materialized sources.

## Verification

Environment:

- macOS 26.3 (Darwin arm64)
- Git `2.50.1 (Apple Git-155)`
- Python `3.11.15`
- pytest `9.1.1`

Commands were run against the tested implementation revision above:

```text
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -q \
  tests/injection tests/discovery tests/runner \
  --junitxml=docs/runs/2026-08-20-issue-185-curated-candidate-materialization/verification/focused-pytest.xml
PASS: 427 passed, 0 failed, 0 errors, 0 skipped; JUnit 13.870s;
real 14.50s, user 7.47s, sys 5.81s.

PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -qq \
  --junitxml=docs/runs/2026-08-20-issue-185-curated-candidate-materialization/verification/full-pytest.xml
PASS: 1,153 passed, 0 failed, 0 errors, 1 skipped (1,154 total);
JUnit 59.374s; real 59.56s, user 36.14s, sys 19.41s.

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src
PASS: exit 0.

git diff --check origin/main...HEAD
PASS: exit 0.
```

The only full-suite skip is the existing repository-external-fixture gate at
`tests/bench/test_m9_recovery_formal.py:195`; it requires explicit admission
and is unrelated to this hermetic M0.1 slice.

## Artifact inventory

- `verification/focused-pytest.xml` — 427-test focused JUnit report; SHA-256
  `1fa64115fd58359cbb1615d1bab6cad93512c241076357144eefa7e51a3cf3d6`.
- `verification/full-pytest.xml` — 1,154-test full JUnit report; SHA-256
  `7e37850afd6c2bd5b4d3249ddf5293d2226f251b221897ccc33432863ef79606`.
- `verification.json` — machine-readable command, result, artifact, and scope
  inventory.
- `checksums.sha256` — checksum inventory for every other committed run
  artifact.

Implementation files:

- `src/aiverify/injection/models.py` — canonical contracts and identities.
- `src/aiverify/injection/materialization.py` — detached-worktree application
  and verified cleanup.
- `src/aiverify/injection/__init__.py` — public M0.1 surface.
- `tests/injection/test_materialization.py` — seven temporary-Git-repository
  regressions.

No screenshots, layouts, logs, APKs, package or activity identifiers, emulator
artifacts, Android CLI/adb commands, Gradle builds, provider calls, model
invocations, manual device steps, or network-dependent test fixtures were used.
The tests construct and dispose only temporary local Git repositories.

## Claim boundary and known gaps

- This proves only safe source-delta materialization and source identity in a
  local hermetic test boundary. It is not an admission, sealed Injected Case
  Package, blind verifier packet, Discovery Campaign, Run Spec, ExecutionRecord,
  runtime oracle, formal cohort, or metric aggregation result.
- M0.1 supports declared unified diffs only. AST/PSI mutation, LLM proposals,
  real-bug replay, Manifest/resource/Intent mutation, and runtime/environmental
  perturbations remain out of scope.
- Curated catalog rendering, audit admission, disclosure-token checks, verifier
  packets, and the four auditor mapping cells are deliberately deferred to
  #186–#190. In particular, this slice does not claim semantic-leak detection
  or a behaviorally valid control.
- A collision-resistant checksum and ownership marker are a fail-closed local
  safety boundary, not protection against arbitrary privileged filesystem or
  Git-database tampering outside the public materializer API.

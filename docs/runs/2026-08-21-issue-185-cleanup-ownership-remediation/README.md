# Issue #185 — cleanup ownership remediation

Status: this run records the remediation requested after independent review of
the M0.1 curated-candidate materialization slice. It is a hermetic,
source-preparation change only; it makes no Behavior-Layer Defect, Android
runtime, verification-agent, formal-admission, or benchmark claim.

## Source and review remediation

- Issue: [#185](https://github.com/yangliang2/ai_verification/issues/185).
- Base revision: `aa55648c7a5f5b0da3599792273e62218b571583`.
- Base tree: `0df050a3327d4126c5bca8438d2e85b11fb26233`.
- Remediation revision:
  `44ee41489f4b9b845b0298e91b399bdaea46cfbb`.
- Remediation tree: `ab768fa178151b8d203d824d8b36716a86debed1`.

The independent spec review found that a caller could forge a receipt and
matching marker for an existing, detached linked worktree in the same Git
common directory. `InjectionMaterializer` now retains a non-serializable,
per-instance registration for every worktree it creates, including the exact
`MaterializedWorktree` contract and the directory device/inode pair. Cleanup
requires that registration in addition to the pre-existing marker, repository,
detached-HEAD, baseline, and result-tree checks. Consequently, a new
materializer instance fails closed rather than deleting a worktree it did not
create.

`FaultOperator.applicability` and `safety_boundary` remain immutable audit
metadata in M0.1. The executable non-applicability boundary is deliberately
one `SourceDelta` applying to the declared immutable baseline through `git
apply --check`; an operator-specific interpreter is deferred to a later
milestone.

## Acceptance-criteria coverage

- `tests/injection/test_materialization.py` adds
  `test_cleanup_refuses_a_forged_receipt_for_an_existing_linked_worktree`.
  It creates a temporary Git repository, materializes a candidate, creates a
  separate detached linked worktree in the same common directory, applies the
  same delta, and writes a receipt-shaped marker. The public
  `cleanup(receipt)` seam raises `InjectionCleanupError` and preserves that
  pre-existing worktree.
- Existing materialization tests continue to exercise the single detached
  worktree, canonical identities, rejected non-applicable patch, provenance
  mismatch, caller-checkout preservation, foreign checkout refusal, modified
  result refusal, and unsafe-root refusal paths.
- No Android build, installation, device action, provider invocation, formal
  admission, or metric aggregation command was executed.

## Verification

Environment:

- macOS 26.3 (Darwin arm64)
- Git `2.50.1 (Apple Git-155)`
- Python `3.11.15`
- pytest `9.1.1`

Commands were run against the remediation source tree above:

```text
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -q \
  tests/injection tests/discovery tests/runner \
  --junitxml=docs/runs/2026-08-21-issue-185-cleanup-ownership-remediation/verification/focused-pytest.xml
PASS: 428 passed, 0 failed, 0 errors, 0 skipped; JUnit 13.753s;
real 13.88s, user 7.26s, sys 5.55s.

PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -qq \
  --junitxml=docs/runs/2026-08-21-issue-185-cleanup-ownership-remediation/verification/full-pytest.xml
PASS: 1,154 passed, 0 failed, 0 errors, 1 skipped (1,155 total);
JUnit 91.902s.

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src
PASS: exit 0.

git diff --check origin/main...HEAD
PASS: exit 0.
```

The one full-suite skip remains the repository-external-fixture gate at
`tests/bench/test_m9_recovery_formal.py:195`; it requires explicit admission
and is unrelated to the hermetic M0.1 slice.

## Artifact inventory

- `verification/focused-pytest.xml` — 428-test focused JUnit report;
  SHA-256 `cafb55a5884f800404f3105162b1cb817b418c6ae7bf7414e24e4bef04ad2a6e`.
- `verification/full-pytest.xml` — 1,155-test full JUnit report;
  SHA-256 `cc5462a0124f9c5340f51a6b1f2319ab86f6dcee806dcf814df4cbbe5e8da0b0`.
- `verification.json` — machine-readable verification and scope inventory.
- `checksums.sha256` — checksum inventory for every committed run artifact.

No screenshots, layout dumps, logs, APKs, package/activity identifiers,
emulator/device artifacts, Android CLI/adb commands, Gradle builds, provider
calls, model invocations, manual device steps, or network-dependent fixtures
were used. The tests create and dispose only temporary local Git repositories.

## Known boundary

The instance-local authority registry intentionally makes cleanup fail closed
after the creating `InjectionMaterializer` is discarded. A serialized receipt
remains an auditable, regenerable identity record, but a newly constructed
materializer cannot use it to delete an existing worktree. This is a deliberate
M0.1 safety boundary, not a durable cross-process cleanup protocol.

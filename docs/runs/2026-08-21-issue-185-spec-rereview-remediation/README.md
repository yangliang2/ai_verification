# Issue #185 — spec re-review remediation

Status: this run records the two findings from the second independent
specification review of the M0.1 curated-candidate materialization slice. It is
a hermetic source-preparation change only; it makes no Behavior-Layer Defect,
Android runtime, verification-agent, formal-admission, or benchmark claim.

## Source and remediation

- Issue: [#185](https://github.com/yangliang2/ai_verification/issues/185).
- Base revision: `aa55648c7a5f5b0da3599792273e62218b571583`.
- Base tree: `0df050a3327d4126c5bca8438d2e85b11fb26233`.
- Remediation revision:
  `307473c6358144393b24be4851606e7727f7aebb`.
- Remediation tree: `5bee635d5ceea0dd8e16ad3ea4fbd43b10d53ad1`.

The re-review found two incomplete paths:

1. `git apply` left added source files untracked, while `git diff <baseline>`
   omitted them from the canonical result diff. The materializer now checks and
   applies the one declared delta with `--index`, then derives
   `result_diff_sha256` from the staged binary diff. Added files and edits are
   now bound to the same result identity.
2. A directly supplied `InjectionCandidate` could pass dataclass construction
   but fail canonical identity encoding later, causing an exception rather than
   a stable rejected receipt. `materialize()` now preflights its canonical
   candidate identity and returns `invalid_candidate` with no candidate identity
   or worktree for any such input.

## Acceptance-criteria coverage

- `tests/injection/test_materialization.py` adds
  `test_materializes_added_source_files_in_the_canonical_result_diff`. It uses
  one unified diff that both modifies an existing source file and adds a new
  one; the public `materialize(candidate)` seam must emit a receipt whose
  canonical result-diff SHA-256 binds both paths.
- The same file adds
  `test_direct_candidate_with_an_unencodable_identity_returns_stable_rejection`.
  A direct candidate containing a UTF-8-unencodable lone surrogate returns two
  equal `invalid_candidate` receipts and creates no worktree root.
- The prior cleanup-ownership regression remains in the focused suite. Together
  the temporary-Git-repository tests cover materialized and rejected outcomes,
  caller preservation, provenance validation, added files, direct invalid input,
  and verified cleanup ownership.
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
  --junitxml=docs/runs/2026-08-21-issue-185-spec-rereview-remediation/verification/focused-pytest.xml
PASS: 430 passed, 0 failed, 0 errors, 0 skipped; JUnit 13.929s;
real 14.04s, user 7.39s, sys 5.52s.

PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -qq \
  --junitxml=docs/runs/2026-08-21-issue-185-spec-rereview-remediation/verification/full-pytest.xml
PASS: 1,156 passed, 0 failed, 0 errors, 1 skipped (1,157 total);
JUnit 53.547s.

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src
PASS: exit 0.

git diff --check origin/main...HEAD
PASS: exit 0.
```

The one full-suite skip remains the repository-external-fixture gate at
`tests/bench/test_m9_recovery_formal.py:195`; it requires explicit admission
and is unrelated to the hermetic M0.1 slice.

## Artifact inventory

- `verification/focused-pytest.xml` — 430-test focused JUnit report;
  SHA-256 `5db639b1e723b21d0f0027bec25e844e26dd2d64bbbbc255a35f219432b34472`.
- `verification/full-pytest.xml` — 1,157-test full JUnit report;
  SHA-256 `c75f49c16325804d452571ee64bdb78c9d548c04f670492ff6a5648f9e7046d6`.
- `verification.json` — machine-readable verification and scope inventory.
- `checksums.sha256` — checksum inventory for every committed run artifact.

No screenshots, layout dumps, logs, APKs, package/activity identifiers,
emulator/device artifacts, Android CLI/adb commands, Gradle builds, provider
calls, model invocations, manual device steps, or network-dependent fixtures
were used. The tests create and dispose only temporary local Git repositories.

## Known boundaries

- M0.1 accepts declared unified diffs only. AST/PSI mutation, LLM proposals,
  real-bug replay, Manifest/resource/Intent mutation, and runtime/environmental
  perturbations remain out of scope.
- `FaultOperator.applicability` and `safety_boundary` remain immutable audit
  metadata. Non-applicability is executable only as failure of the declared
  source delta to apply to the declared baseline; a machine-interpreted operator
  scope remains later-milestone work.
- Cleanup authority is intentionally instance-local and fail-closed after the
  creating `InjectionMaterializer` is discarded; it is not a durable
  cross-process cleanup protocol.

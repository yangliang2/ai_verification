# Issue #185 — Git canonicalization remediation

Status: this run records the two findings from the final independent
specification review of the M0.1 curated-candidate materialization slice. It is
a hermetic source-preparation change only; it makes no Behavior-Layer Defect,
Android runtime, verification-agent, formal-admission, or benchmark claim.

## Source and remediation

- Issue: [#185](https://github.com/yangliang2/ai_verification/issues/185).
- Base revision: `aa55648c7a5f5b0da3599792273e62218b571583`.
- Base tree: `0df050a3327d4126c5bca8438d2e85b11fb26233`.
- Remediation revision:
  `84b3f01aa2d879bdbd0ab7d72a2417a8d69f2216`.
- Remediation tree: `01b75e63d8e2d5e4860bed4ab333808eb4b69e63`.

The final review found that materialization inherited Git configuration that
could alter both safety checks and receipt identity:

1. A caller setting `core.autocrlf=true` caused a fresh linked worktree to
   contain CRLF checkout bytes while baseline identity was derived from LF Git
   blobs. The materializer now runs Git with `core.autocrlf=false` and
   `core.eol=lf`, so the source-tree comparison, patch application, and result
   source identity use the declared Git bytes.
2. Caller diff settings could alter the raw staged binary diff and therefore
   `result_diff_sha256`, `result_identity_sha256`, and receipt identity. The
   materializer now pins Git config and output options for quote paths, color,
   rename detection, prefixes, diff algorithm and heuristics, context, path
   ordering, relative paths, text conversion, and external diff helpers before
   hashing the staged result diff.

## Acceptance-criteria coverage

- `tests/injection/test_materialization.py` adds
  `test_materializes_when_caller_configures_autocrlf`: a candidate from an LF
  commit materializes successfully even when the caller checkout configures
  CRLF conversion.
- The same file adds
  `test_materialization_identities_ignore_caller_diff_configuration`: the same
  two-path source delta is materialized before and after setting caller
  `diff.noprefix`, `diff.mnemonicPrefix`, `diff.renames`, `diff.algorithm`,
  `color.ui`, and `diff.orderFile`; all result and receipt identities remain
  equal.
- Existing temporary-Git-repository tests continue to exercise exactly one
  detached worktree, added files, stable invalid/non-applicable/provenance
  rejections, caller-checkout preservation, instance-owned cleanup, and source
  modification refusal.
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
  --junitxml=docs/runs/2026-08-21-issue-185-git-canonicalization-remediation/verification/focused-pytest.xml
PASS: 432 passed, 0 failed, 0 errors, 0 skipped; JUnit 14.891s;
real 15.00s, user 7.78s, sys 6.03s.

PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -qq \
  --junitxml=docs/runs/2026-08-21-issue-185-git-canonicalization-remediation/verification/full-pytest.xml
PASS: 1,158 passed, 0 failed, 0 errors, 1 skipped (1,159 total);
JUnit 55.094s.

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src
PASS: exit 0.

git diff --check origin/main...HEAD
PASS: exit 0.
```

The one full-suite skip remains the repository-external-fixture gate at
`tests/bench/test_m9_recovery_formal.py:195`; it requires explicit admission
and is unrelated to the hermetic M0.1 slice.

## Artifact inventory

- `verification/focused-pytest.xml` — 432-test focused JUnit report;
  SHA-256 `14845f3e94c09b6a545925d14db18e467e15a27b5a43cf69c70b499b7f0ddc9b`.
- `verification/full-pytest.xml` — 1,159-test full JUnit report;
  SHA-256 `7323b607d39bbfc231e68c02f7358fac47b6ff57771c319fa452be543b2f73db`.
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

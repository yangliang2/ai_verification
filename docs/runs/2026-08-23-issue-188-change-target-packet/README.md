# Issue #188 — blind-safe ChangeTarget packet verification

## Scope

This run verifies DIL-M0.4 on branch
`issue-188-blind-safe-change-target-packet`. A fixture-local, structurally
admitted defect/control pair is compiled into one deterministic,
verifier-facing packet for either selected variant. The packet binds an actual
checked-in unified patch, its SHA-256, source origin and commit, baseline and
materialized source-tree identities, result-diff identity, and sealed receipt
identity.

The implementation is a structural packet-contract boundary only. It does not
invoke a Verification Agent, construct or execute a Discovery Campaign or Run
Spec, build an Android application, or make a runtime/behavioral qualification
claim.

## Implemented evidence

- `src/aiverify/injection/packets.py` defines the private auditor pair and
  public `VerifierPacket` contracts, canonical serialization/identity,
  revalidation of sealed admission and Disclosure Policy provenance, real
  materialized-source and catalogued-patch checks, compatible-pair checks, and
  fixed non-disclosing rejection codes.
- `src/aiverify/injection/__init__.py` exposes the packet boundary as
  `compile_change_target_packet`.
- `tests/injection/test_change_target_packet.py` creates a temporary Git
  fixture with real materialized worktrees and checked-in patch files. It
  proves deterministic packet bytes/identities, public-field round trips,
  high-entropy audit-only sentinel exclusion, and fail-closed rejection for a
  missing pair, an unsealed case, forged worktree provenance, incompatible
  baseline provenance, different fixture anchors, upstream disclosure
  rejection, final path disclosure, and a symlink-loop error whose hidden path
  is excluded from the full traceback.

Acceptance mapping:

| Acceptance criterion | Evidence |
| --- | --- |
| Deterministic real, provenance-bound ChangeTarget packet | deterministic compiler test reads the catalogued patch and materialized source tree; packet parser round-trips its canonical bytes and identity. |
| No audit-only disclosure in public packet/errors/IDs | high-entropy policy checks all packet material; final packet review scans paths and derived identity; traceback regression checks the public error chain. |
| Stable fail-closed rejections | explicit negative tests assert the terminal `PacketCompilationError.code` values. |
| Pair is fixture-local and compatible | same baseline, distinct delta, population, taxonomy, and identical fixture anchor are all required; the differing-anchor test rejects. |
| No prohibited execution/scope expansion | deterministic Python-only tests; no verifier, campaign, Run Spec, Android, device, emulator, or runtime invocation. |

## Environment

- Package: `aiverify` 0.1.0 (Python package; no Android app/package was built)
- CPython 3.11.15
- pytest 9.1.1
- git 2.50.1 (Apple Git-155)

## Commands and results

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' -q tests/injection/test_change_target_packet.py

Passed: 9 tests in 13.09 seconds.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src tests

Passed with exit status 0.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' -q tests/injection --junitxml=docs/runs/2026-08-23-issue-188-change-target-packet/verification/injection-pytest.xml

Passed: 65 tests; failed: 0; errors: 0; skipped: 0; JUnit elapsed time:
40.494 seconds.

    PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' -q --junitxml=docs/runs/2026-08-23-issue-188-change-target-packet/verification/full-pytest.xml

Passed: 1,211 tests; failed: 0; errors: 0; skipped: 1; total: 1,212
tests; JUnit elapsed time: 92.583 seconds.

    git diff --check origin/main...HEAD

Passed with no whitespace errors after the evidence commit.

## Artifact inventory and checksums

| Artifact | Purpose | SHA-256 |
| --- | --- | --- |
| `verification/injection-pytest.xml` | Injection Lab suite JUnit report | `af8fa9c7068bc3c7f2e31af2097bcf9e828b35ebac8707509dd48aa5e8c1b9e5` |
| `verification/full-pytest.xml` | Full repository JUnit report | `eefcaf651912f6b3ab427055d3f6e2631dd45c7d00caf3e1f0c5e3b51e3825dd` |
| `SHA256SUMS` | Machine-checkable report checksum inventory | N/A (contains the two hashes above) |

Verify the reports with:

    (cd docs/runs/2026-08-23-issue-188-change-target-packet && shasum -a 256 -c SHA256SUMS)

No screenshots, layout dumps, logs beyond the JUnit reports, generated JSON,
Gradle builds, APKs, Android devices/emulators, models/providers, formal
benchmark runs, or manual verification were used. The temporary Git fixtures
are created and cleaned up by pytest; they are not durable artifacts.

## Review and known gaps

The required two-axis code review found no documented-standard violations.
Its initial maintainability suggestions (one cleanup context manager and one
correlated pair selection) were applied. The specification review found and
then verified fixes for fixture-anchor compatibility and suppression of raw
filesystem paths from chained public tracebacks.

- The Disclosure Policy is intentionally a declared-token safeguard, not a
  general semantic-leak detector.
- This ticket is structural and test-fixture-local; it does not prove a
  verifier outcome or a behavioral result.
- No configured mypy, pyright, or ruff executable is present in this
  repository. `compileall` checks syntax; pytest provides the available
  automated behavioral validation.

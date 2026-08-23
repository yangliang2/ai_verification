# Issue #187 — stale-result disclosure rejection verification

## Scope

This run verifies DIL-M0.3 on branch
`issue-187-stale-result-disclosure-rejection`. It binds the existing
`curated-deterministic-concurrency-apply-stale-result-v1` catalog entry to its
raw catalog bytes, the sealed M0 admission package, and the declared run-spec
audit artifact. The auditor-side disclosure policy then rejects the candidate
from the blind verifier-packet boundary while retaining the sealed audit
evidence.

The implementation is structural and deliberately bounded: it detects only
auditor-declared tokens, with case/separator spelling normalization. It makes
no claim to detect arbitrary semantic disclosure.

## Implemented evidence

- `bench/curated-source-catalog-v1.json` declares the stale candidate's audit
  artifact and pins its digest.
- `src/aiverify/injection/catalog.py` validates the audit artifact's declared
  path, bytes, digest, and catalog provenance before admission.
- `src/aiverify/injection/disclosure.py` scans all JSON-visible keys and
  strings, including source text, metadata, paths, and derived identifiers.
  It returns the deterministic terminal status `rejected` with
  `declared_disclosure_detected` and the explicit claim boundary
  `m0_structural_blind_packet_eligibility_only`.
- `tests/injection/test_disclosure.py` proves detection of `APPLY_STALE`,
  `injected_defect`, and `expected_oracle`; preserves audit evidence; verifies
  serialization; and checks that the patch and frozen run-spec bytes are not
  rewritten. `tests/injection/test_catalog_admission.py` covers audit-artifact
  drift rejection and the static catalog declaration.

Pinned identities exercised by the static stale-result test:

- Catalog identity: `93b0b566c767cfaf25548825aea338b2644a8a1beddbbdb32cfd948f382684d5`
- Raw catalog SHA-256: `2fbcbb60882c749a4c02365717f01afe6d379d10571fafea9e142292deebec3b`
- Catalog-entry identity: `a520e20c44ae4f671945316e8bb635f21ecf455acde3a9848f580d7cf695bb9c`
- Candidate identity: `3040e0e5814b01b5b9030ba3a9e6a130b91ebcf919756134d92173eeddf4d7fe`
- Disclosure-policy identity: `ab36e6027774174579229077684afb0f37a7695a97b2e6de58b8da84fb6b53e4`

## Environment

- CPython 3.11.15
- pytest 9.1.1
- git 2.50.1 (Apple Git-155)

## Commands and results

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' -q tests/injection --junitxml=docs/runs/2026-08-23-issue-187-disclosure-rejection/verification/injection-pytest.xml

Passed: 56 tests; failed: 0; errors: 0; skipped: 0; JUnit elapsed time:
26.141 seconds.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' -q --junitxml=docs/runs/2026-08-23-issue-187-disclosure-rejection/verification/full-pytest.xml

Passed: 1,202 tests; failed: 0; errors: 0; skipped: 1; total: 1,203 tests;
JUnit elapsed time: 76.507 seconds.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src

Passed with exit status 0.

    git apply --check bench/capability-slices/deterministic-concurrency/patches/apply-stale-result.patch

Passed with exit status 0; the catalogued patch remains syntactically
applicable.

    git diff --check origin/main...HEAD

Passed with no whitespace errors before recording this run; it is rerun after
the evidence commit as a final structural check.

## Artifact inventory and checksums

| Artifact | Purpose | SHA-256 |
| --- | --- | --- |
| `verification/injection-pytest.xml` | Focused injection-suite JUnit report | `5e3d65914e99054ccdc4d42ff85404cbbd35d43e3e4d3b0daa0612e19de6ef30` |
| `verification/full-pytest.xml` | Full repository JUnit report | `ff403c10408100207f5e652be22e26b636f5d5de0afec1cf1cf3f96ed0299074` |
| `SHA256SUMS` | Machine-checkable artifact checksum inventory | N/A (contains the two hashes above) |

Verify the reports with:

    (cd docs/runs/2026-08-23-issue-187-disclosure-rejection && shasum -a 256 -c SHA256SUMS)

No screenshots, layout dumps, logs, generated JSON, Gradle builds, APKs,
Android devices/emulators, models/providers, or formal benchmark runs were
used. No manual verification was required for this deterministic Python-only
boundary.

## Known gaps and follow-up risks

- The policy is intentionally a declared-token safeguard, not a general
  semantic-leak detector.
- The stale-result integration test uses a deterministic M0 receipt seam after
  catalog loading; it does not claim a fresh full static worktree
  materialization. The real temporary-Git materializer behavior is covered by
  issue #185's tests.
- No configured mypy, pyright, or ruff executable is available in this
  repository. `compileall` checks syntax only; the pytest suites are the
  available automated behavioral validation.

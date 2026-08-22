# Issue #186 — M0.2 catalog admission verification

This run records the local verification of the M0.2 Catalog Admission slice on
branch `issue-186-catalog-admission`, based on
`0c4c398ceee3d046dc1f6a2c55e8ad516935598c`. It is a hermetic,
temporary-Git-repository validation of Injection Lab source preparation and
structural admission only. It does not build, install, or run an Android app,
invoke a provider or model, produce a Behavior-Layer Defect claim, or admit a
Qualification Case Package or cohort member.

- Issue: [#186](https://github.com/yangliang2/ai_verification/issues/186)
- Runtime: CPython 3.11.15
- Test runner: pytest 9.1.1
- Git: `git version 2.50.1 (Apple Git-155)`
- App/package/activity identifier: not applicable; no Android artifact was
  created.

## Acceptance-criteria evidence

- `bench/curated-source-catalog-v1.json` declares the supported
  `curated-deterministic-concurrency-apply-stale-result-v1` source with its
  immutable patch bytes, fixture-anchor SHA-256, curated controlled population,
  and explicit known taxonomy relationship
  `coroutine-concurrency-05`.
- `src/aiverify/injection/catalog.py` parses that catalog deterministically,
  rejects duplicate JSON keys and catalog conflicts, verifies each referenced
  patch and fixture byte identity, and requires the catalog plus all declared
  files to match raw Git `HEAD` blobs through a sanitized Git environment. Its
  `CheckedInCuratedSourceCatalog` binds both semantic catalog identity and the
  exact catalog-file SHA-256 without placing a local path in the audit identity.
- `src/aiverify/injection/admission.py` accepts only a catalog path and
  reloads it immediately before materialization through the #185 seam. It
  checks candidate, baseline, and patch receipt identities before trusting either a
  materialized or rejected outcome, and emits a hash-chained terminal ledger.
  A sealed `InjectedCasePackage` records `non_formal`,
  `not_a_cohort_member`, `m0_structural_audit_only`, and six explicit
  `not_claimed` evidence dimensions.
- `tests/injection/test_catalog_admission.py` covers the catalog-to-real-
  materializer path, catalog/patch/fixture drift, duplicate and invalid
  provenance records, untracked catalog files, ambient-Git isolation, missing
  selection, drift revalidation before materialization, dirty-caller
  preservation, ledger serialization, materialized contradictory receipts, and
  rejected contradictory receipts.

The checked-in catalog verification produced:

```text
catalog_identity_sha256=92dcdf6b3b30ee40cd8a7721eb7e50b482bf787badc32b6c2ac02799f47a0d95
catalog_source_sha256=8a24bec5c6f41d455a323e209b70f513a3a95d2038488fa91240485ab6b83e08
entry_identity_sha256=b2ece61839122a0f6b3628482c91298be18547305e914d25466ef8e493d5982d
candidate_identity_sha256=3040e0e5814b01b5b9030ba3a9e6a130b91ebcf919756134d92173eeddf4d7fe
```

## Verification commands and results

All commands ran from the implementation worktree. The existing shared
Python 3.11 virtual environment was used because the disposable worktree does
not contain its own `.venv`.

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m compileall -q src
```

Passed: exit 0.

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m pytest -p no:cacheprovider -o addopts='' -q tests/injection \
  --junitxml=docs/runs/2026-08-22-issue-186-catalog-admission/verification/injection-pytest.xml
```

Passed: 51 passed, 0 failed, 0 errors, 0 skipped in 25.10s (JUnit time
25.064s).

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m pytest -p no:cacheprovider -o addopts='' -q \
  --junitxml=docs/runs/2026-08-22-issue-186-catalog-admission/verification/full-pytest.xml
```

Passed: 1,197 passed, 0 failed, 0 errors, 1 skipped (1,198 total; JUnit time
74.612s). The one skipped test is the repository's explicit external-fixture
gate, not this hermetic Injection Lab slice.

```sh
git apply --check bench/capability-slices/deterministic-concurrency/patches/apply-stale-result.patch
git diff --check
```

Both commands passed with exit 0. The first is a read-only structural check of
the catalogued static patch; the second is repeated after this run record is
added before commit.

## Artifact inventory

| Artifact | Purpose | SHA-256 |
| --- | --- | --- |
| `verification/injection-pytest.xml` | Focused Injection Lab JUnit report, 51 tests | `25b96fcaa3808d0a957506f469f03fa3d8b74cc758a21f99fd760a02eab16178` |
| `verification/full-pytest.xml` | Full repository JUnit report, 1,198 tests | `00db461061e4002aeabf9dcce8def152bd913e24c25ae3f6b4f3e638fa592657` |
| `SHA256SUMS` | Machine-verifiable checksum inventory | Covers both JUnit artifacts |

No screenshots, layout dumps, logs, APKs, Android builds, emulator/device
artifacts, `adb` commands, manual runtime checks, provider calls, or model
invocations were produced. The tests create and dispose only temporary local
Git repositories and materializer-owned worktrees.

## Known boundaries and gaps

- The checked-in static catalog was parsed, byte-bound, and patch-checked. Its
  exact end-to-end materialization was not run in this execution environment:
  the #185 source-tree checksum implementation invokes one Git process per
  blob for this roughly 9,200-file baseline and exceeds the command channel's
  approximately 30-second cap. The same public catalog-to-materializer path is
  covered deterministically against a committed temporary Git repository in
  the focused suite; no static materialization success is claimed here.
- M0.2 is intentionally structural. Build, installation, runtime, oracle,
  flakiness, and equivalence are all explicitly `not_claimed`; formal
  qualification, cohort membership, benchmark metrics, Discovery Campaign,
  and Run Spec work remain later milestones.

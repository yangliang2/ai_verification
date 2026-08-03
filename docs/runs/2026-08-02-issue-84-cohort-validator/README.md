# Issue #84 — M6 cohort validator foundation

Date: 2026-08-02 (America/New_York)

## Scope

This run record verifies the candidate-independent validation foundation for
issue #84. It does **not** freeze or admit the six M6 cases, authorize upstream
access, run admission preflights, or start a formal qualification lane.

Source revision under test:
`6afd476bf5c50ccc21e0c3331dce7c1b59394b4b`

The final evidence commit is the commit that contains this run record and
`checksums.sha256`; it is intentionally separate from the source revision under
test so generated evidence was absent from the test invocation.

## Implemented contract

- `src/aiverify/bench/m6_cohort_schema.json` is a strict Draft 2020-12 schema
  for a versioned draft/frozen cohort, environment and retry policy, exactly six
  admitted slots, a ranked replacement pool, durable exclusions and
  replacements, and formal invocation state.
- `src/aiverify/bench/m6_cohort.py` rejects invalid schema, duplicate YAML
  keys, non-3+3 populations, missing H-01 through H-03/P-01 through P-03 slot
  identities, fewer than four M5 risk families, and any total other than the
  frozen 36-lane plan.
- Historical admissions require exact, distinct pre-fix/fixed revisions,
  matched fail/pass evidence, and reject synthetic or reverse-applied changes.
- Prospective admissions bind upstream eligibility, frozen development input,
  separate sessions, candidate freeze, verifier blinding, network policy, and
  no-upstream-interaction policy.
- Source/task overlaps, invalid replacement ranks, cross-track replacement,
  skipped unexcluded candidates, exclusion/admission overlap, and replacement
  at or after a slot's first formal invocation fail closed.
- All artifact references use normalized repository-relative paths and exact
  SHA-256. Referenced files must exist and match unless the CLI is explicitly
  used for syntax-only inspection.
- Frozen manifests require prior maintainer approval. Admissions, exclusions,
  and replacement events cannot occur after the version's freeze time, and
  formal invocations cannot predate it.
- Historical and prospective claim contracts remain distinct. Combined
  denominators, detection/false-positive rates, confidence claims, prospective
  Goldset, general Android coverage, and upstream acceptance are explicitly
  forbidden.
- The loader retains both exact consumed-file SHA-256 and canonical-document
  SHA-256 identities and exposes a deterministic machine-readable CLI summary.
- `pyproject.toml` packages the schema with `aiverify.bench`.

## Verification

Environment:

- macOS 26.3 (build 25D125)
- Python 3.11.15
- pytest 9.0.3
- jsonschema 4.26.0
- PyYAML 6.0.3
- git 2.50.1 (Apple Git-155)

### Schema self-validation

```bash
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -c 'from aiverify.bench.m6_cohort import self_validate_schema; self_validate_schema(); print("Draft 2020-12 schema: valid")'
```

Result:

- exit status: 0
- output: `Draft 2020-12 schema: valid`

### Focused contract slice

```bash
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest \
  -p no:cacheprovider -o addopts='' \
  tests/bench/test_m6_cohort.py -q \
  --junitxml=docs/runs/2026-08-02-issue-84-cohort-validator/artifacts/focused-junit.xml
```

Result:

- exit status: 0
- 16 passed, 0 failed, 0 errors, 0 skipped
- pytest duration: 0.99s; JUnit suite time: 0.988s
- wall/user/sys: 1.09s / 0.98s / 0.10s

The focused tests cover valid frozen/draft documents, schema packaging,
missing/duplicate cases, track mixing, risk-family coverage, exact historical
pairs, prospective network policy, claim leakage, duplicate/overlapping source
identity, path traversal, missing/tampered artifacts, valid and invalid
replacement transitions, approval/admission ordering, duplicate YAML keys, and
CLI output.

### Complete project suite

```bash
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest \
  -p no:cacheprovider -o addopts='' -q \
  --junitxml=docs/runs/2026-08-02-issue-84-cohort-validator/artifacts/full-junit.xml
```

Result:

- exit status: 0
- 695 passed, 0 failed, 0 errors, 0 skipped
- pytest duration: 17.51s; JUnit suite time: 17.502s
- wall/user/sys: 17.73s / 9.36s / 3.22s

### Repository and evidence integrity

```bash
git diff --check
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.run_record_checksums \
  docs/runs/2026-08-02-issue-84-cohort-validator
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.run_record_checksums --verify \
  docs/runs/2026-08-02-issue-84-cohort-validator
```

Expected final result: all commands exit 0; checksum verification reports no
missing, changed, duplicate, malformed, outside-record, or unlisted artifact.

## Artifact inventory

| Artifact | Purpose | Size |
|---|---|---:|
| `artifacts/focused-junit.xml` | 16-test cohort-contract result | 2,261 bytes |
| `artifacts/full-junit.xml` | complete 695-test project result | 95,542 bytes |
| `source-revision.txt` | exact source revision tested | 41 bytes |
| `checksums.sha256` | deterministic SHA-256 inventory for this run record | generated after this README |

## Device and manual verification

No emulator, physical device, APK build/install, Android CLI Journey, upstream
source checkout, or manual UI verification was run. This slice changes only the
project-side cohort contract, loader, CLI, and repository tests. Package,
application, APK, device serial, and build-duration fields are therefore not
applicable.

Manual review confirmed that the validator cannot authorize a draft for formal
consumption, does not combine historical and prospective denominators, and does
not treat a replacement-pool entry as admitted without a same-track,
pre-invocation ledger transition.

## Human decision and known gaps

The [maintainer decision packet](https://github.com/yangliang2/ai_verification/issues/84#issuecomment-5161267550)
remains pending. It requests approval of the proposed three historical and three
prospective primaries, ordered replacements, four-family balance, local-only
claim boundary, and permission to perform read/build/test admission preflights
without upstream state-changing interaction.

- There is no committed six-case `QualificationCohortManifest` yet.
- No historical exact-revision matched fail/pass admission evidence exists yet.
- No prospective fixture/oracle has been qualified and no development input has
  been frozen.
- No external-source snapshot from a permitted admission preflight is included.
- No upstream repository was fetched, cloned, built, tested, commented on,
  assigned, or otherwise changed.
- This record supports only the validator foundation; it does not satisfy or
  close #84 and does not unblock #85, #86, #87, or #88.

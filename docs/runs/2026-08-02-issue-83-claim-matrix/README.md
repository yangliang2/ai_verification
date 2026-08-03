# Issue #83 — current capability claim matrix

Date: 2026-08-02 (America/New_York)

## Scope

This run record verifies the documentation-only M6-0 closeout for issue #83. The
change publishes one current claim matrix and synchronizes `README.md`,
`HANDOFF.md`, `CONTEXT.md`, and the M5 gap register without changing runner,
oracle, attempt-accounting, Android host, or device behavior.

Source revision under test:
`c36c32474709a165be823aa76030a913d54798bc`

The final evidence commit is the commit that contains this run record and
`checksums.sha256`; it is intentionally separate from the source revision under
test so that generated evidence is not present during the test invocation.

## Acceptance evidence

### Claim and tracker reconciliation

- [`docs/current-capability-claim-matrix.md`](../../current-capability-claim-matrix.md)
  maps the public execution chain, M1/M2/M3/M3.1 populations, M4 pilot, and M5
  G-01 through G-08 to committed run records.
- The matrix uses explicit bounded-support, `non_accountable`, not-yet-measured,
  and current-nonclaim states.
- `README.md`, `HANDOFF.md`, `CONTEXT.md`, and the gap register all identify M6
  as current and retain the dependency
  `#83 → #84 → #85 → (#86 与 #87) → #88`.
- #80 is recorded as 30/30 first-attempt/eventual accountability, 15/15 controls
  passed, 15/15 expected defects caught, 0 retries, and 30/30 provenance within
  its frozen scope.
- M4 remains two accountable `locally_supported` cases plus one
  `non_accountable` case, with the entry-gate chronology violation retained.
- Every G-01 through G-08 claim is linked to its own bounded fixture/run record;
  Android-general, device-fleet, benchmark-wide, Goldset, and upstream-acceptance
  claims remain excluded.

#58 and #59 were closed only after explicit maintainer approval:

- [#58 completion evidence comment](https://github.com/yangliang2/ai_verification/issues/58#issuecomment-5161151209)
  cites the fresh #80 population and preserves the failed #62 population.
- [#59 retrospective closure comment](https://github.com/yangliang2/ai_verification/issues/59#issuecomment-5161151210)
  cites the M4 aggregate and states that later #80 evidence does not retroactively
  make M4 entry-gate chronology compliant.
- Read-only tracker verification reported both issues `CLOSED` with
  `stateReason=COMPLETED`; no upstream repository was contacted or changed.

### Files implementing the acceptance criteria

- `docs/current-capability-claim-matrix.md`
- `README.md`
- `HANDOFF.md`
- `CONTEXT.md`
- `docs/research/2026-07-19-verification-gap-register.md`
- `tests/bench/test_current_claim_matrix.py`

The new test module checks evidence mappings, status vocabulary, M3/M4 facts,
M6 dependency and denominator boundaries, and every relative Markdown link in
the living source-of-truth documents. The existing M2 report tests are retained
in the focused slice to guard historical compatibility.

## Verification

Environment:

- macOS 26.3 (build 25D125)
- Python 3.11.15
- pytest 9.0.3
- git 2.50.1 (Apple Git-155)

### Documentation-focused slice

```bash
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest \
  -p no:cacheprovider -o addopts='' \
  tests/bench/test_current_claim_matrix.py \
  tests/bench/test_m2_beta_benchmark_slice_report.py \
  -q \
  --junitxml=docs/runs/2026-08-02-issue-83-claim-matrix/artifacts/focused-junit.xml
```

Result:

- exit status: 0
- 10 passed, 0 failed, 0 errors, 0 skipped
- pytest duration: 0.01s; JUnit suite time: 0.013s
- wall/user/sys: 0.12s / 0.07s / 0.01s

### Complete project suite

```bash
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest \
  -p no:cacheprovider -o addopts='' -q \
  --junitxml=docs/runs/2026-08-02-issue-83-claim-matrix/artifacts/full-junit.xml
```

Result:

- exit status: 0
- 679 passed, 0 failed, 0 errors, 0 skipped
- pytest duration: 16.14s; JUnit suite time: 16.130s
- wall/user/sys: 16.28s / 8.59s / 3.14s

### Repository and evidence integrity

```bash
git diff --check
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.run_record_checksums \
  docs/runs/2026-08-02-issue-83-claim-matrix
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.run_record_checksums --verify \
  docs/runs/2026-08-02-issue-83-claim-matrix
```

Expected final result: all commands exit 0; checksum verification reports no
missing, changed, duplicate, malformed, outside-record, or unlisted artifact.

## Artifact inventory

| Artifact | Purpose | Size |
|---|---|---:|
| `artifacts/focused-junit.xml` | 10-test documentation and historical-compatibility result | 1,677 bytes |
| `artifacts/full-junit.xml` | complete 679-test project result | 93,539 bytes |
| `source-revision.txt` | exact source revision tested | 41 bytes |
| `checksums.sha256` | deterministic SHA-256 inventory for this run record | generated after this README |

## Device and manual verification

No emulator, physical device, APK build/install, Android CLI Journey, or manual UI
verification was run. This issue changes source-of-truth documentation and its
repository checks only; all Android behavior claims are links to already committed
run records rather than new observations. Package/app/device identifiers are
therefore not applicable to this run.

Manual review checked that:

- later #80 evidence does not overwrite the failed #62 or original M3 populations;
- M4's chronology exception remains explicit;
- prospective cases are not labeled Goldset;
- local conclusions are not presented as upstream acceptance;
- #84 remains a human-required freeze before formal M6 execution.

## Known gaps and claim boundary

- This run proves documentation consistency and link integrity, not Android
  behavior, runner reliability, or M6 qualification outcomes.
- GitHub issue comments are durable external references but are not copied into
  the checksum inventory; their exact URLs are recorded above.
- No M6 cohort case was selected or executed.
- No upstream task claim, comment, pull request, or acceptance action occurred.
- Historical and prospective M6 denominators remain separate, and this six-case
  plan is not a statistical detection-rate or false-positive-rate population.

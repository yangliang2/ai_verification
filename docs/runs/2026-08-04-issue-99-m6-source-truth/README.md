# M7-0 M6 source-of-truth reconciliation

Date: 2026-08-04

Issue: [#99](https://github.com/yangliang2/ai_verification/issues/99)

Base under test: `origin/main` at `f21c79e46e7d31ab63c843b50e5a11bc5e1102cb`
(PR #105 / M7-1 merge)

Scope: documentation and consistency-test update only. No Android device,
emulator, build host, upstream repository checkout, task claim, or external
project state was changed. The immutable M6 packages and aggregate were not
rewritten or rerun.

## Source-of-truth facts preserved

- M6 completed through PR #97 and the committed #88 aggregate.
- Six frozen Qualification Case Packages remain split into three historical and
  three prospective packages; their denominators are never merged.
- All 36 planned lanes are accountable, with 0 retries and 6/6 package
  adjudication agreement.
- Historical pre-fix/fixed observations remain their original 18-lane population.
- Prospective P-01/P-02 remain `locally_supported`; P-03 remains `inconclusive`
  because the frozen fixture/oracle contract is internally contradictory.
- The only forward route is
  `remediate_fixture_execution_oracle_adjudication_gaps`. It is a future
  admission boundary, not an M7 scale pass; P-03 is not repaired, replaced, or
  rerun.

## Verification commands and results

Commands were run from `/Users/peter/projects/ai_verification-m7-99` using the
repository virtualenv:

```text
/Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -o addopts='' -q \
  tests/bench/test_current_claim_matrix.py \
  tests/bench/test_m6_case_package.py \
  tests/bench/test_m6_cohort.py
42 passed in 5.12s

/Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -o addopts='' -q
733 passed in 21.56s

git diff --check
pass
```

Relevant tool versions:

```text
uv 0.11.7
git 2.50.1
Python 3.11.15
pytest 9.0.3
jsonschema 4.26.0
PyYAML 6.0.3
```

## Changed surfaces

- `README.md`: current milestone moved from pending M6 to completed M6 and M7
  entry boundary.
- `HANDOFF.md`: tracker/dependency narrative now records the closed M6 chain,
  immutable P-03 gap, and M7 next steps.
- `CONTEXT.md`: current milestone boundary records the six-package aggregate and
  M7 mission.
- `docs/current-capability-claim-matrix.md`: adds the M6 population row and
  forward admission rule; removes stale "M6 is next" narrative.
- `docs/research/2026-07-19-verification-gap-register.md`: records M6 result and
  M7 route without inflating capability claims.
- `tests/bench/test_current_claim_matrix.py`: checks living-doc agreement,
  six-package/36-lane/P-03 facts, forward route, and absence of stale M6-current
  language.

## Evidence inventory and checksums

The source evidence consumed by this documentation update remains committed at
`docs/runs/2026-08-03-issue-88-aggregate/`:

```text
README.md
aggregate.json
aggregate.md
artifact-checksums.txt
independent-audit.json
independent-audit.md
qualification package JSON files (H-01..H-03, P-01..P-03)
```

SHA-256 checksums of the primary aggregate artifacts at validation time:

```text
1cea67b9ca137df3ad3830f27a947acb226a90dd07d8efbb2e528bde80a56cac  README.md
e6bce157336ffd95e017dcd7deffd1424f5ce3abdba9a92ec868415b8a7243a4  aggregate.json
9b2ff91d23f5f8df9e5589b5117f12163a1033a3608bf6c1158192edacbcec5d  aggregate.md
d03921745f3ae6bcf2b3d29700bc7f87e23fbcea00111211ca6fcb2587f8cdcd  artifact-checksums.txt
```

## Known gaps and claim boundary

- No device/manual verification applies to this documentation-only slice.
- The P-03 contradiction remains a forward remediation item and is not evidence
  of a repaired or rerun experiment.
- M6 evidence supports only its frozen local host/fixture/device/run contracts;
  it does not establish M7 scale, Android-wide coverage, benchmark-wide rates,
  physical/OEM coverage, or upstream acceptance.
- This run record becomes durable evidence with the source-of-truth commit and
  merge; the aggregate artifacts it cites are already committed and checksummed.

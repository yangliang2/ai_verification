# Issue #85 — Qualification Case Package

Date: 2026-08-03
Branch: `issue-85-case-package`
Base: `32234a63b47e1b48058a4d5b1fbece389a05bedb` (merged #91)

## Decision

The common M6 Qualification Case Package contract and fail-closed six-slot
aggregate are implemented. This change validates package identity and
append-only attempt accounting, adapts existing artifact outputs without
changing oracle semantics, keeps historical/prospective summaries separate,
and renders deterministic JSON and Markdown from one aggregate model.

This is a contract and validation slice only. It does not claim that the M6
36-lane formal execution has happened, and it does not make an upstream
Wikimedia change.

## Verification commands

The exact commands and captured outputs are recorded beside this file:

| Check | Command | Result |
|---|---|---|
| Focused package tests | `uv run --with pytest --with pyyaml --with jsonschema --python 3.14 pytest tests/bench/test_m6_case_package.py -q` | see `focused-tests.txt` |
| Cohort compatibility tests | `uv run --with pytest --with pyyaml --with jsonschema --python 3.14 pytest tests/bench/test_m6_case_package.py tests/bench/test_m6_cohort.py -q` | see `cohort-tests.txt` |
| Complete suite | `uv run --with pytest --with pyyaml --with jsonschema --python 3.14 pytest -rA --tb=short` | see `full-tests.txt` |
| Schema/package build admission | `uv run --with build --python 3.14 python -m build --wheel --outdir /tmp/aiverify-85-dist` | see `build.txt` |

Observed complete-suite result: 709 passed, 3 pre-existing L2
`DeprecationWarning`s, 16.85 seconds pytest time (17.58 seconds wall time).
The focused package suite contains 13 test cases after parametrization and
passes; the package-plus-cohort compatibility run contains 30 cases and
passes.

## Implemented files

- `src/aiverify/bench/m6_case_package_schema.json` — versioned Draft 2020-12
  envelope for historical and prospective packages.
- `src/aiverify/bench/m6_case_package.py` — duplicate-key-safe loader, semantic
  identity/reference checks, append-only ledger reconciliation,
  `QualificationAttemptInventory`, `QualificationCasePackage`,
  `QualificationAggregate`, aggregate validation, CLI, and deterministic
  structured/Markdown renderers.
- `tests/bench/test_m6_case_package.py` — valid input, identity omissions,
  checksum tampering, hidden attempts, forbidden claim leakage, adjudication
  contradiction, retry ordering, six-slot aggregation, and byte-stable
  render tests.
- `tests/bench/test_m6_cohort.py` — package-data expectation updated for the
  second packaged schema.
- `pyproject.toml` — packages the new schema with `aiverify.bench`.

## Scope and limitations

- Artifact references are repository-relative POSIX paths and SHA-256 bound.
- Formal case selection, candidate replacement, Android journeys, and the
  36-lane execution remain outside this issue.
- The package deliberately preserves the existing oracle output; it only
  checks accountability and identity consistency around it.
- The report model exposes local conclusions, accountability, adjudication,
  and operational timing only. Historical and prospective denominators are
  never combined.

## Regeneration

From the repository root, install the declared project dependencies (the
commands above use `uv`), then run the focused/full commands. For an admitted
package set, use:

```text
python -m aiverify.bench.m6_case_package validate <package.json> --repo-root .
python -m aiverify.bench.m6_case_package aggregate \
  --manifest bench/m6/m6-qualification-v1.yaml \
  --packages <H-01.json> <H-02.json> <H-03.json> <P-01.json> <P-02.json> <P-03.json> \
  --repo-root . --json-output aggregate.json --markdown-output aggregate.md
```

Both reports are generated from the same validated aggregate object and must
be byte-for-byte stable when inputs and tool versions are unchanged.

## Artifact inventory

- `focused-tests.txt`, `cohort-tests.txt`, `full-tests.txt`: captured test
  output and exit status.
- `build.txt`: captured wheel build output and exit status.
- `build-wheel.sha256`: checksum of the wheel emitted at
  `/tmp/aiverify-85-dist/aiverify-0.1.0-py3-none-any.whl`; the wheel is an
  external build product and is not part of the source commit.
- `environment.txt`: Python, uv, pytest, jsonschema, PyYAML, and git identity.
- `checksums.sha256`: SHA-256 inventory for this run record and implementation
  inputs.

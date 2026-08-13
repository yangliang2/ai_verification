# Issue #163 — explicit external-fixture gate

Status: implementation and local verification complete on
`issue-163-external-fixture-gate`. This run record becomes durable with the
branch commit that contains this directory; the exact pushed and merged evidence
identity is recorded in the Issue #163 completion comment.

## Objective and source identity

- Issue: `#163` (`bug`, `ready-for-agent`).
- Base revision: `314831758f723f3362e44144a62dc44c3f31a1c0`.
- Base tree: `8edb3483d5041d64b3bcd5fc660be240c9ddfbe0`.
- Tested implementation revision:
  `4fec201acb357fff56351780fb077771c0694578`.
- Tested implementation tree:
  `c7ceb94e31fa046bb50c4e530786ef2c140fa2df`.
- Tested evidence revision:
  `8b3cb2508f243f461c4fe6ae3fffbc70310ef293`.
- Tested evidence tree:
  `0b78bf67d7131ecff3b629fa752bfcac26780fcf`.
- The tested evidence revision is the first commit containing both the tested
  implementation and this run record with its checksum ledger. The exact final
  reconciliation and merged identities are recorded in the Issue #163 completion
  comment.
- Claim boundary: pytest test-infrastructure hardening only. Production formal
  defaults, discovery identity rules, and frozen #137/#154/#157 evidence were not
  changed, invoked, or reinterpreted.

## Implemented acceptance criteria

- `external_fixture` is a registered pytest marker. Marked tests are skipped by
  default regardless of repository-external path existence.
- `--run-external-fixtures` explicitly admits marked tests. The option and marker
  appear in ordinary project `pytest --help` and `pytest --markers` output.
- Explicit admission does not weaken discovery identity. A generated non-Git
  fixture fails with `DiscoveryContractError: source identity command failed`.
- The historical frozen-target regression changed only from a directory-based
  `skipif` to the marker. Its body still requires the exact target-specific
  mismatch and asserts that no formal root is created.
- Subprocess contract tests cover default skip, explicit admission, strict invalid
  source failure, and help/marker discoverability. Their environment ignores
  user-level `PYTEST_ADDOPTS` and auto-loaded third-party plugins.
- The README documents the default and explicit-admission workflows and the
  unchanged fail-closed identity boundary.

## TDD record

Baseline bug reproduction on the base revision:

```text
/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q tests/bench/test_m9_recovery_formal.py::test_frozen_target_specific_mismatch_is_side_effect_free
EXPECTED FAILURE: 1 failed in 1.64s; real 1.81s, user 0.23s, sys 1.19s.
DiscoveryContractError: source identity command failed: git rev-parse --show-toplevel: fatal: not a git repository
```

Default-gate tracer before the plugin existed:

```text
/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q tests/test_external_fixture_gate.py::test_default_run_skips_external_fixture
EXPECTED RED: 1 failed in 1.62s; real 1.91s, user 0.17s, sys 1.24s.
The isolated pytest process could not import the not-yet-implemented external-fixture plugin.
```

Explicit-admission tracer before the option existed:

```text
/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q tests/test_external_fixture_gate.py::test_explicit_option_runs_external_fixture
EXPECTED RED: 1 failed in 0.08s; real 0.18s, user 0.13s, sys 0.04s.
pytest rejected the unknown --run-external-fixtures argument with exit code 4.
```

The strict-source-identity characterization passed when first added because the
production acquisition boundary was already fail closed; it guards the gate from
turning an admitted invalid source into a skip.

## Final verification on the tested implementation revision

Tools:

- macOS 26.3 (25D125), Darwin 25.3.0
- Git 2.50.1 (Apple Git-155)
- uv 0.11.7 (`9d177269e`, 2026-04-15, aarch64-apple-darwin)
- Python 3.11.15
- pytest 9.1.1

Commands and results:

```text
/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q tests/test_external_fixture_gate.py
PASS: 4 passed in 2.04s; real 2.33s, user 0.57s, sys 1.31s.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q tests/bench/test_m9_recovery_formal.py::test_frozen_target_specific_mismatch_is_side_effect_free -rs
PASS: 1 skipped in 0.10s; real 0.41s, user 0.16s, sys 0.05s.
Skip reason: repository-external fixture tests require explicit admission.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q tests/bench/test_m9_recovery_formal.py::test_frozen_target_specific_mismatch_is_side_effect_free --run-external-fixtures
EXPECTED STRICT FAILURE: 1 failed in 0.16s; real 0.33s, user 0.21s, sys 0.05s.
The admitted stale path raised DiscoveryContractError because it is not a Git repository.

uv run --extra dev python -m pytest --help | rg -n -A2 '^aiverify:|--run-external-fixtures'
PASS: the aiverify option group lists --run-external-fixtures and its admission description.

uv run --extra dev python -m pytest --markers | rg -n -A1 '^@pytest.mark.external_fixture'
PASS: external_fixture is registered as requiring an explicitly admitted repository-external fixture.

/usr/bin/time -p uv run --extra dev python -m compileall -q src tests
PASS: exit 0; real 0.23s, user 0.02s, sys 0.03s.

uv run --extra dev python -m pytest --collect-only -q | awk -F': ' 'NF == 2 {sum += $2} END {print sum}'
PASS: 1022 tests collected.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs
PASS: 1021 passed, 1 skipped in 50.45s; real 50.57s, user 30.01s, sys 16.39s.

git diff --check
PASS: exit 0.

uv run --extra dev python -m aiverify.bench.run_record_checksums docs/runs/2026-08-12-issue-163-external-fixture-gate --verify
PASS: checksum inventory verified for 2 artifacts.

uv run --extra dev python -m pytest -o addopts='' -q tests/bench/test_current_claim_matrix.py tests/bench/test_run_record_checksums.py
PASS: 13 passed in 0.02s.
```

## External fixture and side-effect inventory

`/private/tmp/m9-r3-snapshot-b` was inspected read-only before and after
verification. Both observations reported a directory modified at
`2026-08-12T00:00:02-0400` with no `.git` entry. It was not repaired, moved,
deleted, initialized, or otherwise mutated.

No emulator, physical device, Android build/install, model invocation, formal
consumer, namespace claim, mapping release, oracle, Falsification Review, or
manual UI step was performed. The explicitly admitted negative check invoked
read-only discovery far enough to reject the invalid Git identity; it did not
start a formal run or create the monkeypatched formal root.

## Artifact inventory and known gap

- `README.md` — source identities, red/green commands, results, scope, and gaps.
- `verification.json` — machine-readable verification, external state, and
  mutation inventory.
- `checksums.sha256` — checksum ledger for the two artifacts above.

Known gap: the exact valid historical frozen source is unavailable on this host,
so the target-specific expected-mismatch body was not replayed against a valid
snapshot. The body and its no-formal-root assertion are unchanged, the generic
explicit-admission execution path is covered, and the available stale snapshot
was deliberately allowed to fail strict source identity. No formal evidence is
claimed from that expected negative run.

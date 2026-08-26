# Issue #200 source-of-truth verification

Date: 2026-08-26 (America/New_York)

Status: **repository evidence; durable when committed with the implementation**. This record covers the V1
source-of-truth contract only. It does not authorize or claim a runtime
calibration, Android capability, device result, or model evaluation.

## Outcome

Issue #200 is implemented as a staged, model-free `verify-candidate` boundary
for the OpenCalc Runtime Calibration V1 family. The checked-in candidate under
[`bench/runtime-calibration/opencalc-input-save-enabled-v1/`](../../../bench/runtime-calibration/opencalc-input-save-enabled-v1/)
contains the family manifest, matched source pair, discovery commitments, claim
boundary, eight contract schemas, and four opaque lane projections with their
driver plans, recipes, and Run Specs. The candidate manifest enumerates 28
artifacts and binds each artifact's raw and canonical SHA-256 identity.

The public command accepted the frozen candidate with:

- family: `opencalc-runtime-calibration-v1` / `v1`;
- candidate identity: `d8613a9af06f2d18eec3439da51426f4b837fe5b83b91449d1017aa7f302286e`;
- artifact inventory: 28 entries,
  `f55bbb0161d011102a3bbd823901d118da39a0319619e158d69984b368876492`;
- package declaration: `com.darkempire78.opencalculator.debug`;
- launcher declaration:
  `com.darkempire78.opencalculator.activities.MainActivity`.

Invalid, incomplete, duplicated, unknown, contradictory, drifted, and
wrong-version inputs are rejected with stable reasons before any build,
device, process, network, or model operation. Stage receipts are written only
under the caller-owned output root: a start receipt precedes candidate
validation, and the terminal receipt binds the start checksum and complete
candidate inventory. An interrupted start has no terminal receipt and is
reported as abandoned.

## Implementation surface

- `src/aiverify/bench/runtime_calibration.py`: strict document parsing,
  canonical identities, frozen V1 candidate validation, staged receipt
  writing, receipt integrity checks, status helpers, and the public CLI;
- `tests/bench/test_runtime_calibration.py`: public-command and serialized-
  receipt coverage for acceptance, rejection reasons, output-root safety,
  interruption, and receipt tampering;
- `bench/runtime-calibration/opencalc-input-save-enabled-v1/`: committed V1
  public-input set;
- `docs/adr/0004-first-class-journey-driver-backends.md` and
  `docs/adr/0005-accountable-runtime-calibration-family.md`: proposed ADRs;
- `docs/opencalc-runtime-calibration-v1.md` and `CONTEXT.md`: published
  vocabulary, immutable claims, boundaries, and stage contract.

## Exact verification commands and results

All commands ran from `/Users/peter/projects/ai_verfication`.

### Candidate acceptance

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.runtime_calibration verify-candidate --candidate-root bench/runtime-calibration/opencalc-input-save-enabled-v1 --output-root /Users/peter/projects/ai_verfication/docs/runs/2026-08-26-issue-200-source-of-truth/verification/candidate-stage > /Users/peter/projects/ai_verfication/docs/runs/2026-08-26-issue-200-source-of-truth/verification/candidate-terminal.json
```

Result: exit 0; terminal status `accepted`; 28 artifacts; the serialized
stdout receipt is `verification/candidate-terminal.json`, and the checksum-
bound stage receipts are under `verification/candidate-stage/`.

### Public contract suite

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -o addopts='' -q tests/bench/test_runtime_calibration.py --junitxml=docs/runs/2026-08-26-issue-200-source-of-truth/verification/contract-pytest.xml
```

Result: 14 passed, 0 failed, 0 skipped; pytest time 1.358s; wall time 1.50s.

### Full repository regression

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/pytest -p no:cacheprovider -o addopts='' -qq --junitxml=docs/runs/2026-08-26-issue-200-source-of-truth/verification/full-pytest.xml
```

Result: 1,307 collected; 1,306 passed, 0 failed, 1 skipped; JUnit suite time
449.819s; wall time 450.16s. The one skip is the pre-existing external-fixture
test that requires the explicit `--run-external-fixtures` admission flag.

### Static checks

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q src/aiverify/bench/runtime_calibration.py tests/bench/test_runtime_calibration.py
uv run --with ruff ruff check src/aiverify/bench/runtime_calibration.py tests/bench/test_runtime_calibration.py
git diff --check
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m aiverify.bench.run_record_checksums docs/runs/2026-08-26-issue-200-source-of-truth
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m aiverify.bench.run_record_checksums docs/runs/2026-08-26-issue-200-source-of-truth --verify
```

All five static/checksum commands exited 0. Checksum generation wrote
`checksums.sha256`, and checksum verification reported a verified inventory.

## Artifact inventory

- `verification/candidate-stage/stage-start.json`: start receipt, including
  candidate/output roots and start identity;
- `verification/candidate-stage/stage-terminal.json`: accepted terminal with
  all 28 raw/canonical artifact digests and terminal identity;
- `verification/candidate-terminal.json`: exact public CLI JSON output;
- `verification/contract-pytest.xml`: 14-case public contract JUnit receipt;
- `verification/full-pytest.xml`: full repository JUnit receipt;
- `tool-versions.txt`: host, Python, pytest, Ruff, uv, and Git versions;
- `verification.json`: machine-readable commands, counts, identities, and
  claim boundary;
- `code-review.md`: two-axis final review record;
- `checksums.sha256`: SHA-256 inventory for every other file in this record.

No screenshot, layout dump, logcat, APK, emulator/device session, build output,
model trace, or manual runtime artifact exists for this issue. The pre-existing
exploratory OpenCalc record at
`docs/runs/2026-08-23-opencalc-calibration/` is not consumed as runtime
evidence by this verifier.

## Known gaps and claim boundary

- No Android CLI, adb, emulator, Gradle, APK inspection, source checkout,
  network fetch, or model invocation was performed by `verify-candidate`.
- The candidate records upstream provenance and future build/runtime
  declarations; it does not prove those declarations operationally.
- Discovery materialization, deterministic backend execution, source
  preparation, preflight, device lifecycle evidence, oracle outcomes, reducer
  output, and capability claims remain later issues.
- `mypy` is not configured or installed in the repository environment and was
  not used; Ruff and Python compilation provide the static checks recorded
  above.
- This run record is durable only when included in the implementation commit;
  the issue comment records the commit that carries it.

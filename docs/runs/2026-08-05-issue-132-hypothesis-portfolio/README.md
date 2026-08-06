# M9 Hypothesis Portfolio

Issue: [#132](https://github.com/yangliang2/ai_verification/issues/132)<br>
Base: `origin/main` at `f9e25a2a1fa2cdb570a0d4501e274ef8b93d4ccf`<br>
Worktree: `/Users/peter/projects/ai_verification-m9-132`

This record documents the bounded, side-effect-free M9 hypothesis-generation
slice. It adds exactly three approved prior definitions (temporal,
state-evolution, and lifetime/ownership drift), a strict ProjectTarget-only
generation request/response boundary, deterministic candidate validators and
priority factors, and a frozen top-three portfolio with append-only selection
ledger and remaining frontier. Existing temporal and state-evolution
derivation entry points remain unchanged.

The backend receipt below is a bounded local fake-backend invocation. It is
not a production provider call, does not use a formal M9 holdout, and contains
no hidden mapping or outcome data. No scenario, journey, oracle, verdict,
cohort, Finding, or runtime execution contract is sent to the generation role.

## Scope and result

`HypothesisGenerationRequest` binds a `ProjectTarget`, acquired
provenance-bound `QualityContextGraph`, exactly three `RiskPrior` definitions,
and a positive budget. `HypothesisGeneratorIdentity` captures backend,
requested model, effective model, invocation ID, and an identity digest.
`HypothesisGenerationResponse` captures the authoritative backend-output
digest and preserves malformed candidates as auditable rejections.

`validate_hypothesis_candidate` rejects target/prior/operator mismatch, missing
or non-known facts, missing provenance, unsupported or circular causal chains,
generic non-falsifiable suspicion, output leakage, and duplicate semantic
candidates. `calculate_risk_priority` records impact, propagation reach,
context sensitivity, uncertainty, evidence gap, and estimated probe cost after
capture; the score is only an ordering aid. `freeze_hypothesis_portfolio`
orders deterministically, freezes at most three, records every other candidate
as rejected or deferred in the hash-chained ledger, and records remaining
prior/fact frontier and budget.

## Verification commands and results

Commands ran on 2026-08-05. Timings are `/usr/bin/time -p` values where shown.

```text
uv venv .venv && uv pip install --python .venv/bin/python pytest pyyaml jsonschema
→ exit 0; CPython 3.11.15 environment with pytest 9.1.1, pyyaml 6.0.3,
  jsonschema 4.26.0.

PYTHONPATH=src /usr/bin/time -p .venv/bin/pytest -q tests/discovery/test_hypothesis_portfolio.py
→ 6 passed, 0 failed; exit 0; real 0.22s, user 0.19s, sys 0.01s.

PYTHONPATH=src /usr/bin/time -p .venv/bin/pytest -q \
  tests/discovery/test_risk_derivation.py \
  tests/discovery/test_state_evolution_risk.py \
  tests/discovery/test_campaign.py tests/discovery/test_contracts.py \
  tests/discovery/test_acquisition.py tests/discovery/test_hypothesis_portfolio.py
→ 60 passed, 0 failed; exit 0; real 2.59s, user 1.75s, sys 0.68s.

PYTHONPATH=src /usr/bin/time -p .venv/bin/pytest -q
→ 840 passed, 0 failed; exit 0; real 29.04s, user 20.54s, sys 4.87s.
  A separate `--collect-only` count confirmed 840 tests.

PYTHONPATH=src .venv/bin/python -m compileall -q src tests
→ exit 0.

PYTHONPATH=src .venv/bin/python - <<'PY' ... self_validate_schema() ... PY
→ exit 0; discovery schema self-validation passed.

git diff --check
→ exit 0.

uv build --out-dir docs/runs/2026-08-05-issue-132-hypothesis-portfolio/artifacts
→ source distribution and wheel built successfully; package `aiverify 0.1.0`;
  real 0.92s, user 0.53s, sys 0.21s; final artifact sizes and SHA-256 values
  are listed below.

PYTHONPATH=src .venv/bin/python docs/runs/2026-08-05-issue-132-hypothesis-portfolio/validate_receipt.py
→ exit 0; status=passed; source_contract_checks=12; run_record_checks=8;
  package_artifact_checks=2; checksum_manifest_checks=13.

(cd docs/runs/2026-08-05-issue-132-hypothesis-portfolio && shasum -a 256 -c checksums.sha256)
→ 13/13 entries OK; exit 0.
```

## Artifact inventory and checksums

- `README.md`: scope, exact verification commands, result, and claim boundary.
- `bounded-generation-receipt.json`: bounded fake-backend identity/output/
  portfolio receipt; formal holdout is explicitly false.
- `validate_receipt.py`: deterministic source/schema/receipt/package/checksum
  validator.
- `validation-output.json`: committed validator result.
- `tool-versions.txt`: host and tool identity receipt.
- `artifacts/aiverify-0.1.0-py3-none-any.whl`: package artifact, 339972 bytes;
  SHA-256 `55f522b3b2b882c86e39d0330569e083f90db9f637466373e2c0816da8fd56d4`.
- `artifacts/aiverify-0.1.0.tar.gz`: source distribution, 308386 bytes;
  SHA-256 `8b905783a098c445ba062c9fe0a6eb05beb5bae06c143c7c9019d9b610ddffc0`.
- `checksums.sha256`: SHA-256 inventory for this record, source contracts,
  tests, fake receipt, and package artifacts.

No APK, screenshot, layout dump, logcat, emulator/device receipt, production
repository, external project state, credentials, live provider receipt, or
formal holdout artifact was generated.

## Manual steps, known gaps, and claim boundary

Manual/device steps: none. The bounded receipt uses a local deterministic fake
backend with requested/effective fixture model identity and one in-process
call. No external model or provider was contacted.

Known gaps: priority factors are deterministic ordering aids, not calibrated
probabilities; the three priors are an approved M9 registry, not a completeness
claim; lifecycle derivation remains a bounded static contract. This issue does
not create scenarios, Attack Plans for the portfolio, runtime evidence,
Findings, cohort decisions, formal holdout results, production/upstream
validation, OEM/ColorOS claims, benchmark rate/recall/completeness claims, or
automatic remediation.

Local-only claim boundary: evidence supports only the committed contracts,
fake-backend receipt, deterministic validators/portfolio, regression tests,
package build, and checksums listed here. It does not support any formal M9
qualification result or any runtime/project-wide risk claim.

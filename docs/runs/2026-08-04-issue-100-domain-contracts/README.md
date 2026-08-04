# M7-1 domain-contracts validation

Date: 2026-08-04

Issue: [#100](https://github.com/yangliang2/ai_verification/issues/100)

Worktree: `/Users/peter/projects/ai_verification-m7-100`

Base: `origin/main` at `27d807d52c2073d4568226170ca20d79218ffd7a`
Scope: local contract/schema validation only; no Android device, emulator, build
host, or external project checkout was touched.

## Verification commands and results

All commands were run from the worktree above with the repository virtualenv:

```text
/Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -o addopts='' -q tests/discovery/test_contracts.py
17 passed in 0.11s

/Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -o addopts='' -q
732 passed in 19.52s

/Users/peter/projects/ai_verfication/.venv/bin/python -m json.tool \
  src/aiverify/discovery/discovery_schema.json >/dev/null
pass

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python - <<'PY'
from aiverify.discovery import self_validate_schema
self_validate_schema()
print('schema self-validation: pass')
PY
schema self-validation: pass

git diff --check
pass

uv build --out-dir /tmp/aiverify-m7-build.V6nVDV
Successfully built aiverify-0.1.0.tar.gz
Successfully built aiverify-0.1.0-py3-none-any.whl
```

The build environment did not provide `python -m build` or `pip`; `uv build`
used the repository's setuptools backend instead. The wheel contains the
versioned schema and all discovery modules:

```text
aiverify/discovery/contracts.py
aiverify/discovery/discovery_schema.json
aiverify/discovery/models.py
aiverify/discovery/schema.py
```

Build artifact checksums (artifacts remain in the local temporary directory and
are not treated as durable evidence):

```text
f047b8b452c762e39db57dd94cdfc5a5de051063960220e7f41c53a4b8fbb45f  aiverify-0.1.0.tar.gz
b5208398beb1f0f1fcedfa461bd215c024c65c67fbb17c58f0c78a56c52e71e6  aiverify-0.1.0-py3-none-any.whl
```

## Acceptance mapping

- `CONTEXT.md` defines Discovery Campaign, ChangeTarget, ProjectTarget, Quality
  Context Graph, Context Fact, Quality Contract, Contract Drift, Risk Prior,
  Attack Operator, Risk Hypothesis, Failure Chain, Attack Plan, Finding,
  Residual Risk, and Project Risk Map.
- `docs/adr/0003-discovery-campaign-above-run-spec.md` records the seam between
  discovery orchestration and one-experiment Run Spec execution.
- `src/aiverify/discovery/models.py` provides strict, versioned targets,
  provenance-bound facts, and graph snapshots.
- `src/aiverify/discovery/contracts.py` provides the causal risk contracts,
  campaign aggregate, evidence-backed outcomes, and side-effect-free admission.
- `src/aiverify/discovery/discovery_schema.json` and `schema.py` provide
  Draft 2020-12 self-validation and strict serialized-contract validation.
- `tests/discovery/test_contracts.py` covers round trips, null/unknown state,
  target ambiguity, dangling references, tamper rejection, v1 compatibility,
  contradiction rejection, and missing pre-execution relationships.

## Known limitations

- This slice does not extract context from Kotlin/Android artifacts, generate or
  rank risks with an LLM, execute Android experiments, or claim upstream/OEM
  behavior.
- Build checksums point to local-only temporary artifacts; the source, tests,
  schema, ADR, and this run record become durable only after commit and merge.
- Manual Standards and Spec review was performed against `origin/main` and #100;
  no device or real-project checkout admission was needed for this domain-only
  issue.

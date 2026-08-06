# M9 #135 — Independent Falsification Review

This run records the clean-context, separately identified challenge pass for a
candidate Finding. The review contract accepts only immutable source and
execution references, a frozen hypothesis and admitted plan, an oracle
contract reference, the candidate Finding, raw evidence, relevant control
evidence, and a claim boundary. It requires six ordered dimensions, typed
reasons, evidence binding, identity separation, and fail-closed reconciliation.
The review path has no import or delegation path to the production oracle or
adjudication implementation.

The bounded receipt is a local fake-backend invocation on a non-holdout fixture.
It is not a production provider call and does not select, reveal, or execute
the M9 formal cohort.

## Verification commands and results

Commands ran on 2026-08-05/06 in the dedicated clean worktree after rebasing
onto `origin/main` containing #133. Timings are `/usr/bin/time -p` values.

```text
PYTHONPATH=src /usr/bin/time -p .venv/bin/pytest -q tests/discovery/test_falsification_review.py
→ 7 passed, 0 failed; real 0.16s, user 0.12s, sys 0.02s.

PYTHONPATH=src .venv/bin/pytest --collect-only -q | awk -F': ' '/: [0-9]+$/{s+=$2} END{print s+0}'
→ 852 collected tests.

PYTHONPATH=src /usr/bin/time -p .venv/bin/pytest -q -rA
→ 852 collected and all 852 reported PASSED, 0 failed; real 28.43s,
  user 20.92s, sys 4.69s.

PYTHONPATH=src .venv/bin/python -m compileall -q src tests
→ exit 0.

PYTHONPATH=src .venv/bin/python -c 'from aiverify.discovery.schema import self_validate_schema; self_validate_schema(); print("schema self-validation passed")'
→ exit 0; schema self-validation passed.

git diff --check
→ exit 0.

/usr/bin/time -p uv build --quiet --out-dir docs/runs/2026-08-05-issue-135-falsification-review/artifacts
→ package `aiverify 0.1.0`; wheel 357745 bytes, SHA-256
  `d166ec72530a744fc81584097f04504c8858e566f40a52301d13d5acbb6a6c35`;
  sdist 324584 bytes, SHA-256
  `db9513dbb44892d735cec2b5a26fa06bfacc66df6cabd6678adfd48e07d0e4c5`;
  real 0.91s, user 0.53s, sys 0.22s.

PYTHONPATH=src .venv/bin/python docs/runs/2026-08-05-issue-135-falsification-review/validate_receipt.py
→ exit 0; validator output is committed in `validation-output.json`.

(cd docs/runs/2026-08-05-issue-135-falsification-review && /usr/bin/shasum -a 256 -c checksums.sha256)
→ all manifest entries OK; exit 0.
```

## Contract and bounded receipt

Implementation and tests are in:

- `src/aiverify/discovery/falsification_review.py`: immutable context and
  artifact references, separate reviewer identity, six-dimensional review,
  fail-closed invocation, typed reasons, serialization, and reconciliation.
- `src/aiverify/discovery/discovery_schema.json` and
  `src/aiverify/discovery/schema.py`: checked-in schemas and contract map.
- `src/aiverify/discovery/__init__.py`: public discovery exports.
- `tests/discovery/test_falsification_review.py`: clean-context allowlisting,
  all three review outcomes, identity separation, malformed output rejection,
  forbidden material in any allowlisted context field, evidence tampering
  rejection, serialization round trips, and AST proof that the module has no
  production oracle/adjudication import path.

The fake backend was invoked once with:

- backend: `fake-falsifier`;
- role: `verification-agent-falsification-reviewer-v1`;
- requested/effective model: `fixture-model-v1` / `fixture-model-v1`;
- provider family: `family-a`;
- invocation: `review-invocation-1`;
- same-family limitation: review supports implementation-path separation only;
- result: complete `survived` review, six supported dimensions, aggregate
  support reconciled without rewriting the Finding or raw evidence;
- context digest:
  `9298f77fe60044ce97538470ea32b6c5d750b5e49974aed21ae6b105588e6971`;
- reviewer identity digest:
  `33826eb03dc8f9479b61ef7ce38b37418437dade8050458850efedce2eb97327`;
- authoritative output digest:
  `12a14cb163f6a555934c5fb45f8c751d097e5ec42b0be732d1fefe244beb5aea`.

See `bounded-review-receipt.json` for the allowlisted context, raw output,
effective identity, result, and reconciliation. `validate_receipt.py`
reconstructs and replays the fixture, validates the four discovery contracts,
checks package inventory, and checks the committed checksum manifest.

## Artifact inventory and claim boundary

- `bounded-review-receipt.json`: one fake-backend review receipt, including
  context, raw six-dimension output, identity, result, and reconciliation.
- `validate_receipt.py`: deterministic source/schema/receipt/package/checksum
  validator.
- `validation-output.json`: committed validator result.
- `tool-versions.txt`: host and tool identity.
- `artifacts/aiverify-0.1.0-py3-none-any.whl`: 357745 bytes;
  SHA-256 `d166ec72530a744fc81584097f04504c8858e566f40a52301d13d5acbb6a6c35`.
- `artifacts/aiverify-0.1.0.tar.gz`: 324584 bytes;
  SHA-256 `db9513dbb44892d735cec2b5a26fa06bfacc66df6cabd6678adfd48e07d0e4c5`.
- `checksums.sha256`: SHA-256 inventory for this run and package artifacts.

No APK, screenshot, layout dump, logcat, emulator/device, production
provider, upstream project, formal M9 holdout, hidden mapping, ground truth,
retry, replacement, runtime verdict, or external side effect was used. The
result supports only the checked-in independent-review contract, its
fail-closed reconciliation seam, and this exact local fake-backend receipt. It
does not claim provider diversity, discovery effectiveness, project
completeness, benchmark rate, Android/OEM/ColorOS coverage, or production
behavior.

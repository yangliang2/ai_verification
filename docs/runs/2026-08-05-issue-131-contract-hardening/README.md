# M9 Context Acquisition Contract Hardening

Issue: [#131](https://github.com/yangliang2/ai_verification/issues/131) follow-up

This run records a narrowly scoped post-merge contract correction for the
bounded ProjectTarget Context Acquisition slice. It hardens the Python
contracts to agree with the checked-in JSON schema: boolean `schema_version`
values are rejected, the request normalizes sequence input, `no_diff` is
exactly `true`, and graph/receipt source provenance must match the target.
No acquisition behavior, adapter scope, runtime behavior, or M9 holdout
behavior was expanded.

The follow-up was developed in the clean worktree
`/Users/peter/projects/ai_verification-m9-131-followup` from the then-current
`origin/main` (`dd8824e330e120d863c65a7f32c007357b2c785a`). The original
`issue-73-accessibility-slice` worktree and its experimental files were not
modified.

## Verification commands and results

Commands ran on 2026-08-05. Timings are `/usr/bin/time -p` values where shown.

```text
uv venv .venv && uv pip install --python .venv/bin/python pytest pyyaml jsonschema
→ exit 0; pytest 9.1.1, pyyaml 6.0.3, jsonschema 4.26.0 installed in the
  worktree-local CPython 3.11.15 environment.

/usr/bin/time -p .venv/bin/pytest -q tests/discovery/test_acquisition.py
→ 7 passed, 0 failed; exit 0; real 5.64s, user 1.01s, sys 0.87s.

/usr/bin/time -p .venv/bin/pytest -q
→ 834 passed, 0 failed; exit 0; real 26.95s, user 20.92s, sys 4.99s.

.venv/bin/python -m compileall -q src tests
→ exit 0.

.venv/bin/python - <<'PY' ... Draft202012Validator.check_schema ... PY
→ exit 0; discovery JSON Schema parsed and self-validated.

git diff --check
→ exit 0.

uv build --out-dir docs/runs/2026-08-05-issue-131-contract-hardening/artifacts
→ source distribution and wheel built successfully; package `aiverify 0.1.0`;
  real 0.75s, user 0.52s, sys 0.19s; final artifact sizes and SHA-256 values
  are listed below.

.venv/bin/python docs/runs/2026-08-05-issue-131-contract-hardening/validate_receipt.py
→ exit 0; status=passed; source_contract_checks=6; run_record_checks=6;
  package_artifact_checks=2; checksum_manifest_checks=8.

(cd docs/runs/2026-08-05-issue-131-contract-hardening && shasum -a 256 -c checksums.sha256)
→ 8/8 entries OK; exit 0.
```

## Artifact inventory and checksums

- `README.md`: scope, exact commands, result, and claim boundary.
- `validate_receipt.py`: deterministic source/package/checksum validator.
- `validation-output.json`: committed validator result.
- `tool-versions.txt`: host and tool identity receipt.
- `artifacts/aiverify-0.1.0-py3-none-any.whl`: package artifact, 324563 bytes,
  SHA-256 `907c271e12719301e33bc54162fee2d6363044d2855687c250deda0bbd6d1be1`.
- `artifacts/aiverify-0.1.0.tar.gz`: source distribution, 293770 bytes,
  SHA-256 `fdf58fcc3aa7579f44a0dd1ff53baf3365d52d529c646584e35ef91f7a800b52`.
- `checksums.sha256`: SHA-256 inventory for this record, source files, and
  package artifacts.

No APK, screenshot, layout dump, logcat, device receipt, live backend receipt,
production repository, external project state, credentials, or formal M9
holdout artifact was generated.

## Manual steps, known gaps, and claim boundary

Manual/device steps: none. The checks are local Python contract, schema,
package, and checksum checks only.

Known gaps: this is a follow-up hardening patch, not a new Context Acquisition
adapter or a runtime validation. It does not establish source completeness,
device behavior, model/backend behavior, formal M9 holdout results, or any
production, OEM/ColorOS, benchmark-rate, recall, or completeness claim.

Local-only claim boundary: the evidence supports only the listed contract
hardening and regression tests in the committed repository state.

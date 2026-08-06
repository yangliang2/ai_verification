# M9 Context Acquisition

Issue: [#131](https://github.com/yangliang2/ai_verification/issues/131)<br>
Base: `origin/main` / `aa486e1ca32baa83c9766aa8937bf31b9c962655` at implementation start<br>
Branch: `m9-131-context-acquisition`

This record documents the bounded, read-only ProjectTarget Context Acquisition
slice. The implementation is committed at
`47322eadde64ee5e00788a10b78364f4c398e7c1` (the final evidence-pin commit is
recorded in the completion comment). Work was confined to
`/Users/peter/projects/ai_verification-m9-131`; the original
`issue-73-accessibility-slice` worktree was not modified.

## Scope and result

The new public contracts and entry points are `ContextAcquisitionRequest`,
`acquire_project_context`, and `acquire_context`. They accept only a clean,
immutable `ProjectTarget`, verify origin/commit/tree
identity and no diff with read-only Git commands, inspect tracked files in the
declared scope up to the target budget, and produce a provenance-bound
`QualityContextGraph`, `ContextAcquisitionReceipt`, and deterministic graph
checksum.

The bounded adapters cover Android manifest/component declarations, Gradle/
Maven/build/version descriptors, Kotlin/Java symbols and call sites,
persistence writer/reader/version/migration/restore/fallback evidence,
lifecycle/ownership boundaries, and quality/version signals. Missing,
ambiguous, unsupported, stale, contradictory, unreadable, and budget-exhausted
paths remain explicit unresolved receipt entries. Suggestions are receipt-only;
they cannot become known facts without source evidence. Historical descriptor
loading through `load_context_manifest` remains unchanged and is not called by
the new formal entry point.

The held-out test creates a raw source Git repository without a context manifest
or outcome mapping. It checks that facts and structural edges carry resolvable
file checksums, that graph/receipt round trips are deterministic, and that
contradictory and stale source descriptors do not become known evidence.

## Verification commands and results

All commands below ran from `/Users/peter/projects/ai_verification-m9-131` on
2026-08-05. Timings are `/usr/bin/time -p` values where shown.

```text
uv pip install --python .venv/bin/python pytest pyyaml jsonschema
→ exit 0; installed pytest 9.1.1, pyyaml 6.0.3, jsonschema 4.26.0 and their
  worktree-local dependencies in the isolated .venv.

.venv/bin/python -m pytest -q tests/discovery/test_acquisition.py
→ 6 passed, 0 failed; exit 0; real 1.47s, user 0.74s, sys 0.59s.

.venv/bin/python -m pytest -q tests/discovery/test_contracts.py tests/discovery/test_context_graph.py
→ 24 passed, 0 failed; exit 0; real 0.33s, user 0.27s, sys 0.03s.

.venv/bin/python -m pytest -ra
→ 833 passed, 0 failed in 27.88s; exit 0; real 27.97s, user 20.25s,
  sys 4.84s. No tests were skipped or deselected. This final run includes
  merged #130 production-seam admission tests.

.venv/bin/python -m compileall -q src tests/discovery/test_acquisition.py
→ exit 0.

python3 -m json.tool src/aiverify/discovery/discovery_schema.json >/dev/null
→ exit 0; checked the checked-in discovery schema parses as JSON.

.venv/bin/python docs/runs/2026-08-05-issue-131-context-acquisition/validate_receipt.py
→ first diagnostic run exited 1 because the validator glob matched the `.tar.gz`
  but not the wheel's hyphenated platform tag; the validator was corrected and
  the final run below passed. This was an evidence-validator defect, not a
  repository test or product failure.

(cd docs/runs/2026-08-05-issue-131-context-acquisition && shasum -a 256 -c checksums.sha256)
→ an intermediate diagnostic exited non-zero because the first checksum list
  used repository-root paths while this command runs from the evidence
  directory; paths were corrected to be run-directory-relative before the
  final 10/10 check below.

uv build --out-dir docs/runs/2026-08-05-issue-131-context-acquisition/artifacts
→ source distribution and wheel built successfully; package `aiverify 0.1.0`;
  final artifact sizes are 324492 bytes (wheel) and 293730 bytes (sdist);
  SHA-256 values are listed below; real 0.94s, user 0.56s, sys 0.22s.

git diff --check
→ exit 0.

.venv/bin/python docs/runs/2026-08-05-issue-131-context-acquisition/validate_receipt.py
→ exit 0; status=passed; source_contract_checks=10; run_record_checks=8;
  package_artifact_checks=2; checksum_manifest_checks=10.

(cd docs/runs/2026-08-05-issue-131-context-acquisition && shasum -a 256 -c checksums.sha256)
→ 10/10 entries OK; exit 0.
```

The package build has no Android SDK, APK, emulator, device, agent backend,
requested/effective model, production repository, or formal M9 holdout side
effect. The test-only temporary Git repositories use a public-looking
`example.invalid` origin and contain no defect/control mapping or expected
verdict.

## Artifact inventory and checksums

- `README.md`: this durable run record and claim boundary.
- `validate_receipt.py`: deterministic source/receipt/package/checksum validator.
- `validation-output.json`: committed validator result.
- `tool-versions.txt`: host, Python, uv, pytest, package, backend/model/device
  identity receipt.
- `artifacts/aiverify-0.1.0-py3-none-any.whl`: package artifact.
- `artifacts/aiverify-0.1.0.tar.gz`: source distribution artifact.
- `checksums.sha256`: SHA-256 inventory for the run record, validator output,
  source contract files, and package artifacts.
- No APK, screenshot, layout dump, logcat, device receipt, agent transcript,
  live backend receipt, or formal cohort artifact was generated.

Final artifact checksums:

```text
artifacts/aiverify-0.1.0-py3-none-any.whl  324492 bytes  5a99391d9955a11452a99bc1888a134b210a8b30eee839e4200ad0ecfd8b3dd3
artifacts/aiverify-0.1.0.tar.gz             293730 bytes  0f02d044079da060aeff00b4257ddbf9fa67f244208b1267d4285010c5f787f3
```

## Manual steps, known gaps, and claim boundary

Manual/device steps: none. No emulator, APK install/launch, production data,
external project state, upstream issue/PR, credentials, device network policy,
or M9 holdout was touched.

Known gaps: this is a bounded syntax/evidence acquisition slice, not a complete
Kotlin compiler/data-flow index. It does not infer risk, rank hypotheses, create
an Attack Plan, build or run an APK, select a cohort, release hidden mapping,
or support runtime, project-completeness, benchmark-rate, OEM/ColorOS,
production, upstream, or provider-independence claims. Runtime thread/process
observation and files outside the declared scope remain coverage frontier.

Local-only claim boundary: the evidence supports only the committed source
adapter contracts, deterministic receipt behavior, and test/package checks
listed here for the bounded local fixture. It does not support any formal M9
holdout result or a general ProjectTarget discovery capability claim.

# M9-0 source-of-truth reconciliation

Issue: [#129](https://github.com/yangliang2/ai_verification/issues/129)<br>
Base: `origin/main` / `957f108d88afd74a8787b42be568ab558c5fb9b1`<br>
Branch: `m9-129-source-of-truth`

## Scope and result

This run reconciles the living documentation after merged M8 and records the
approved M9 vocabulary and boundary. It does not implement M9 runtime code,
select a target, reveal a mapping, build an Android APK, invoke a Verification
Agent Backend, or execute a formal holdout. The result is documentation-only and
does not measure M9 capability.

Changed source-of-truth documents:

- `CONTEXT.md` — adds `Context Acquisition`, `Hypothesis Portfolio`,
  `Exploration Stop Rule`, and `Falsification Review`, including their
  relationships and avoided synonyms.
- `README.md` and `HANDOFF.md` — record merged M8 PR #127, the immutable
  `0/12 accountable` / `inconclusive` result, the no-rerun boundary, and the
  M9 ProjectTarget-only route.
- `docs/current-capability-claim-matrix.md` — records M8 as bounded failure
  evidence and M9 as planned/unmeasured with six lanes, a contradiction packet,
  three priors, and local-only claims.
- `docs/runs/2026-08-05-issue-129-source-of-truth/validate_docs.py` — checks
  glossary coverage, immutable M8 facts, M9 boundary facts, ADR decision, and
  relative links.

The ADR assessment is explicit: ADR-0001, ADR-0002, and ADR-0003 were reviewed;
#129 makes no new hard-to-reverse architecture, provider, data-ownership, or
production-operation decision, so no ADR is added.

## Verification commands and results

All commands below ran from `/Users/peter/projects/ai_verification-m9-129` on
macOS arm64, against the clean #129 branch. Timings are the `/usr/bin/time -p`
values where shown.

```text
.venv/bin/python docs/runs/2026-08-05-issue-129-source-of-truth/validate_docs.py
→ exit 0; status=passed; glossary_terms_checked=13; m8_facts_checked=8;
  m9_boundary_facts_checked=11; relative_links_checked=60; real 0.01s.

uv run pytest -o addopts='' -ra
→ 821 passed in 26.30s; exit 0; real 26.40s, user 19.76s, sys 3.94s.

Final post-evidence rerun: `uv run pytest -o addopts='' -ra`
→ 821 passed in 27.92s; exit 0; real 28.07s, user 20.82s, sys 4.46s.

uv run pytest -q
→ exit 0; full suite completed; real 27.03s, user 19.60s, sys 3.90s.

uv run python -m compileall -q src tests
→ exit 0; real 0.10s, user 0.06s, sys 0.02s.

uv build --out-dir docs/runs/2026-08-05-issue-129-source-of-truth/artifacts
→ source distribution and wheel built successfully; package version 0.1.0;
  wheel 306240 bytes; sdist 276589 bytes; real 0.79s, user 0.54s, sys 0.20s.

git diff --check
→ exit 0.
```

An earlier parallel build regenerated timestamp-bearing archive metadata after
the first checksum snapshot; that inventory mismatch was diagnosed and replaced
with the final artifact hashes. The serial final checksum verification below
passed all three entries.

The targeted validator is standard-library-only and performs no external
side-effect operation. The full test suite includes the existing discovery,
qualification, runner, and claim-matrix regression tests; no tests were skipped
or deselected for the recorded full run.

Tool identity: `uv 0.11.7`, CPython `3.11.15`, pytest `9.1.1`, pluggy `1.6.0`,
and package `aiverify 0.1.0`.

## Artifact inventory and checksums

- `validate_docs.py`: deterministic documentation/link/claim-boundary checker.
- `artifacts/aiverify-0.1.0-py3-none-any.whl`: built package artifact.
- `artifacts/aiverify-0.1.0.tar.gz`: built source distribution.
- `checksums.sha256`: SHA-256 inventory for the checker and package artifacts.
- No APK, emulator, screenshot, layout dump, logcat, agent transcript, device
  receipt, live backend receipt, or formal qualification artifact was generated.

The committed checksum inventory verifies with:

```bash
(cd docs/runs/2026-08-05-issue-129-source-of-truth && shasum -a 256 -c checksums.sha256)
```

Expected result: all three entries `OK`.

## Manual steps, gaps, and claim boundary

Manual/device steps: none. No emulator, APK, production data, external project,
upstream state, credentials, network policy, or formal M9 holdout was touched.

Known gaps: this issue intentionally does not implement Context Acquisition,
Hypothesis Portfolio generation, Attack Plan synthesis, production-seam
admission, Project Risk Map execution, Falsification Review code, qualification
freeze, or formal lanes. M9 remains planned/unmeasured. The M8 population remains
immutable: `22af9b2` is not a rerun authorization, and no M8 lane is placed in the
M9 denominator.

Local-only claim boundary: this record supports only the consistency and link
validation of the committed repository documents and the package/build checks
listed above. It does not support an M9 implementation, runtime, Android,
project-completeness, benchmark-rate, OEM/ColorOS, production, upstream, or
provider-independence claim.

# M8 #121 qualification-freeze evidence

This run record freezes the exact M8 state-evolution qualification contract
before formal execution. It proves the dual-mode discovery/admission seam and
the 12-lane population; it intentionally performs no Gradle build, APK install,
device launch, or runtime interpretation. Issue #122 is the only consumer that
may start formal lanes, and it must consume the exact merged manifest commit.

## Frozen contract

- Manifest: `bench/m8/m8-state-evolution-qualification-v1.json`
- Population: four ordered cells (`change-defect`, `change-control`,
  `project-defect`, `project-control`) × three repetitions = 12 lanes.
- Change packets retain a `BehaviorDelta`, `ContractDrift`, and the exact patch
  checksum. Project packets are no-diff `ProjectTarget` packets with neither a
  delta nor synthetic drift.
- Every lane traverses Context Expansion → state-evolution hypothesis freeze →
  Attack Plan admission → neutral Run Spec compilation. The auditor mapping is
  not loaded or released by this preflight.
- One attempt is frozen, no retry or replacement is allowed, and every
  identity/fixture/evidence/adjudication/claim contradiction aborts before
  formal side effects.
- The claim boundary is local-only: the state-evolution fixture and discovery /
  admission seam. No runtime, rate, whole-project, device-fleet, production,
  or upstream claim is made here.

## Durable artifacts

- `manifest-identity.json`: raw and canonical manifest checksums plus the exact
  preflight commit and tool identity.
- `preflight.json`: 12 lane receipts, campaign/plan/run-spec identities, mode
  bindings, and no-side-effect gate.
- `leakage-audit.json`: verifier packet and pre-execution artifact leakage
  checks; all 12 packets pass and mapping remains withheld.
- `contradiction-audit.json`: representative source, target/context,
  prior/operator, fixture/state, Run Spec, retry, evidence, adjudication, and
  claim contradictions; all are rejected with `side_effects=false`.
- `artifacts/`: package-build receipt and the built wheel/sdist when present.
- `checksums.sha256`: SHA-256 inventory for every committed JSON, script, and
  package artifact.

## Verification commands

Commands below were run from the dedicated clean #121 worktree. The exact
revision, durations, pass counts, tool versions, and package checksums are
recorded here and cross-checked by `manifest-identity.json`,
`package-build.json`, and `checksums.sha256`.

```text
uv build --out-dir docs/runs/2026-08-05-issue-121-qualification-freeze/artifacts
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest tests/bench/test_m8_qualification.py -q
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -ra
uvx ruff check src/aiverify/bench/m8_qualification.py src/aiverify/bench/state_evolution.py tests/bench/test_m8_qualification.py docs/runs/2026-08-05-issue-121-qualification-freeze/generate_evidence.py
uvx ruff format --check src/aiverify/bench/m8_qualification.py tests/bench/test_m8_qualification.py docs/runs/2026-08-05-issue-121-qualification-freeze/generate_evidence.py
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python -m compileall -q src
uv build --out-dir docs/runs/2026-08-05-issue-121-qualification-freeze/artifacts
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python docs/runs/2026-08-05-issue-121-qualification-freeze/generate_evidence.py
(cd docs/runs/2026-08-05-issue-121-qualification-freeze && shasum -a 256 -c checksums.sha256)
git diff --check
```

Results: targeted M8 tests `13 passed` in 1.46s; full suite `816 passed` in
26.86s; Ruff 0.16.1 check passed for the changed M8/state-evolution paths and
format check passed for the new M8/evidence files; `compileall` passed;
`uv build` 0.11.7 completed in 0.82s; the wheel is 290,973 bytes
(`cfd11dbc7cbce1e0eb149e678a173877400f13cb93ef52d2644619ed5f71b10c`) and the
sdist is 260,629 bytes
(`4d4c9af4ee36fe0a823ede69c28724267e3f7c5ef16aba39a220fdf5e81cc869`);
preflight admitted 12/12 lanes with 37 checks, leakage and contradiction
audits passed, and `side_effects=false`; checksum verification passed for all
9 inventory entries. Python is 3.11.15 (CPython, macOS arm64). The final
implementation revision is recorded as `preflight_commit` in
`manifest-identity.json` after the implementation commit.

No Android CLI, Gradle, adb, emulator, APK, real-device, manual UI, process
death, backup/restore, production data, external project, or network policy
operation was performed in this #121 slice. Those are #122 formal-execution
responsibilities.

## Known gaps

- No formal outcome is available yet. `supported`, `rejected`, `inconclusive`,
  and `non_accountable` remain #122 runtime results, not #121 claims.
- The source/build/auditor identities are frozen and checksum-bound; the
  auditor-only matched-pair mapping remains unavailable until after hypothesis
  and plan admission.
- This does not claim benchmark-wide detection, false-positive rate, general
  Android persistence correctness, device/OEM coverage, or upstream acceptance.
- The touched legacy `state_evolution.py` and `campaign.py` modules retain
  pre-existing Ruff format/lint findings outside this slice; the new M8 paths
  are clean under the scoped commands above.

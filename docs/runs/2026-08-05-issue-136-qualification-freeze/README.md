# M9 #136 — Frozen blinded ProjectTarget qualification

Status: frozen and ready for the exact-commit consumer #137. No formal lane,
device action, agent invocation, or runtime holdout was executed in #136.

The human approval is recorded at
`https://github.com/yangliang2/ai_verification/issues/136#issuecomment-5207290095`.
The authoritative contract is
`bench/m9/m9-project-qualification-v1.json`; the older `candidate-*` files in
this directory are retained as superseded pre-approval history.

## Frozen contract

- Implementation commit: `d3e03dc036a1fb8d0f7f314e7999b58294399242` (merged
  #135).
- ProjectTarget: `android/architecture-samples` at
  `ee66e1526b84c026615df032c705842b7d2a521f`, tree
  `19455e693ec8c96c37a56aec55059a220826c5a3`, source-index SHA-256
  `66fa95486f2c63e84dbb1ba1dd77a43ad34cdd6ecbd8c659e496e9a204e38585`.
- Matched pair: human-approved Option A defect commit
  `208575f78d59716669d0733b5ed3e08797b08787` versus the unchanged baseline
  control. The defect omits the local upsert in
  `DefaultTaskRepository.updateTask`.
- Application identity: package
  `com.example.android.architecture.blueprints.main`; launcher
  `com.example.android.architecture.blueprints.todoapp.TodoActivity`; min/target
  SDK 21/35.
- Cohort: three defect lanes and three matched control lanes, opaque lane order
  `m9-lane-01` through `m9-lane-06`. The committed auditor mapping is bound by
  SHA-256 `81aa8a18a3174bae566c006bb064803d8794a4add9f345f33e39022c2bf30a62`
  over canonical mapping bytes (raw artifact SHA-256
  `2004d2c343dc63f19cb143b9332d24ae1f411b8433c44300294ec6e831ff987b`). It is
  not included in verifier-facing packets. It may be released only after
  Context Acquisition, the top-three portfolio, Attack Plan admission, and
  the leakage audit, then must be verified before lane release.
- Runner: `codex_cli`, policy `m9-production-seam-v1`, device
  `emulator-5554` / AVD `aiverify_api35` / API 35, network disabled, portrait,
  requested driver and L3 model `codex-default`.
- Portfolio: exactly three approved M9 prior/operator/strategy definitions,
  budget 8, maximum top-three selection.
- Oracle: edited task title must remain visible after navigation, reopening, and
  the admitted process boundary. The oracle consumes only terminal execution
  and raw evidence identities; it does not receive the hidden lane role.
- Falsification Review: six reviews, one per lane, clean context, independent
  invocation identity, no production adjudication/oracle path, same-provider
  limitation disclosed.
- Accounting: one accountable attempt per lane, zero retry, zero replacement.
  Adverse, challenged, inconclusive, rejected, and non-accountable outcomes are
  terminal evidence.
- Each serialized RunSpec carries only a role-neutral sealed source-binding
  reference. Source-context inputs contain the approved baseline snapshot only;
  role-bearing source identities remain auditor evidence and are not sent to
  acquisition, planning, execution-agent, or Falsification Review inputs.

## Side-effect-free preflight

`generate_evidence.py` created six serialized RunSpecs and admitted each exact
RunSpec/runner pair through `admit_production_seam`. The admission command
runner allowed only read-only `git` identity queries. The preflight rejected no
approved lane, did not build/install/launch, and did not invoke Android CLI,
adb, Codex, a device, an oracle, or a formal runtime.

Results:

- RunSpecs: 6/6 present and checksum-bound.
- Production-seam admission: 6/6 admitted; 0 rejected.
- Pre-release neutral leakage audit: 6/6 packets passed before source-binding
  materialization; mapping release remained false.
- Final neutral leakage audit: 6/6 packets passed; mapping release remained
  false.
- Contradiction packet: rejected before any build/device/agent/runtime side
  effect; excluded from the formal denominator.
- Formal execution: false; side effects: false.

## Verification commands and results

Commands ran from the dedicated clean worktree
`/Users/peter/projects/ai_verification-m9-136` on 2026-08-06.

```text
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python -m py_compile \
  src/aiverify/bench/m9_qualification.py \
  docs/runs/2026-08-05-issue-136-qualification-freeze/generate_evidence.py
→ exit 0.

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -q \
  tests/bench/test_m9_qualification.py tests/runner/test_admission.py
→ 12 passed, 0 failed; real 1.17s, user 0.57s, sys 0.50s.

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -q
→ 870 passed, 0 failed; real 33.06s, user 23.65s, sys 5.79s.

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  docs/runs/2026-08-05-issue-136-qualification-freeze/generate_evidence.py
→ status=passed; 6 admissions; leakage=pass; contradiction=pass;
  formal_execution_started=false; preflight duration 1.57s.

uv build --quiet --out-dir \
  docs/runs/2026-08-05-issue-136-qualification-freeze/artifacts
→ package `aiverify 0.1.0`; wheel and sdist built successfully; real 0.73s.

(cd docs/runs/2026-08-05-issue-136-qualification-freeze && \
  shasum -a 256 -c checksums.sha256)
→ all committed inventory entries passed.

git diff --check -- src/aiverify/bench/m9_qualification.py \
  src/aiverify/runner/admission.py tests/bench/test_m9_qualification.py \
  docs/runs/2026-08-05-issue-136-qualification-freeze/generate_evidence.py
→ exit 0.
```

The approved pair was rebuilt host-side without formal execution:

```text
(cd /private/tmp/m9-136-option-a && \
  ./gradlew --no-daemon --no-configuration-cache --max-workers=1 :app:assembleDebug)
→ BUILD SUCCESSFUL in 5s; 43 actionable tasks up-to-date; APK SHA-256
  `61063a0fd247eb03d1bd251b0d9359c3c2a5ea07cb8abe4b38d3daae57c153ac`.

(cd /private/tmp/m9-136-candidate-a-control && \
  ./gradlew --no-daemon --no-configuration-cache --max-workers=1 :app:assembleDebug)
→ BUILD SUCCESSFUL in 5s; 43 actionable tasks up-to-date; APK SHA-256
  `d38b30f17010da114b5585dadec8326eb76b04dfbae4a175f7cb2840a0093c66`.
```

Tool identity: CPython 3.11.15, OpenJDK 17.0.19, Gradle wrapper 8.11.1,
Android CLI 1.0.15498356, adb 1.0.41 / platform 37.0.0-14910828,
Codex CLI 0.144.6, backend `codex_cli`, requested/effective contract model
`codex-default`. The tool receipt is `tool-versions.json`.

## Artifact inventory and key checksums

- `bench/m9/m9-project-qualification-v1.json`: frozen manifest; final raw
  SHA-256 is recorded in `manifest-identity.json` and `checksums.sha256`.
- `bench/m9/run-specs/m9-lane-01.yaml` through `m9-lane-06.yaml`: six exact
  serialized RunSpecs.
- `admission/m9-lane-01.json` through `m9-lane-06.json`: six admitted,
  side-effect-free production-seam receipts.
- `preflight.json`, `admission-audit.json`, `neutral-verifier-packets.json`,
  `pre-release-neutral-verifier-packets.json`, `leakage-audit.json`,
  `pre-release-leakage-audit.json`, `contradiction-packet.json`, and
  `contradiction-audit.json`: ordered gate evidence.
- `operator-registry.json`, `attack-plan-admission.json`, and
  `source-context-inputs.json`: frozen discovery/planning inputs and receipts;
  source context is baseline-only and role-neutral.
- `build-logs/*.log`: committed copies of candidate, selected-pair, final-pair,
  and offline diagnostic build output; their SHA-256 values are in
  `checksums.sha256`.
- `artifacts/aiverify-0.1.0-py3-none-any.whl`: 375,652 bytes; SHA-256
  `eb348907e558b351937dccb5089705bf04ea0944454d9c3ccc3e2d287032849b`.
- `artifacts/aiverify-0.1.0.tar.gz`: 341,172 bytes; SHA-256
  `743367a46e8624afe8af1424e7b8dc7fb3637895ef09b787f53a1588d340b3ee`.
- Defect APK: 24,681,461 bytes; SHA-256
  `61063a0fd247eb03d1bd251b0d9359c3c2a5ea07cb8abe4b38d3daae57c153ac`.
- Control APK: 24,681,606 bytes; SHA-256
  `d38b30f17010da114b5585dadec8326eb76b04dfbae4a175f7cb2840a0093c66`.
- `checksums.sha256`: committed inventory for the run record, manifest,
  RunSpecs, source validator, tests, and package artifacts.

No screenshot, layout dump, logcat, installed APK, emulator session, manual UI
step, Codex invocation, live provider receipt, oracle result, Finding,
ResidualRisk, Project Risk Map, or Falsification Review result exists yet.
Those are #137 responsibilities.

## Manual steps, known gaps, and claim boundary

Manual/device steps in #136: none. The device profile is frozen but not accessed.
The candidate offline Gradle diagnostic failed closed because the local cache
lacked candidate dependencies; the online/normal host builds above passed and
their logs are committed under `build-logs/`. No formal lane was retried or
replaced.

Known gap: the formal six-lane result is intentionally unavailable. #137 must
consume the exact merged #136 commit, perform the ordered Context Acquisition →
top-three Portfolio → Attack Plan admission → leakage audit → mapping release,
then execute each lane once and independently reconcile all six reviews. Any
non-Supported result remains valid evidence.

Local-only claim boundary: this record supports only the human-approved public
snapshot, local matched pair, frozen contracts, host build/package checksums,
side-effect-free admissions, leakage audit, and contradiction rejection. It
does not claim production or upstream behavior, OEM/ColorOS coverage, device
fleet behavior, success/recall/completeness rates, benchmark-scale capability,
M8 results, or automated repair.

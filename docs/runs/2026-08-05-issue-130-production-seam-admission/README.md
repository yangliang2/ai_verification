# M9-1 production-seam admission

Issue: [#130](https://github.com/yangliang2/ai_verification/issues/130)<br>
Base: `origin/main` / `aa486e1ca32baa83c9766aa8937bf31b9c962655`<br>
Branch: `m9-130-production-seam-admission`<br>
Implementation commit: `0a0224999544824b5c3c5024453af5b89188f984`<br>

## Scope and result

This run implements the M9 production-seam admission boundary. Admission binds
the exact serialized Run Spec bytes and exact planned runner options, resolves
the repository with read-only git identity queries, validates origin/commit/
worktree/subdirectory policy and path containment, checks APK/package/activity
declarations, runner backend/model/tool prerequisites, and reserves a clean
artifact namespace. It emits a deterministic checksum-bound receipt and marks
the boundary as having no build, device, agent, or external side effect.

The formal runner can require and re-verify that receipt before establishing a
formal ExecutionRecord. Run Spec, source/worktree, target, artifact namespace,
or runner-option drift is rejected before the record or any device/build/agent
operation. A separate helper proves that a temporary admission envelope can be
terminally abandoned as non-accountable without entering a formal attempt
namespace.

The historical M8 host-project-subdirectory/runner-root mismatch is a rejected
regression case. The corrected explicit subdirectory policy and repository-root
host both admit. Tests use a git-only instrumented command double; any android,
adb, codex, build, or device command would fail the test.

Changed modules and tests:

- `src/aiverify/runner/admission.py` — admission policy, deterministic receipt,
  drift verification, temporary-record helper.
- `src/aiverify/runner/cli.py` — strict admission for source-backed formal CLI
  invocations and `--allow-host-project-subdir` policy.
- `src/aiverify/runner/__init__.py` — public admission exports.
- `tests/runner/test_admission.py` — root/subdirectory admission, historical
  rejection, deterministic receipt, drift, no-side-effect, and abandoned-record
  coverage.

No APK was built for a target project, no device was queried or modified, no
Verification Agent Backend was invoked, and no formal M9 holdout or hidden
mapping was consumed.

## Verification commands and results

All commands ran from `/Users/peter/projects/ai_verification-m9-130` on macOS
Darwin arm64. The worktree was clean before package/evidence generation.

```text
uv venv .venv
→ exit 0; CPython 3.11.15.

uv pip install --python .venv/bin/python pytest pyyaml jsonschema
→ exit 0; installed pytest 9.1.1, PyYAML 6.0.3, jsonschema 4.26.0.

/usr/bin/time -p .venv/bin/python -m pytest -q tests/runner/test_admission.py tests/runner/test_cli.py
→ 49 passed, 0 failed; exit 0; real 1.10s, user 0.52s, sys 0.48s.

/usr/bin/time -p .venv/bin/python -m pytest -ra
→ 827 passed, 0 failed in 28.45s; exit 0; real 28.54s, user 20.92s, sys 4.71s.

/usr/bin/time -p .venv/bin/python -m compileall -q src tests
→ exit 0; real 0.08s, user 0.06s, sys 0.01s.

git diff --check
→ exit 0.

uv build --out-dir docs/runs/2026-08-05-issue-130-production-seam-admission/artifacts
→ exit 0 in 3.09s; package `aiverify 0.1.0`; wheel 311872 bytes; sdist 281280 bytes.

.venv/bin/python docs/runs/2026-08-05-issue-130-production-seam-admission/validate_receipt.py
→ exit 0; status=passed; required wheel/sdist entries present; deterministic receipt
regeneration and no-external-side-effects checks recorded in validation-output.json.

(cd docs/runs/2026-08-05-issue-130-production-seam-admission && shasum -a 256 -c checksums.sha256)
→ 10/10 entries OK; exit 0.
```

The package build and checksum manifest are committed with this record. The
final evidence-content commit and merged PR commit are added to this record in
the completion handoff because a commit cannot contain its own SHA.

Tool identity: system Python 3.14.4; worktree CPython 3.11.15; uv 0.11.7;
pytest 9.1.1; pluggy 1.6.0; PyYAML 6.0.3; jsonschema 4.26.0; macOS 26.3 /
Darwin arm64; package `aiverify 0.1.0`. Requested/effective backend and model,
device, emulator, Android CLI, adb, and Codex runtime were not invoked by this
validation run.

## Artifact inventory and checksums

- `README.md`: this durable run record.
- `src/aiverify/runner/admission.py`: admission implementation.
- `tests/runner/test_admission.py`: targeted contract tests.
- `artifacts/aiverify-0.1.0-py3-none-any.whl`: built package artifact.
- `artifacts/aiverify-0.1.0.tar.gz`: built source distribution.
- `checksums.sha256`: SHA-256 inventory for this record, validator/test receipt,
  source modules, and package artifacts.
- `validation-output.json`: deterministic artifact/schema receipt.
- No APK, screenshot, layout dump, logcat, device receipt, backend transcript,
  formal RunSpec, cohort mapping, or production project artifact was generated.

Package sizes and hashes: wheel 311872 bytes,
`c0cb2734efa34f5c1c3c0fd8462efba9cd2205acde1eed6b376f9f4bf9890918`; sdist
281280 bytes,
`7b28e7e5d6dd15297ef59de2937f97d628401ecc21a3cd51c6081ca7202ee0d8`. All
other artifact hashes are recorded in the committed `checksums.sha256` file.
The validation output records the targeted contract result and deterministic
receipt regeneration.

## Manual steps, gaps, and claim boundary

Manual/device steps: none. No production data, external project, upstream
state, credentials, network policy, device, emulator, APK, backend, or formal
M9 holdout was touched.

Known gaps: this issue does not implement Context Acquisition, Hypothesis
Portfolio generation, Attack Plan synthesis, Falsification Review, Project
Risk Map execution, qualification freeze, or formal lane execution. Admission
does not prove that a target builds, installs, launches, or behaves correctly;
those remain later bounded contracts.

Local-only claim boundary: this record supports only the side-effect-free
admission and receipt/drift behavior exercised by the committed tests, on the
recorded host and toolchain. It does not support runtime behavior, project
completeness, detection/false-positive rates, benchmark-wide capability,
Android/OEM/ColorOS, production, upstream, or provider-independence claims.

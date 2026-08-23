# Issue #190 — four-cell auditor-mapping verification

Issue: [DIL-M0.6: Seal the four-cell auditor mapping and structural walkthrough](https://github.com/yangliang2/ai_verification/issues/190)

Implementation under test: `870743d feat(injection): seal four-cell auditor mapping`,
with review remediation in `211ea30 fix(injection): bind mapping packet receipts`.

## Scope and claim boundary

This record verifies the structural M0.6 Injection Lab boundary only. A sealed,
compatible `AuditorPair` produces four verifier-facing packet shapes—two
`ChangeTarget` and two `ProjectTarget`—plus a separately serializable private
`AuditorMapping`. The public `VerifierPacketFamily` has no mapping field and
rejects an attached mapping; the audit-side aggregate deliberately has no mixed
public/private serializer.

This is not a Verification Agent invocation, Discovery Campaign, Run Spec,
Android build, APK install, emulator/device run, network/provider/model
operation, formal Qualification Cohort, benchmark result, or detection claim.
The local test walkthrough uses only temporary Git repositories and owned
worktrees.

## Implementation and acceptance evidence

| Acceptance criterion | Evidence |
| --- | --- |
| Four uniquely identified canonical packet shapes and one private mapping | `compile_four_cell_case_family` compiles both target modes for defect/control. `VerifierPacketFamily` requires exactly two packets of each target kind; `AuditorMapping` requires all four target/variant cells and canonical ordering. |
| Mapping binds public IDs to private audit identities without becoming verifier input | `AuditorMappingEntry` records each packet ID, target kind, hidden variant, and `InjectedCasePackage.identity_sha256`. `AuditorCaseFamily` checks packet-ID membership, target kind, audit-package identity, and the corresponding sealed receipt identity. Public parsers reject mapping bytes or an attached mapping field. |
| Incomplete, inconsistent, or disclosure-unsafe input fails closed | Contract tests cover incomplete public/private cell sets, forged audit-package identities, a defect/control packet-ID swap, incompatible baseline provenance, and disclosure-policy rejection. All errors are fixed boundary errors; no partial family is returned. |
| Deterministic structural walkthrough | `test_four_cell_structural_walkthrough_seals_private_mapping_separately` compiles the family twice, checks byte-for-byte canonical stability, both target modes, all four private cells, parser separation, and declared-token absence from public bytes. |
| Explicit non-formal claim boundary | Both public-family and private-mapping contracts carry M0 structural-only claim boundaries; this record states the same boundary. |

Relevant implementation files:

- `src/aiverify/injection/packets.py`
- `src/aiverify/injection/__init__.py`
- `tests/injection/test_change_target_packet.py`

## Automated verification

| Command | Result |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' tests/injection/test_change_target_packet.py --junitxml=docs/runs/2026-08-23-issue-190-four-cell-auditor-mapping/verification/four-cell-pytest.xml` | 30 passed; JUnit: 30 tests, 0 failures, 0 errors, 0 skipped, 113.39s. |
| `uv run --with ruff ruff check src/aiverify/injection/packets.py src/aiverify/injection/__init__.py tests/injection/test_change_target_packet.py` | Passed (Ruff 0.16.4). |
| `uv run --with mypy mypy --follow-imports=skip src/aiverify/injection/packets.py src/aiverify/injection/__init__.py` | `Success: no issues found in 2 source files` (mypy 2.3.1). |
| `.venv/bin/python -m compileall -q src tests` | Passed. |
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' -q tests/injection --junitxml=docs/runs/2026-08-23-issue-190-four-cell-auditor-mapping/verification/injection-pytest.xml` | 86 passed; JUnit: 86 tests, 0 failures, 0 errors, 0 skipped, 183.75s. |
| `PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -p .venv/bin/python -m pytest -p no:cacheprovider -o addopts='' -q --junitxml=docs/runs/2026-08-23-issue-190-four-cell-auditor-mapping/verification/full-pytest.xml` | 1,232 passed, 1 skipped; JUnit: 1,233 tests, 0 failures, 0 errors, 1 skipped, 328.22s. No build was applicable or run. |
| `git diff --check` | Passed with no whitespace errors. |
| `shasum -a 256 -c SHA256SUMS` from this directory | All three JUnit reports verified `OK`. |

Environment: `aiverify 0.1.0`, CPython 3.11.15, pytest 9.1.1, Ruff 0.16.4,
mypy 2.3.1, Git 2.50.1 (Apple Git-155), macOS host.

## Review results

The required two-axis review compared `origin/main...HEAD`.

- Standards: no code-standard or ADR violation. The initial review noted the
  required durable evidence record and ambiguous local parser names; this record
  fulfills the delivery requirement and the locals were renamed.
- Spec: the first review found that a forged mapping could swap defect/control
  packet IDs while retaining valid package hashes. The remediation binds each
  mapped public packet's receipt identity to the selected audit package and adds
  a regression test. The final re-review reported no remaining spec findings.

## Evidence artifacts

| Artifact | Purpose | SHA-256 |
| --- | --- | --- |
| `verification/four-cell-pytest.xml` | Focused four-cell packet contract JUnit report | `439621795a2a43ba014f81849d814b8e8e40bb6c29d2734211a335acfbd4ff79` |
| `verification/injection-pytest.xml` | Injection Lab JUnit report | `99532ba2f2f725ec2f673d4c30e41a1e033c75f0e2a07ff0ad7614af64645384` |
| `verification/full-pytest.xml` | Repository-wide JUnit report | `c31912bda34d9e1742bdf2458e8be38692e4238ba79338b36d02d89da746dffe` |
| `SHA256SUMS` | Checksum manifest for the three reports | See manifest. |

No screenshots, layout dumps, device logs, Android artifacts, or generated
application JSON were produced.

## Known gaps and follow-up risks

- The declared-token Disclosure Policy is a structural boundary, not a general
  semantic leak detector.
- The four-cell family is fixture-local and non-formal. It does not validate a
  defect, control equivalence, verifier behavior, discovery completeness, or a
  benchmark rate.
- No Android or network/provider/model execution was applicable or performed;
  a future formal/runtime population requires separate human approval and
  contracts.

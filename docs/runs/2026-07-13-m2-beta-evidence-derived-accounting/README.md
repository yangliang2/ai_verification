# M2-beta Evidence-Derived Accounting Run

Issue: #39
Date: 2026-07-13
Base commit before this change: `3b1cd87`

## Scope

This run validates the M2-beta aggregation contract change from
manifest-declared outcomes to evidence-derived accounting.

No Android emulator, real device, APK build, or package install was part of this
run. The work is repository-level aggregation over committed `verdict.json`,
run-spec, manifest, and repeatability `summary.json` artifacts.

Package/app identifier: not applicable for this aggregation-only validation.
Build duration: not applicable; no Android or Python package build was run.

## Implemented Surface

- `src/aiverify/bench/m2_beta_summary.py`
  - Rejects manifest `defect_outcome` and `control_outcome` fields.
  - Resolves included seed caught/missed and passed-control/false-positive
    counts from committed control and defect verdict lanes.
  - Validates seed identity, metric context, expected oracle metadata, evidence
    existence, non-accountable lanes, and expected defect-class signal.
  - Resolves fixed-evidence L3 repeatability totals from committed
    `summary.json` files.
- `bench/goldset/m2-beta-slice.yaml`
  - Replaces manual outcome fields with explicit evidence pointers.
  - Marks three historical M1 control lanes as `legacy_control_document`.
- `docs/M2-beta-aggregate-summary.md`
  - Regenerated from the renderer.
- `docs/M2-beta-inclusion-rules.md`
  - Documents evidence-derived accounting and legacy control classification.
- `docs/M2-beta-benchmark-slice-report.md`
  - Documents evidence contract counts.
- `tests/bench/test_m2_beta_summary.py`
  - Covers valid evidence, seed-level and evidence-level manual outcome
    rejection, missing artifacts, non-accountable lanes, metric context
    mismatch, expected class contradiction, repeatability separation, and
    generated doc matching.
- `tests/bench/test_m2_beta_inclusion_rules.py`
  - Covers evidence-derived inclusion guidance.
- `tests/bench/test_m2_beta_benchmark_slice_report.py`
  - Covers evidence-derived report language.

## Commands And Results

Tool versions:

```bash
.venv/bin/python --version
# Python 3.12.13

.venv/bin/pytest --version
# pytest 9.1.1
```

Targeted validation:

```bash
.venv/bin/pytest tests/bench/test_m2_beta_summary.py tests/bench/test_m2_beta_inclusion_rules.py tests/bench/test_m2_beta_benchmark_slice_report.py -q
# ......................                                                   [100%]
# exit 0

.venv/bin/pytest --collect-only -q tests/bench/test_m2_beta_summary.py tests/bench/test_m2_beta_inclusion_rules.py tests/bench/test_m2_beta_benchmark_slice_report.py | awk -F': ' '/: [0-9]+$/ {files += 1; total += $2} END {print "collected_files", files; print "collected_tests", total}'
# collected_files 3
# collected_tests 22
```

Aggregate renderer verification:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m2_beta_summary >/tmp/m2-beta-summary.md && cmp -s /tmp/m2-beta-summary.md docs/M2-beta-aggregate-summary.md; echo summary_cmp=$?
# summary_cmp=0

PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
from aiverify.bench.m2_beta_summary import build_summary
s=build_summary(Path('.'))
print('included', s.state_counts.get('included', 0))
print('blocked', s.state_counts.get('blocked', 0))
print('candidate', s.candidate_count)
print('defect_outcomes', s.defect_outcomes)
print('control_outcomes', s.control_outcomes)
print('evidence_contracts', s.evidence_contracts)
print('repeatability_totals', s.repeatability_totals)
PY
# included 10
# blocked 0
# candidate 0
# defect_outcomes {'caught': 10}
# control_outcomes {'passed_control': 10}
# evidence_contracts {'legacy_control_document': 3, 'verdict': 7}
# repeatability_totals {'packages': 2, 'total_calls': 20, 'baseline_passes': 10, 'defect_fails': 10, 'errors': 0}
```

Full repository validation:

```bash
.venv/bin/pytest -q
# ........................................................................ [ 21%]
# ........................................................................ [ 43%]
# ........................................................................ [ 65%]
# ........................................................................ [ 87%]
# ...........................................                              [100%]
# 2 warnings:
# - tests/agent/test_oracle_l2.py::test_l2_fail_when_node_gone
# - tests/bench/test_goldset_process_death_02_state_loss.py::test_defect_build_l2_fails_with_state_loss
# Both warnings are the existing Element truth-value DeprecationWarning from
# src/aiverify/agent/oracle/l2.py:123.
# exit 0

.venv/bin/pytest --collect-only -q | awk -F': ' '/: [0-9]+$/ {files += 1; total += $2} END {print "collected_files", files; print "collected_tests", total}'
# collected_files 40
# collected_tests 331

git diff --check
# exit 0
```

## Artifact Inventory

- `bench/goldset/m2-beta-slice.yaml`
- `src/aiverify/bench/m2_beta_summary.py`
- `docs/M2-beta-aggregate-summary.md`
- `docs/M2-beta-inclusion-rules.md`
- `docs/M2-beta-benchmark-slice-report.md`
- `tests/bench/test_m2_beta_summary.py`
- `tests/bench/test_m2_beta_inclusion_rules.py`
- `tests/bench/test_m2_beta_benchmark_slice_report.py`
- `docs/runs/2026-07-13-m2-beta-evidence-derived-accounting/README.md`

No screenshots, layout dumps, APKs, device logs, or Android reports were
generated by this validation run.

## Checksums

```text
8f806f9758af6930c99a6d48c13f425defd1a923dd6a1d5ffc871b37ad8b2a7c  docs/M2-beta-aggregate-summary.md
5dcaaa095d39ad0333adcc4dafbda73b86bdf7010212e18cf7196ebb07f3cc27  bench/goldset/m2-beta-slice.yaml
```

## Known Gaps

- No Android CLI, emulator, or real-device validation was run for this issue;
  #39 is an accounting-contract change over already committed evidence.
- Three included M1 controls remain legacy historical controls documented via
  `docs/M1-goldset-report.md`; they are explicitly counted under
  `legacy_control_document` rather than silently upgraded to modern standalone
  control verdict evidence.
- Historical verdicts that predate the runner execution and metric-context
  contract are accepted only with legacy notes; new missing, mismatched,
  contradictory, or non-accountable evidence fails closed.

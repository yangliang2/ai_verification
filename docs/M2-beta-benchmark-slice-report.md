# M2-beta Benchmark Slice Report

M2-beta packages the current Wikipedia Goldset-derived evidence into a small
audited aggregate benchmark slice. It is a bounded milestone report, not a
benchmark-wide detection-rate claim.

## Source Issues

| Issue | Status in this report | Output |
|---|---|---|
| #24 | Parent PRD | M2-beta audited aggregate benchmark slice |
| #25 | Completed | Inclusion rules |
| #26 | Completed | Metric-context backfill |
| #27 | Completed | Oversized saved-state quarantine |
| #28 | Completed | Aggregate summary path |
| #29 | Completed by this report | Final benchmark-slice report |

## Durable Artifacts

| Artifact | Purpose |
|---|---|
| `docs/M2-beta-inclusion-rules.md` | Defines `included`, `control`, `repeatability-only`, `candidate`, `blocked`, and `excluded` accounting states. |
| `docs/M2-metric-schema.md` | Documents seed outcome, oracle outcome, oracle defect class, taxonomy category, and taxonomy pattern separation. |
| `bench/goldset/m2-beta-slice.yaml` | M2-beta seed inventory manifest. |
| `src/aiverify/bench/m2_beta_summary.py` | Repeatable aggregate summary renderer. |
| `docs/M2-beta-aggregate-summary.md` | Generated aggregate summary. |
| `docs/M2-beta-oversized-saved-state-quarantine.md` | Formal M2-beta quarantine note for #23. |
| `docs/M1-goldset-report.md` | M1 five-seed source report. |
| `docs/M2-l3-text-layout-summary.md` | Fixed-evidence L3 repeatability source summary. |

## Aggregate Result

M2-beta currently has:

- included injected-defect seeds: 9;
- blocked seeds: 1;
- candidate seeds: 1;
- repeatability-only packages: 2;
- included defect outcomes: `caught: 9`;
- baseline-control outcomes: `passed_control: 9`.

Expected oracle distribution among included seeds:

- `L1`: 3;
- `L2`: 4;
- `L3`: 2.

Taxonomy/root-cause distribution among included seeds:

- `config-change`: 2;
- `coroutine-concurrency`: 1;
- `lifecycle`: 1;
- `navigation`: 2;
- `process-death`: 1;
- `ui-rendering`: 2.

Oracle defect-class distribution among included seeds:

- `crash_stability`: 3;
- `state_loss`: 4;
- `ui_rendering`: 2.

Fixed-evidence L3 repeatability remains separate from caught/missed accounting:

- packages: 2;
- total L3 calls: 20;
- baseline passes: 10;
- defect fails: 10;
- errors: 0.

## Oversized Saved-State Status

#23, `wikipedia-process-death-03-oversized-saved-state`, remains implemented but
is not included in M2-beta counts.

Current M2-beta status:

- accounting state: `candidate` and `blocked`;
- denominator impact: 0;
- caught/missed outcome: none;
- control outcome: none.

Reason: the 2026-07-09 live retry did not reach a valid baseline UI state, no
valid baseline verdict was produced, and no defect lane was run. The quarantine
note defines the criteria for future inclusion if a stable emulator or real
device produces a valid baseline/defect matched pair.

## Supported Claims

The project can now claim:

- the MVP verification chain is live and audited;
- M1 caught five of five seeded defects;
- M2-alpha added post-M1 seed expansion and two repeatability-gated text-layout
  L3 seeds;
- M2-beta has a reproducible aggregate summary over committed repo artifacts;
- M2-beta explicitly separates included, blocked, candidate, and
  repeatability-only evidence;
- #23 is quarantined from M2-beta counts without closing future execution work.

## Out Of Scope

This report does not claim:

- benchmark-wide detection rate;
- benchmark-wide false-positive rate;
- 100+ AI-generated defect coverage;
- fully unattended Journey reliability;
- visual-only or multimodal L3 reliability;
- cross-host or non-Wikipedia generality;
- ColorOS migration readiness.

## Next Step

The next milestone decision should not add more accounting machinery first. The
project should choose one of two directions:

1. define an M2-beta extension with more included seeds and explicit sample-size
   goals; or
2. plan M3 around execution reliability, false-positive controls, and larger
   benchmark reporting.

#23 remains the only known open seed-execution candidate and should be retried
only when a stable emulator or real device is available.

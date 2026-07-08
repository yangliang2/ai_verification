# M2 L3 Text-Layout Summary

This report summarizes the current repeatability-gated L3 evidence for text-layout
semantic UI defects. It is a bounded M2 evidence summary, not a benchmark-wide
detection-rate or false-positive-rate claim.

## Scope

The current L3 evidence covers two Wikipedia text-layout semantic seeds:

| Seed | Source issues | Matched-pair run record | Repeatability run record | Defect shape |
|---|---|---|---|---|
| `ui-rendering-01` nav label swap | #12, #14 | `docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/` | `docs/runs/2026-07-07-l3-repeatability-ui-rendering-01/` | Saved/Search bottom-nav labels are swapped while the app remains functional. |
| `ui-rendering-02` search-card copy mismatch | #17, #18 | `docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/` | `docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/` | Search tab `search_card` renders History copy while the card and navigation still work. |

Both seeds are invisible to L1/L2 by construction: no crash, no ANR, no boundary
state assertion, and no missing target node in the valid defect evidence.

## Live Matched Pairs

| Seed | Baseline result | Defect result | Baseline timing | Defect timing |
|---|---|---|---:|---:|
| `ui-rendering-01` | L1 inconclusive / L2 inconclusive / L3 pass, confidence 0.97 | L1 inconclusive / L2 inconclusive / L3 fail / `ui_rendering`, confidence 0.97 | 99.638s | 111.319s |
| `ui-rendering-02` | L1 inconclusive / L2 inconclusive / L3 pass, confidence 0.96 | L1 inconclusive / L2 inconclusive / L3 fail / `ui_rendering`, confidence 0.97 | 68.051s | 82.535s |

## Fixed-Evidence Repeatability

| Seed | Half | Iterations | Valid verdicts | Errors | Outcomes | Defect classes | Confidence min/median/max | Timing total |
|---|---|---:|---:|---:|---|---|---|---:|
| `ui-rendering-01` | baseline | 5 | 5 | 0 | `pass: 5` | `null: 5` | 0.97 / 0.97 / 0.98 | 100.079s |
| `ui-rendering-01` | defect | 5 | 5 | 0 | `fail: 5` | `ui_rendering: 5` | 0.97 / 0.98 / 0.98 | 86.527s |
| `ui-rendering-02` | baseline | 5 | 5 | 0 | `pass: 5` | `null: 5` | 0.96 / 0.96 / 0.98 | 82.689s |
| `ui-rendering-02` | defect | 5 | 5 | 0 | `fail: 5` | `ui_rendering: 5` | 0.96 / 0.97 / 0.98 | 92.855s |

Aggregate across these two text-layout semantic seeds:

- Repeatability calls: 20 total, 20 valid verdicts, 0 errors.
- Baseline halves: 10/10 pass, 0 inconclusive, 0 fail.
- Defect halves: 10/10 fail / `ui_rendering`, 0 inconclusive, 0 class drift.
- Confidence range across all calls: 0.96-0.98.

## Judge Boundary

For both seeds, the L3 judge receives the run spec's `scenario.l3_spec` plus observed
evidence from the final checkpoint. The judge does not receive:

- `expected_behavior`;
- the injected patch;
- frozen baseline/defect verdict fixtures;
- issue text describing the expected defect outcome.

This boundary keeps the L3 decision tied to product-facing UI semantics in the
observed evidence rather than to the known injected change.

## What This Supports

It is reasonable to use the current L3 path for M2 text-layout semantic seeds under
the same fixed-evidence repeatability discipline:

- add a live matched pair first;
- freeze the observed layout/screenshot/journey evidence;
- repeat only the L3 judge call;
- require stable baseline pass and defect fail / `ui_rendering` before using the seed
  in an M2 text-layout semantic summary.

## What This Does Not Support

This evidence does not support:

- visual-only or multimodal L3 reliability;
- benchmark-wide detection rate;
- benchmark-wide false-positive rate;
- fully unattended Journey reliability;
- claims about non-text semantic UI defects;
- claims about other host apps, internal apps, or ColorOS migration.

The current claim is narrower: **two Wikipedia text-layout semantic L3 seeds have
stable fixed-evidence repeatability under Codex CLI L3 judging.**

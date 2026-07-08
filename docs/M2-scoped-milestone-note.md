# M2 Scoped Milestone Note

This note defines the current M2-alpha evidence package and its limits. It is meant
to keep seed-count evidence, L3 repeatability evidence, and remaining benchmark gaps
separate.

## Source Issues and Evidence

| Area | Issues | Durable evidence |
|---|---|---|
| M1 seed-count baseline | #9, #10 | `docs/M1-goldset-report.md`; M1 run records under `docs/runs/2026-07-05-*` and `docs/runs/2026-07-06-wikipedia-process-death-02-tab-state-loss/` |
| L3 path bring-up and repeatability | #12, #14, #17, #18, #19 | `docs/M2-l3-text-layout-summary.md`; `docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/`; `docs/runs/2026-07-07-l3-repeatability-ui-rendering-01/`; `docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/`; `docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/` |
| M2 seed expansion | #15, #16, #17 | `docs/runs/2026-07-07-wikipedia-config-change-02-query-duplication/`; `docs/runs/2026-07-07-wikipedia-navigation-02-back-button-swallowed/`; `docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/` |

## What Is Proven

### Runner and Evidence Chain

The repo has a working `python -m aiverify.runner` chain from Run Spec through Codex
CLI-driven app navigation, Android CLI / adb evidence capture, Journey Segment
Boundary event injection, L1/L2/L3 oracle evaluation, verdict output, and durable run
records.

### M1 Seed Coverage

M1 has five category seeds and all five injected defects were caught:

- config-change query loss: L2 fail / `state_loss`;
- lifecycle recreation crash: L1 fail / `crash_stability`;
- coroutine-concurrency main-thread ANR: L1 fail / `crash_stability`;
- navigation double-open crash: L1 fail / `crash_stability`;
- process-death tab-state loss: L2 fail / `state_loss`.

This establishes a smoke-grade, audited 5/5 M1 result. It does not establish a
general benchmark detection rate.

### M2 Seed Expansion

M2-alpha currently adds three post-M1 seed-expansion issues:

- #15 `config-change-02` duplicated query state: baseline L2 pass, defect L2 fail.
- #16 `navigation-02` swallowed Back: baseline L2 pass, defect L2 fail.
- #17 `ui-rendering-02` search-card copy mismatch: baseline L3 pass, defect L3 fail /
  `ui_rendering`.

These broaden symptom coverage beyond the original M1 five seeds, but they are still
small-N evidence rather than benchmark-level metrics.

### Text-Layout L3 Repeatability

Two text-layout semantic L3 seeds have passed fixed-evidence repeatability:

- `ui-rendering-01`: #12 live matched pair, #14 repeatability.
- `ui-rendering-02`: #17 live matched pair, #18 repeatability.

The consolidated summary is `docs/M2-l3-text-layout-summary.md`. Across both seeds,
the fixed-evidence repeatability package has 20 total L3 judge calls, 20 valid
verdicts, 0 errors, baselines 10/10 pass, defects 10/10 fail / `ui_rendering`, and
confidence range 0.96-0.98.

The L3 judge boundary remains: `scenario.l3_spec` plus observed evidence only. The
judge does not receive `expected_behavior`, the injected patch, issue text, or frozen
verdict fixtures.

## What Is Not Proven

Do not claim the following from the current M2-alpha evidence:

- benchmark-wide detection rate;
- benchmark-wide false-positive rate;
- visual-only or multimodal L3 reliability;
- fully unattended Journey reliability;
- reliability over 100+ AI-generated defects;
- cross-host or non-Wikipedia generality;
- ColorOS migration readiness;
- public throughput or cost metrics for full benchmark execution.

The current public-safe wording is narrower: **the MVP verification chain is live and
audited; M1 caught 5/5 seeded defects; M2-alpha has three additional seed-expansion
issues; and two Wikipedia text-layout semantic L3 seeds passed fixed-evidence
repeatability under Codex CLI judging.**

## Recommended Next Decisions

1. Add another M2 seed deliberately:
   - L2 state/navigation is cheaper and broadens non-L3 evidence.
   - Text-layout L3 broadens semantic coverage but should keep the #14/#18
     repeatability discipline.
2. Clean up metric/schema language before aggregating M2:
   - current L2 mismatch failures may still report as `state_loss` even when the seed
     is duplicated-state or navigation-state.
   - document whether per-seed outcome, oracle defect class, and taxonomy class should
     be separate fields.
3. Harden automation:
   - reduce Agent-In-The-Loop assumptions in Journey execution;
   - keep intent-free navigation constraints;
   - expand recovery and evidence capture around transient Android CLI layout dumps.
4. Only after the above, decide whether to define a larger M2-beta milestone with
   explicit sample size, false-positive controls, and reporting rules.

# M2-beta Inclusion Rules

This note defines the inclusion boundary for the M2-beta audited benchmark slice.
It is an accounting contract, not a new oracle design.

M2-beta exists to turn the current M1 and M2-alpha evidence into a small,
auditable benchmark slice. The benchmark slice must not treat incomplete live
runs, blocked Android execution, or fixed-evidence L3 repeatability calls as
ordinary caught/missed seed outcomes.

Source issues:

- Parent PRD: #24
- Inclusion-rules slice: #25
- Open oversized saved-state candidate: #23
- Existing scoped milestone evidence: #13, #20, #21, #22

## Status Vocabulary

M2-beta uses these seed accounting states:

| State | Counts in injected-defect denominator | Meaning |
|---|---:|---|
| `included` | yes | The seed has valid baseline/control evidence, valid defect evidence, durable artifacts, and an interpretable oracle result under these rules. |
| `control` | no | A baseline/control lane used to check false positives. It is reported separately as `passed_control` or `false_positive`. |
| `repeatability-only` | no | A fixed-evidence L3 replay package that supports judge stability but is not a new live seed outcome. |
| `candidate` | no | Seed implementation exists, but valid M2-beta evidence is not complete. |
| `blocked` | no | A live run attempt was prevented by host, device, emulator, harness, or evidence-capture instability. |
| `excluded` | no | Evidence exists, but it is outside the M2-beta scope or invalid for benchmark accounting. |

Only `included` injected-defect seeds can contribute to caught/missed counts.
Every other state must be reported outside the numerator and denominator.

## Valid Included Seed

An injected-defect seed is `included` only when all of the following are true:

1. The seed has committed benchmark artifacts: a run specification, injected
   patch, human-readable seed description or equivalent documentation, and
   regression coverage for the oracle-level expectation.
2. The baseline/control path and the defect path exercise the same user-facing
   scenario, system-event boundary, and assertion surface unless the seed
   explicitly documents why no system event applies.
3. The baseline/control path reaches the target surface and does not fail any
   oracle for the defect under measurement.
4. The defect path reaches the intended trigger or observation surface and
   produces an interpretable L1, L2, or L3 oracle result.
5. The live evidence is durable: run records, relevant logs/layouts/verdicts,
   issue comments, and known gaps are committed or otherwise linked from the
   repo.
6. The seed can be represented by metric context without conflating taxonomy
   category with oracle defect class.

A seed without a valid baseline/defect matched pair cannot count as caught or
missed. It must be marked `candidate`, `blocked`, or `excluded`.

## Outcome Rules

For `included` injected-defect seeds:

- `caught` means at least one oracle returns `fail` on the defect path.
- `missed` means no oracle returns `fail` on the defect path.

For `control` baseline lanes:

- `passed_control` means no oracle returns `fail`.
- `false_positive` means any oracle returns `fail`.

Baseline controls are reported beside injected-defect outcomes, but they do not
increase the injected-defect seed denominator. They protect the interpretation
of caught/missed counts.

## Live Evidence vs Fixed-Evidence Repeatability

Live matched-pair evidence answers whether the verification chain can catch a
seed in an end-to-end run. Fixed-evidence repeatability answers whether an L3
judge gives stable decisions when replaying the same observed evidence.

M2-beta must report these separately:

- Live matched-pair evidence can count in caught/missed accounting when it
  satisfies the included-seed rules.
- Fixed-evidence repeatability can support an L3 stability claim, but it must
  not add extra seeds, caught outcomes, missed outcomes, or control outcomes.

The existing text-layout L3 repeatability packages are therefore
`repeatability-only` evidence. They support the bounded L3 claim already
summarized in the M2 text-layout report.

## Initial M2-beta Classification Guidance

This table is guidance for the next slices. Later aggregation work may refine
the rows after metric-context backfill, but it must preserve the counting rules
above.

| Evidence family | Initial M2-beta status | Counting note |
|---|---|---|
| M1 five-seed report | eligible for `included` after metadata audit | Counts only through one row per injected-defect seed, not through every artifact. |
| Completed M2 expansion seeds | eligible for `included` after metadata audit | Includes config-change duplicated state, navigation swallowed Back, and search-card copy mismatch. |
| Text-layout L3 repeatability packages | `repeatability-only` | Supports L3 repeatability; does not add denominator rows. |
| Oversized saved-state process-death seed (#23) | `candidate` and currently `blocked` | Excluded from caught/missed counts until a valid baseline/defect matched pair exists. |

## Oversized Saved-State Candidate Boundary

The `wikipedia-process-death-03-oversized-saved-state` seed has committed seed
artifacts, but the 2026-07-09 live retry did not produce valid benchmark
evidence:

- baseline build and install succeeded;
- the app failed before reaching `nav_tab_search`;
- Android CLI layout / UIAutomator remained unstable after emulator refresh;
- no defect lane was run.

Therefore #23 is not an M2-beta `included` seed today. It must remain outside
the M2-beta numerator and denominator unless a future run captures a valid
baseline/defect matched pair on a stable emulator or real device.

M2-beta quarantine note: `docs/M2-beta-oversized-saved-state-quarantine.md`.

## Out-of-Scope Claims

M2-beta inclusion must not be used to claim:

- benchmark-wide detection rate;
- benchmark-wide false-positive rate;
- reliability over 100+ AI-generated defects;
- fully unattended Journey reliability;
- visual-only or multimodal L3 reliability;
- cross-host or non-Wikipedia generality;
- ColorOS migration readiness.

The supported claim is narrower: M2-beta is a small audited benchmark slice with
explicit seed accounting, explicit exclusions, and bounded L1/L2/L3 evidence.

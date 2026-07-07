# Goldset Seed — Wikipedia ui-rendering-01 nav label swap (L3 exercise)

> Issue: [#12](https://github.com/yangliang2/ai_verification/issues/12) — exercise the L3 semantic oracle path.
> Oracle path: **L3 / ui_rendering**, event-less scenario (defect visible on the main screen).
> Run record: [`docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/`](../../../docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/README.md)

## Goal

Prove the verifier catches a **wrong-but-non-crashing on-screen content** defect through
**L3 (LLM semantic judgment)** — the first seed that is invisible to both cheap oracle
layers by construction. Sixth category (ui-rendering), beyond the five M1 categories.

## Defect

`bench/goldset/patches/wikipedia-ui-rendering-01-nav-label-swap.patch`: in
`NavTab.kt`, the `text` string resources of `READING_LISTS` and `SEARCH` are swapped
(models a copy-paste wrong-resource-id mistake):

- the **Saved** tab (`nav_tab_reading_lists`) renders the label **"Search"**
- the **Search** tab (`nav_tab_search`) renders the label **"Saved"**

No crash, no ANR, no missing node, no state loss — every element is present with the
same resource-ids and the app is fully functional. Only the *meaning* of the rendered
labels is wrong, so:

- **L1** sees a clean logcat → inconclusive.
- **L2** has no boundary system event (and every asserted-able node still exists) → not applicable.
- **L3** compares the observed layout against the product spec (`scenario.l3_spec`) → fail.

| dimension | value |
|---|---|
| taxonomy pattern | `ui-rendering-01` (wrong string resource wired to a UI element) |
| verdict symptom axis | `ui_rendering` |
| trigger | none — defect is statically visible on the main screen |
| detector | **L3** (Codex CLI judge via `CodexCliProvider`, provider_id=openai) |
| real-world analogues | copy-paste wrong `R.string.*` id; swapped labels shipped behind unchanged ids |

## Judge contract (what keeps this fair)

- The judge receives **only** `scenario.l3_spec` (the correct-behavior product spec,
  shared verbatim by both halves of the matched pair) plus observed evidence (journey
  results, final checkpoint layout JSON, screenshot paths). It never sees
  `expected_behavior`, the patch, or any hint that a defect may be present.
- Cross-source: the defect patch is Claude-authored (injector ≈ anthropic); the judge
  runs on Codex CLI (`provider_id="openai"`) — satisfies the `providers/base.py`
  injector ≠ verification-side constraint.
- L3 is gated: it runs only because L1/L2 both come back non-fail, per the layered
  oracle design (most expensive layer last).

## Expected verdict

- defect build: L1 = inconclusive, L2 = inconclusive (no event), **L3 = fail,
  defect_class_hypothesis = ui_rendering**.
- baseline build (correct labels), same scenario and same l3_spec: **L3 = pass**.

## Known boundary

- The layout JSON exposes resource-ids alongside labels, so the mismatch is inferable
  from `nav_tab_reading_lists` ↔ "Search" without visual reasoning; screenshots are
  provided as refs but the judge does not need multimodal input for this seed.
- A judge is nondeterministic in principle; the run record freezes the actual judge
  responses as fixtures so the regression test replays them via `MockProvider`
  (hardware- and LLM-independent).

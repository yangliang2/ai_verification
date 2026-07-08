# Goldset Seed Spec - Wikipedia navigation-02 back button swallowed

> Issue: [#16](https://github.com/yangliang2/ai_verification/issues/16) - M2
> navigation Back-button seed.
> Type: **Goldset** Behavior-Layer Defect seed.

## Goal

Add a second navigation seed that complements `wikipedia-navigation-01`, which
is a crash-only duplicate-open defect. This seed exercises a non-crashing
navigation-state failure: the Activity-level Back action is consumed, so the
user remains on the search screen and must press Back again.

## Real-world source pattern

Candidate: `bench/goldset/candidates.md` N3.

- Project: Tusky
- Issue: <https://github.com/tuskyapp/Tusky/issues/3570>
- Fix PR: <https://github.com/tuskyapp/Tusky/pull/3571>
- Pattern: after using search, the first hardware/system Back press had no
  visible effect because SearchView/back dispatch state intercepted the event
  incorrectly.

This Wikipedia seed preserves the behavior-layer shape on a stable host surface:
the search flow works normally, the keyboard Back path is allowed to run, but
the first Activity-level Back callback is swallowed instead of delegating to the
normal dispatcher.

## Host surface

Host: `org.wikipedia.dev` at the same Wikipedia checkout used by M1/M2.

Surface:

- Search tab card: `resource-id="search_card"`
- SearchActivity input: `resource-id="search_src_text"`
- SearchActivity Back callback: `org.wikipedia.search.SearchActivity`

The scenario uses `dark_mode` as an observation boundary after the Back behavior,
because the existing L2 runner evaluates assertions across system-event
boundaries. The defect itself is triggered by the second Back press, not by
`dark_mode`.

## Scenario

1. Start in `org.wikipedia.dev`, complete onboarding if shown, tap the Search
   tab, then tap `search_card` to enter SearchActivity.
2. Type sentinel text `zznavbackqx` into `search_src_text`.
3. Press system Back once to hide the soft keyboard while staying in
   SearchActivity.
4. Press system Back a second time. This is the navigation Back that should
   leave SearchActivity and return to the Search tab surface.
5. At the Journey Segment Boundary, inject `dark_mode` with `night=yes`.
6. Capture Android CLI layout before and after the boundary event.
7. L2 asserts that `search_card` exists by checking
   `search_card.resource-id == "search_card"`.

For live validation after `pm clear`, preseed default shared preferences to skip
host prompts unrelated to this behavior: set `initialOnboardingEnabled=false`,
`exploreFeedUpdatePromptShown=true`, `yearInReviewVisited=true`,
`isYearInReviewEnabled=false`, `searchWidgetInstallPromptShown=true`, and
`hybridSearchOnboardingShown=true`.

## Expected matched-pair behavior

- Baseline build: L1 inconclusive, L2 pass. After the second Back press, the app
  is back on the Search tab and `search_card` is present before and after
  `dark_mode`.
- Defect build: L1 inconclusive, L2 fail. The first Activity-level Back callback
  is consumed, so after the second Back press the app remains in SearchActivity;
  after `dark_mode`, `search_card` is absent and `search_src_text` remains
  visible.

The current L2 defect class remains `state_loss` because the verdict schema has
not yet been broadened for navigation-state mismatches. The evidence text
preserves the navigation-specific symptom by recording that `search_card` did
not reappear after the Back path.

## Injection

Patch:
`bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch`.

The patch adds an intentionally faulty first-Back swallow to
`SearchActivity`'s `OnBackPressedCallback`. The first Activity-level Back
callback records instrumentation but returns without disabling the callback or
delegating to `onBackPressedDispatcher`; a later Back can still delegate. This
keeps the defect faithful to the "first Back does nothing" real-world pattern.

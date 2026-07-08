# Goldset Seed Spec - Wikipedia ui-rendering-02 search card copy mismatch

> Issue: [#17](https://github.com/yangliang2/ai_verification/issues/17) - M2.
> Oracle path: **L3 / ui_rendering**, event-less scenario.

## Goal

Add a second text-layout semantic seed for the L3 oracle. Unlike
`wikipedia-ui-rendering-01`, which checks bottom-navigation labels, this seed checks
copy on the Search tab's search-entry card. The defect keeps the same screen, resource
IDs, and navigation behavior, but renders text from the wrong feature.

## Defect Shape

Host surface: the Wikipedia bottom Search tab, specifically the card that opens
`SearchActivity`:

- Search entry card: `resource-id="search_card"`
- Search card label: `resource-id="search_text_view"`
- Search card icon content description: `resource-id="search_icon"`

Patch:
`bench/goldset/patches/wikipedia-ui-rendering-02-search-card-copy-mismatch.patch`.

The patch changes `HistoryFragment.SearchCardViewHolder.updateSearchHint()` so that
the Search tab's `search_card` label and icon content description use
`R.string.history_empty_message` (`Track what you've been reading here.`) instead of
the normal search hint. This preserves the app's behavior and UI structure while
making the visible copy describe reading history instead of search.

## Scenario

1. Launch `org.wikipedia.dev`, skipping onboarding or prompts if they appear.
2. Tap the bottom Search tab (`nav_tab_search`).
3. Capture the Search tab with `search_card`, `search_text_view`, and `search_icon`
   visible. Do not tap into SearchActivity.
4. L1 should remain inconclusive and L2 should be not applicable because there is no
   crash and no boundary system event.
5. L3 compares the final layout against `scenario.l3_spec`.

For live validation after `pm clear`, preseed default shared preferences to skip host
prompts unrelated to this behavior: set `initialOnboardingEnabled=false`,
`exploreFeedUpdatePromptShown=true`, `yearInReviewVisited=true`,
`isYearInReviewEnabled=false`, `searchWidgetInstallPromptShown=true`, and
`hybridSearchOnboardingShown=true`.

## Expected Matched-Pair Behavior

- Baseline build: L1 inconclusive, L2 inconclusive/not applicable, L3 pass. The
  `search_text_view` and `search_icon` content describe searching Wikipedia, normally
  `Search Wikipedia` or the hybrid search prompt when that experiment is enabled.
- Defect build: L1 inconclusive, L2 inconclusive/not applicable, L3 fail /
  `ui_rendering`. The same `search_card` node is visible, but the card copy says
  `Track what you've been reading here.`, which belongs to History rather than Search.

## Judge Boundary

The L3 judge receives only the correct-behavior product spec and observed evidence. It
does not receive this defect description, the patch, or `expected_behavior`. This keeps
the matched pair fair and preserves the cross-source L3 discipline established by #12
and measured by #14.

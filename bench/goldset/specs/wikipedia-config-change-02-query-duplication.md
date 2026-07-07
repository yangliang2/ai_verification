# Goldset Seed Spec — Wikipedia config-change-02 query duplication

> Issue: [#15](https://github.com/yangliang2/ai_verification/issues/15) — M2
> config-change duplicated-state seed.
> Type: **Goldset** Behavior-Layer Defect seed.

## Goal

Add a second config-change seed that complements the existing
`wikipedia-config-change-01` state-loss seed. This seed exercises the opposite
restore failure: saved UI state is restored and then appended again, so the
visible value is duplicated rather than lost.

## Real-world source pattern

Candidate: `bench/goldset/candidates.md` C3.

- Project: Thunderbird for Android / K-9 Mail
- Issue: <https://github.com/thunderbird/thunderbird-android/issues/10288>
- Duplicate report: <https://github.com/thunderbird/thunderbird-android/issues/10595>
- Fix PR: <https://github.com/thunderbird/thunderbird-android/pull/10353>
- Pattern: recipient token text is restored from saved state and appended to
  existing field contents on configuration change instead of replacing them.

This Wikipedia seed preserves the same behavior-layer pattern on a stable host
surface: the SearchView query is correctly present before the config change, then
the injected restore hook appends the restored query to itself after `uiMode`
recreation.

## Host surface

Host: `org.wikipedia.dev` at the same Wikipedia checkout used by M1.

Surface: `SearchFragment` search input, exposed in Android CLI layout as
`resource-id="search_src_text"`.

`SearchActivity` consumes `orientation|screenSize`, so rotation does not recreate
the activity and cannot exercise restore logic. This seed uses `dark_mode`
(`uiMode`) as the Journey Segment Boundary because that configuration change
forces recreation on this host and was already proven by the M1 config-change
seed.

## Scenario

1. Start in `org.wikipedia.dev`, complete onboarding if shown, tap the Search
   tab, then tap the search card to enter the search input.
2. Type sentinel text `zzsentinelqx` into `search_src_text`, verify the field
   shows that value, then press system Back once to hide the soft keyboard while
   staying on the SearchActivity search page.
3. At the Journey Segment Boundary, inject `dark_mode` with `night=yes`.
4. Capture Android CLI layout before and after the boundary event.
5. L2 asserts `search_src_text.text == "zzsentinelqx"`.

For live validation after `pm clear`, preseed default shared preferences to skip
host prompts that are unrelated to this behavior: set
`initialOnboardingEnabled=false`, `exploreFeedUpdatePromptShown=true`,
`yearInReviewVisited=true`, `isYearInReviewEnabled=false`, and
`searchWidgetInstallPromptShown=true`.

## Expected matched-pair behavior

- Baseline build: L1 inconclusive, L2 pass. The query is restored exactly once.
- Defect build: L1 inconclusive, L2 fail. The query becomes
  `zzsentinelqxzzsentinelqx`, showing duplicated/over-restored state rather than
  simple state loss.

The current L2 defect class remains `state_loss` because the verdict schema has
not yet been broadened to split `state_diff` into loss vs duplication. The
evidence text carries the important distinction by recording the actual duplicated
value.

## Injection

Patch:
`bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch`.

The patch adds an intentionally faulty post-restore hook in
`SearchFragment.initSearchView()`: after the view hierarchy restores the SearchView
query, non-blank text is set to `query + query`. The initial happy path remains
correct because the hook runs before the user types on first creation.

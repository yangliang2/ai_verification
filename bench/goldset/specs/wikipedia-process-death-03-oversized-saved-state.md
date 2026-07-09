# Goldset Seed Spec - Wikipedia process-death-03 oversized saved state

> Issue: [#23](https://github.com/yangliang2/ai_verification/issues/23) -
> M2 oversized saved-state crash seed.
> Type: **Goldset** behavior-layer defect seed.

## Goal

Add a seed for a save-state crash that happens only when Android asks an
Activity to persist instance state. The happy path can work normally, but the
boundary path fails because the app writes data that is too large for the
system's saved-state Binder transaction.

This expands M2 beyond silent state loss and navigation-state mismatch: the
failure is a lifecycle/save-state crash caught by L1 logcat evidence.

## Real-World Source Pattern

Candidate: `bench/goldset/candidates.md` P2.

- Project: Tusky
- Issue: <https://github.com/tuskyapp/Tusky/issues/419>
- Fix commit:
  <https://github.com/tuskyapp/Tusky/commit/bc59d4d938ff5565831e052a3461cf94e0bf2bcf>
- Pattern: `onSaveInstanceState` stores an oversized Bitmap-like payload in the
  Bundle. When the Activity is backgrounded or otherwise saved, Android rejects
  the large transaction with `TransactionTooLargeException`.

## Host Surface

Host: `org.wikipedia.dev` at `/Users/80268204/hosts/wikipedia`.

Surface: `SearchActivity`, reached from the bottom Search tab and `search_card`.
The visible assertion target is `resource-id="search_src_text"`, but the expected
detector for the injected build is L1 crash evidence, not L2 state comparison.

The seed uses `app_to_background` as the boundary because it mirrors the source
failure: Android saves Activity state while moving the task behind launcher. A
2026-07-09 live probe showed that `dark_mode` recreates `SearchActivity` but
does not send a Binder transaction large enough to surface this defect, while
pressing Home does.

## Scenario

1. Launch `org.wikipedia.dev`; if onboarding appears, advance to the main feed.
2. Tap the Search tab, then tap `search_card` to open `SearchActivity`.
3. Type sentinel text `zzoversize` into `search_src_text`.
4. Press Back once to hide the soft keyboard while staying on SearchActivity.
5. At the boundary, inject `app_to_background` by pressing Home.
6. Evaluate logcat with L1. L2 may also run as a baseline sanity assertion, but
   this seed's expected oracle is L1.

## Expected Matched-Pair Behavior

- Baseline build: no `TransactionTooLargeException`; L1 remains inconclusive.
- Defect build: L1 fail / `crash_stability`, with logcat evidence that includes
  `FATAL EXCEPTION` and `TransactionTooLargeException` or the fatal platform
  wrapper raised while saving Activity state.

## Injection

Patch:
`bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch`.

The patch adds `SearchActivity.onSaveInstanceState()` and writes a 2 MiB byte
array to the outgoing `Bundle`. This models a full image/Bitmap-like state save
without adding host dependencies or network preconditions. The post-boundary
surface is the launcher, so the run spec intentionally keeps L2 state
assertions empty and relies on L1 crash evidence.

## Boundary

This seed is intentionally not a benchmark-wide metric claim. It is one
additional M2 seed-expansion data point once live matched-pair evidence is
captured. If live validation is blocked by emulator cold-start instability, the
issue evidence must say so explicitly and should not present the seed as an
audited caught-rate data point.

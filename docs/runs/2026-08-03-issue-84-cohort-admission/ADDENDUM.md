# Proposed addendum to the issue #84 decision packet

Date: 2026-08-03 (America/New_York)

## Why an addendum is required

The approved prospective pool cannot supply the required three admissions:

- all three primaries are already-fixed or non-reproducible on the frozen base;
- replacement ranks 1 and 2 are non-reproducible or lack a stable local
  failure oracle; and
- replacement rank 3, T425733, is admissible but supplies only one G-04 slot.

Changing the candidate identities after seeing admission outcomes requires a
new maintainer decision. The existing 3+3, replacement-before-first-invocation,
four-family, separate-denominator, and local-only claim rules remain unchanged.

## Proposed ordered additions

Append these candidates after the previously approved prospective replacement
rank 3:

| New rank | Task | Eligibility snapshot | Risk family | Proposed bounded oracle |
| ---: | --- | --- | --- | --- |
| 4 | [T426893](https://phabricator.wikimedia.org/T426893) | Open/Low; unassigned; no matching open PR found | G-06 resource/storage | warm a recorded gallery media-list and image-metadata response; disable network; reopening the same image must remain renderable from cache with zero second-phase network requests |
| 5 | [T427224](https://phabricator.wikimedia.org/T427224) | Open/Low; unassigned; no matching open PR found | G-08 deterministic ordering/deduplication | load a recorded Polish article/read-more payload; each returned related-page identity must occur exactly once after footer setup, lazy append, and back-stack reload |

Shared frozen development base remains:
`79ef892e5e88dfea705350bbfa1be2ee14458b47`.

If both additions qualify, the prospective slots would be:

- T425733 — G-04 onboarding theme;
- T426893 — G-06 cached gallery availability; and
- T427224 — G-08 deterministic read-more deduplication.

Together with the historical G-03/G-04 evidence, this preserves the approved
G-03/G-04/G-06/G-08 balance. It does not claim exhaustive G-01 through G-08
coverage.

## Read-only source-readiness observations

T426893 has a narrow app-local seam:

- `GalleryViewModel.fetchGalleryItems()` obtains the media list;
- `GalleryItemViewModel.loadMedia()` obtains image/video metadata; and
- both flows gate whether the cached image can be displayed by the gallery.

The task author and Android maintainer explicitly narrowed the issue to caching
the metadata/API responses that currently block display of an already cached
image.

T427224 also has an app-local seam:

- `JavaScriptActionHandler.setFooter()` installs lazy Read More;
- `JavaScriptActionHandler.appendReadMode()` appends the related items; and
- `PageFragment` can invoke footer setup/append across scroll and back-stack
  load paths.

The proposed oracle is identity/count based. It does not depend on visual
judgment or a live production response after the fixture is recorded. The
approved preflight below confirms that both bounded oracles fail on the frozen
base; this does not elevate either result to a formal M6 lane observation.

## Explicit non-selections

- T381534: related duplicate-footer behavior, but the task remains assigned to
  WRai-WMF and therefore fails the approved unassigned admission rule.
- T419101: its remote saved-page timestamp behavior was addressed by merged PR
  6575, already present in the frozen base.
- T392440: plausible stale-image race, but both reporter and maintainer lacked
  a stable reproduction sequence.
- T350895: explicit steps are unknown and the report depends on unreliable
  network ordering.
- T371419: older duplicate Read More report; T427224 provides a newer,
  language-specific, current reproduction target. It remains a related-task
  risk to audit before admission.

## Decision recorded

The maintainer approved:

1. appending T426893 and T427224 as prospective replacement ranks 4 and 5;
2. assigning them G-06 and G-08 respectively, subject to preflight validation;
3. preserving T425733 as the first admissible replacement and preserving the
   approved G-03/G-04/G-06/G-08 balance;
4. performing isolated local checkout/build/test preflights for these two
   candidates under the existing no-upstream-state-change boundary.

This approval admitted neither candidate to a formal M6 lane and did not
authorize upstream state changes. Both candidates passed the bounded admission
preflight below; the six-slot manifest remains the next gate before any formal
invocation.

## Approval and preflight outcome

The maintainer approved this addendum and the same isolated local
checkout/build/test admission boundary in the Codex session on 2026-08-03.
Neither approval nor preflight authorized any upstream state change.

Both candidates produced stable, machine-checkable failing oracles on the exact
frozen base:

- T426893: `media_list_header_slots=4 image_info_header_slots=0`; one expected
  failure, G-06 bounded gallery metadata/cache seam.
- T427224: three recorded Polish identities projected six times across footer
  setup and lazy append instead of three; one expected failure, G-08 bounded
  lifecycle/dedup seam.

The detailed accountable commands, timings, APK identities, raw logcat, and
claim boundaries are in the candidate sub-records under
`prospective/replacement-t426893/` and `prospective/replacement-t427224/`.
They are admission evidence, not formal M6 lane results. The next gate is the
versioned six-slot manifest and its validator/checksum admission checks.

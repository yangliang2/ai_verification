# Prospective admission fixtures

These sources are copied into the exact frozen upstream checkout only for local
admission preflight. They are not upstream patches, formal M6 lanes, or evidence
that an upstream task is fixed.

Each fixture must establish a bounded, machine-checkable behavior oracle before
the task can be admitted. A fixture that passes on the frozen development base,
cannot reproduce the reported behavior, or depends on unbounded external state
is exclusion evidence rather than an admitted prospective case.

Current fixture sources:

| Candidate | Fixture | Bounded oracle |
| --- | --- | --- |
| T429913 | `p-02/M6P02OfflineCleanupTest.kt` | Bounded registered-offline cleanup removes seeded rows/files through the production worker path. |
| T419910 | `replacement-t419910/M6T419910DiscoverCorpusPreflightTest.kt` | Local 273-page corpus loads and samples deterministically without claiming the live network phase. |
| T425733 | `replacement-t425733/M6T425733OnboardingThemeTest.kt` | Fresh-install onboarding screens retain one light system theme across the first two pages. |
| T426893 | `replacement-t426893/M6T426893GalleryMetadataOfflineTest.kt` | Gallery media-list and image-metadata Retrofit methods both expose the save/lang/title headers required by the offline-cache contract. |
| T427224 | `replacement-t427224/M6T427224ReadMoreLifecycleTest.kt` | The recorded Polish three-item Read More identity set remains unique across footer setup and lazy append commands. |

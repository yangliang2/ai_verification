# Frozen selection evidence for M6 cohort v1

This immutable selection record binds the six admitted slots and the ordered
replacement/exclusion decisions to the #84 admission preflight. It is kept
separate from the evolving run-record overview so manifest artifact checksums
remain stable.

Source base: `79ef892e5e88dfea705350bbfa1be2ee14458b47`

Historical pairs:

- H-01 T425894: `b88c6a672e18167727fcc9d913c9ed57e50e03ce` →
  `996ad8592fbd41e59ea195da72a3e9a728181006`; matched fail/pass.
- H-02 T379777: `675b930624c80498b3d3881592ac1c3f179a2709` →
  `c7250ce14feaa24e52d3a2468fb86b15fa56cfff`; matched fail/pass.
- H-03 T382892: `d67ec44adc1d8c4d8dc7dcb736c0faa9f1b6934c` →
  `fdc4ffb9ef3be93a96500bf630057c1e66ac7b8f`; matched fail/pass.

Prospective admissions:

- P-01 T425733, G-04: expected onboarding light-theme mismatch; 1/1 expected
  failure on the frozen base.
- P-02 T426893, G-06: expected gallery metadata offline-header gap; 1/1
  expected failure on the frozen base.
- P-03 T427224, G-08: expected Polish Read More duplicate projection; 1/1
  expected failure on the frozen base.

Excluded before formal invocation:

- P-01/T431797: locale switch updated the reported chrome/navigation.
- P-02/T429913: bounded registered-offline cleanup passed and did not exercise
  the reporter-scale category.
- P-03/T424161: PR 6575 was already an ancestor of the frozen base.
- P-ALT-01/T426527: power-saving attribution and campaign end.
- P-ALT-02/T419910: local corpus passed; live-network phase lacked a stable
  local oracle.

Replacement events consume ranks P-ALT-03, P-ALT-04, and P-ALT-05 into P-01,
P-02, and P-03 respectively. All occurred before the first formal invocation;
`execution_state.formal_invocations_started` is empty.

The run record under this directory contains exact commands, pass/fail counts,
timings, APK identities, screenshots/logcat, external snapshots, and claim
boundaries. This selection record does not authorize formal execution or any
upstream repository interaction.

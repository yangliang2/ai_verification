# Issue #72 compatibility matrix contract

The fixture must retain `AIVERIFY-ISSUE-72-SENTINEL` while API-35 applies the
declared per-app locale and orientation. English uses LTR ordering. Arabic uses
localized resources and RTL-relative ordering: the logical start anchor appears
to the right of the logical end anchor. Every declared cell is accounted for;
missing or contradictory locale, orientation, form-factor, state, semantic, or
layout evidence fails closed. This bounded local slice makes no detection-rate,
Goldset, upstream-acceptance, accessibility, or general device-coverage claim.

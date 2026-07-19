# Runtime permission denial and revocation slice

This is a bounded behavior-layer verification slice for GitHub #70. It is not a
Goldset seed and it must not be used for a detection-rate or upstream-acceptance
claim.

## Fixture

The debug-only `PermissionFixtureActivity` uses Wikipedia's already-declared
`android.permission.ACCESS_FINE_LOCATION` runtime permission. The screen exposes
stable accessibility IDs for the permission status, Android's
`shouldShowRequestPermissionRationale()` result, request/refresh/use controls,
and the two acceptable fallbacks: continue without location and open app
Settings.

The baseline checks permission immediately before using `LocationManager`, keeps
the app usable after denial or revocation, and exposes Settings after the second
denial. The candidate deliberately removes those fallbacks and calls
`LocationManager` without rechecking the permission.

## Matched Journey

Both APKs execute the same actions and permission boundaries on the same device:

1. Reset `ACCESS_FINE_LOCATION` to a pristine denied state and clear user
   decision flags.
2. Request the real Android permission dialog and deny it once. Record denied
   package state with `USER_SET` and without `USER_FIXED`.
3. Request again and deny if Android shows the dialog. Record the denied package
   state and the on-screen rationale observation; a second denial is treated as
   permanent only when the system no longer offers the rationale/dialog path.
4. Grant through a deterministic package-manager boundary and verify the feature
   is usable.
5. Open the real Android App info screen through a deterministic harness
   boundary. Drive Permissions → Location → Don't allow through visible Settings
   UI, return to the fixture, refresh, access the feature again, and retain UI,
   screenshot, logcat, package-state, and action evidence.

## Oracle contract

- L1 fails with `crash_stability` for an uncaught AndroidRuntime
  `SecurityException`; this is runtime reliability evidence, not a security
  business or certification claim.
- L2 checks the first-denial status and catches a blocked UI or missing fallback.
- L3 receives the Journey, screenshots, final layout, and recorded permission
  postconditions; it may pass only when denial/revocation leaves an explicit,
  usable fallback.
- Any unobservable permission state, missing evidence, failed Journey action, or
  independent-agent ambiguity is fail closed and cannot support a pass claim.

## Expected bounded outcomes

- Baseline: first denial, permanent denial, granted, and revoked states are all
  observable; the app offers continue-without-location and Settings fallbacks.
- Candidate: denial produces `BLOCKED: Location permission is required.` with no
  continue/Settings controls; using the location seam after revocation would
  throw `SecurityException`. The oracle fixtures cover both failure modes.

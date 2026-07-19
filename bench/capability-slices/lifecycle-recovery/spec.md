# Lifecycle and backup-recovery capability contract

This slice verifies one local Android capability: deterministic persisted state
survives configuration recreation and real background process death, then is
restored through Android's local backup transport and migrated exactly once.

## Stable fixture

The committed app creates a legacy SharedPreferences record only when the human
or Journey driver taps `create_fixture`. The observable state contract is:

| Phase | Sentinel | Schema | Revision | Migration status |
| --- | --- | --- | --- | --- |
| Created / rotated / process restored | `AIVERIFY-ISSUE-71-SENTINEL` | `1` | `41` | `PENDING_V1_TO_V2` |
| Backup restored | `AIVERIFY-ISSUE-71-SENTINEL` | `2` | `42` | `MIGRATED_V1_TO_V2` |
| Silent reset indicator | `UNINITIALIZED` | any | any | any |

Only `sharedpref/lifecycle_fixture.xml` is eligible for backup. A marker in
`noBackupFilesDir` identifies an existing app-data epoch; Android excludes that
marker from backup. Consequently rotation and process recreation leave the marker
intact, while `pm clear` followed by restore brings back the legacy preferences
without the marker and deterministically enters the migration path.

## Matched Journey and boundary evidence

Baseline and candidate use byte-equivalent actions, system events, assertions,
package, activity, APK glob, and correct-behavior specification. The candidate
adds only `patches/stale-migration-guard.patch`, which reverses the legacy-schema
guard and leaves restored v1 data stale.

The runner captures UI layout, screenshot, logcat, and command provenance before
and after each boundary. It also records:

1. rotation settings requested and observed;
2. disjoint process IDs before death and after relaunch;
3. selected local backup transport, monitored backup result, restore token,
   monitored restore result, app-data clear result, post-restore process ID, and
   cleanup back to the original backup configuration.

The machine oracle fails closed when layouts, process identity, or successful
backup/restore evidence are absent. Accountable failures are classified as
`crash`, `state_loss`, `silent_reset`, or `stale_state`; the exact successful
state is `correct_restoration`.

This capability slice makes no detection-rate, Goldset, or upstream acceptance
claim. Results apply only to the recorded toolchain, APKs, emulator, and matched
executions in the associated run record.

# Issue #74 performance/resource and Intent-security run

Date: 2026-07-20. Device: `emulator-5554`, API 35, fingerprint recorded in
`raw/environment.txt`. Fixture package: `dev.aiverify.lifecyclefixture` 2.0,
target SDK 35. APK SHA-256 is recorded in `raw/apk.sha256`.

The preregistered cold-start threshold was 1000 ms; three baseline cold starts
were 231, 508, and 253 ms (median 253 ms). Baseline gfxinfo reported no frame at
or above the 700 ms frozen boundary. The narrow performance candidate recorded a
902 ms main-thread frame-callback workload and was rejected. The narrow security
candidate forwarded the package-confined nested Intent and reached `SensitiveActivity`;
it was rejected while the performance domain remained supported.

Storage pressure was observed as LOW after `force-low -f` and NORMAL after reset.
Battery pressure was observed at level 10 and restored to level 100; low-power mode
was restored to its prior value 0. No fixture-owned held wake lock was observed.
The shell could start the exported gateway but direct launch of the non-exported
sensitive Activity produced `SecurityException`. The immutable one-shot token kept
the SAFE_TOKEN action despite a fill-in action and rejected its second send.

Machine inputs and outputs are the three `*-evidence.json` and `*-oracle.json`
files. `raw/` contains startup, gfxinfo/framestats, resource-pressure receipts,
package/component output, layouts, preferences, wakelocks, crash log, environment,
and APK checksum. This is a bounded local result, not a detection-rate, Goldset,
upstream-acceptance, energy-attribution, fleet-performance, or general security claim.

# Performance, resource-pressure, and Intent-security slice

Run on the named API 35 emulator. Before each lane, force-stop and clear graphics
statistics. Record three cold starts with `am start -W`; use the median `TotalTime`.
The cold-start threshold is 1000 ms. After tapping **Render frame**, collect
`dumpsys gfxinfo ... framestats`; a frame at or above 700 ms is frozen and the
allowed frozen-frame count is zero.

Exercise storage pressure with `cmd devicestoragemonitor force-low -f` and restore
with `cmd devicestoragemonitor reset`. Exercise battery pressure with
`dumpsys battery unplug`, `dumpsys battery set level 10`, and low-power mode; restore
with `dumpsys battery reset` and the preregistered prior low-power setting. Store
command receipts and before/during/after observations. Capture fixture-owned held
wake locks and crash/ANR logs.

The security lane passes hostile input only to the exported fixture gateway. Its
nested target is package-confined. Record rejection of malformed extras and nested
redirection, denial of direct shell launch of the non-exported sensitive Activity,
and immutable one-shot PendingIntent fill-in/replay behavior.

Performance/resource and Intent-security evidence are judged separately. Missing
evidence or failed cleanup in either domain makes the aggregate non-accountable.
This local slice makes no detection-rate, Goldset, upstream-acceptance, energy-use,
fleet-performance, or general security-certification claim.

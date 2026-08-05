# M7-R1 synchronous weather runtime contract

The frozen source fixture models a synchronous `WeatherProvider.current` call
from a critical UI-style consumer.  The Android adapter exposes the same call
on `TemporalActivity`'s main thread and records a bounded observation in
`TemporalProbe` logcat events.

The verifier-facing Journey only observes the screen.  The auditor-only oracle
reads `TEMPORAL_RESULT` and compares caller latency with the preregistered
200 ms local budget.  This is a matched local control/defect probe, not an ANR
rate or general Android coverage claim.

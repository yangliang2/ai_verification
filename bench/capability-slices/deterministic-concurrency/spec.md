# Deterministic concurrency slice

Run both preregistered schedules on the named API 35 emulator. For
`new-before-old`, launch the fixture, release NEW, wait for its acknowledged
completion, then release OLD and wait for the terminal event. For
`destroy-before-release`, launch the fixture, issue DESTROY and observe its
acknowledged lifecycle/cancellation events, then release PENDING and wait for the
terminal event. Each control broadcast blocks for at most five seconds while the
explicit worker barrier completes; arbitrary sleeps are not schedule controls.

Capture the monotonic journal from fixture-owned storage, bounded crash/ANR
queries, cleanup, local and pulled-installed APK hashes, package/device/tool
identity, and checksums. Apply the concurrency oracle separately to both schedules
and aggregate fail closed. This fixture result does not establish general Android
concurrency correctness, stress/fuzz coverage, a detection rate, Goldset status,
or upstream acceptance.

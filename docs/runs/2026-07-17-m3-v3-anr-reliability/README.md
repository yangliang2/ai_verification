# M3 V3 ANR Reliability Package

This immutable child package contains six fresh lanes for
`wikipedia-coroutine-concurrency-03-main-thread-anr`: three baseline controls and
three injected-defect repetitions. All six first attempts are accountable. The
controls passed and all defects were caught by L1 as `crash_stability`.

The package uses the public runner and the frozen v3 manifest. Every attempt
retains its runner output, live-validation gate, schema-v2 ExecutionRecord,
execution provenance, Journey artifacts, checkpoints, oracle evidence, verdict,
and checksum manifest. APKs remain external because of their size; exact paths,
sizes, and SHA-256 values are retained in `environment.json`.

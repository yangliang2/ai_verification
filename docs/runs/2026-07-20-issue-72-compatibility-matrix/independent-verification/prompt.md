# Independent Verification Agent prompt

Act as the one separate Verification Agent required by GitHub issue #72. Perform
a read-only audit; do not edit files, run destructive commands, or post to GitHub.

Audit the issue #72 Agent Brief, the compatibility-matrix implementation and
tests, all eight canonical baseline/candidate lanes under this run directory,
their checksum manifests, ExecutionRecords, provenance, system-event receipts,
layout evidence, aggregates, matched Run Specs, frozen one-line defect patch,
device cleanup evidence, and the preserved non-accountable tablet attempt.

Determine whether the evidence supports only this bounded conclusion: the
four-cell API-35 baseline is locally supported, while the matched candidate is
healthy in the English control and locally rejected in all three Arabic RTL
cells. Check accountability, exact matrix accounting, baseline/candidate input
matching, APK/deployment identity, trusted locale/rotation/cleanup postconditions,
localization, RTL geometry, state preservation, automated-test results, and
scope limitations. Return exactly one JSON object conforming to
`bench/capability-slices/compatibility-matrix/independent-conclusion-schema.json`.
Use `locally_supported` only if that complete bounded claim is supported;
otherwise use `locally_rejected` or `non_accountable` and explain why.

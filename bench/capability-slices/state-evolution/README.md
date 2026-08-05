# State-evolution runtime adapter

This capability slice binds the neutral state-evolution discovery fixture to
the existing local Android lifecycle-recovery host.  It is an adapter contract,
not a formal qualification manifest: it contains package/activity identity,
bounded system-event names, and reversible safety limits only.  Cohort mapping,
attack hypothesis, Run Spec compilation, and variant adjudication are owned by
the later M8 tickets.

The matched source pair is the checked-in lifecycle-recovery app and a
localized source change. The auditor-only mapping and checksum-bound build
recipe live under `bench/discovery-fixtures/state-evolution/auditor/`; the
public adapter does not expose which source member is selected for an attempt.

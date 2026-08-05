# State-evolution discovery fixture

This is a small, neutral source descriptor for the M8 state-evolution risk
family.  It exposes the persistence path and its continuity contract without
encoding which matched build contains a fault.  The same context manifest is
bound to either a `ChangeTarget` or a no-diff `ProjectTarget` by the discovery
loader.

The fixture models one bounded local epoch:

`legacy writer → durable SharedPreferences record → schema 1 → one migration
edge → schema 2 reader → process/backup recovery boundary`

The public artifacts do not contain a variant label, a prescribed Journey, an
expected observation, or a conclusion.  The state contract describes the
invariant that must hold; the runtime oracle evaluates only accountable
observations against that invariant.

The Android adapter reuses the checked-in lifecycle-recovery app and its
deterministic `MainActivity`/`StateStore` boundary.  This descriptor remains
fixture-local and does not claim framework-wide persistence coverage.

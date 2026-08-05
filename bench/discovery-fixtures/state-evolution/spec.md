# State-evolution fixture contract

The fixture's durable-state quality contract is continuity across one bounded
local recovery epoch.  A deterministic version-one record contains the
sentinel, schema 1, revision 41, and a pending migration marker.  The current
reader owns one schema transition to version 2 / revision 42 and preserves the
sentinel.  The recovery epoch crosses rotation, a real background process
death/relaunch, and a local backup/clear/restore/relaunch boundary.

The adapter must collect terminal process, transport, package/activity, and
state observations before the state oracle may classify the attempt.  Missing,
contradictory, stale, or unbound evidence remains non-accountable.  All device
state is local and reversible; this contract does not cover production data,
cloud restore, downgrade, concurrent migration, or framework-wide support.

The contract describes a product invariant, not a prescribed Journey or a
variant outcome.  Matched source variants are bound by an auditor outside these
verifier-facing artifacts.

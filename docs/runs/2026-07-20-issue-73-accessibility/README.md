# Issue #73 installed-APK accessibility slice

## Bounded conclusion

`locally_supported`: on one API-35 `aiverify_api35` emulator, the installed
baseline APK passed all three preregistered main/dialog/navigation checkpoints.
The matched candidate remained visually healthy and completed the same Journey,
but the one-line `IMPORTANT_FOR_ACCESSIBILITY_NO` defect removed the Continue
control's declared content description from observed device semantics, so the
oracle returned accountable `locally_rejected`.

This is one fixture slice. It is not WCAG certification, full Accessibility
Test Framework or TalkBack parity, physical/OEM/device-fleet coverage, Goldset,
benchmark-wide coverage, a detection rate, or upstream acceptance evidence.

## Verification commands and results

- `bench/fixtures/lifecycle-recovery-app/gradlew -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug --no-daemon` — baseline and candidate each `BUILD SUCCESSFUL in 3s`; 33 tasks. The first clean fixture build was successful in 4s.
- `PYTHONPATH=src .venv/bin/pytest -q tests/bench/test_accessibility_slice.py tests/runner/test_run_spec.py tests/runner/test_evidence.py --junitxml=.../focused-pytest.xml` — 45 passed, 0 failed/error/skipped; JUnit 0.058s.
- `PYTHONPATH=src .venv/bin/pytest -q --junitxml=.../full-pytest.xml` — 652 passed, 0 failed/error/skipped; JUnit 16.175s.
- `PYTHONPATH=src .venv/bin/python -m compileall -q src` — exit 0.
- `python -m aiverify.bench.accessibility_slice --contract .../contract.json --layouts .../baseline/layouts --uiautomator-xml --density 2.625 --output .../baseline/oracle.json` — exit 0, accountable `locally_supported`, 3/3 checkpoints supported.
- The same oracle against candidate evidence — expected exit 1, accountable `locally_rejected`; main rejected as `missing_or_wrong_accessible_name`, dialog/navigation supported.
- `python -m aiverify.bench.run_record_checksums docs/runs/2026-07-20-issue-73-accessibility --verify` — root inventory verified after finalization; see `checksums.sha256`.

## Real emulator Journey

Android CLI `1.0.15498356` installed and launched each APK on
`emulator-5554` / `aiverify_api35`, API 35, 1080×2400 px, density 420 dpi
(2.625 scale), fingerprint
`google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys`.
The current coding agent performed the exact main → dialog → close → navigation
Journey using Android CLI layouts first and serial-scoped adb input. Each state
has a serial-scoped UIAutomator hierarchy and screenshot. All six screenshots
were visually inspected; baseline and candidate were visibly equivalent and
the destination remained reachable.

Baseline local APK and installed APK SHA-256 both equal
`90028b278b4b00b13603a1ab4df3a3b304c3d64a7da760c6cf9f8290bddbb87d`.
Candidate local and installed APK SHA-256 both equal
`d1484633c285ee6c0dbb232e9c632bab7ab04d2b4b88691da91eb05089bb8f91`.
Each APK is 933,032 bytes. The frozen patch SHA-256 is
`44579c68b791831c1a6505f616b3e03312f370d7d11ed308ea81563950a156e3`.

## Implementation and artifacts

- The accessibility oracle normalizes serial-scoped UIAutomator XML, preserves
  hierarchy order, converts px bounds using observed density, computes WCAG
  relative-luminance contrast for declared deterministic colors, and fails
  closed for missing/untrusted checkpoints.
- The fixture exposes stable main, dynamic-content, dialog, and destination IDs.
- The contract preregisters exact nodes, names, traversal, 48dp minimum targets,
  contrast inputs, and all three checkpoints.
- The matched Run Specs have identical Journey actions and assertions; only the
  candidate names the frozen one-line patch.
- Automated tests cover missing/wrong/duplicate labels, missing nodes, traversal,
  inaccessible actions, undersized targets, contrast failure, density/geometry,
  missing/extra evidence, XML normalization, and matched-pair constraints.

Artifact inventory before checksums: 6 Android CLI layouts, 6 UIAutomator XML
hierarchies, 6 PNG screenshots, 3 logcat captures, 2 oracle aggregates, 2
ExecutionRecords, 2 provenance records, and 2 JUnit reports. APK binaries are
not committed; their local/installed hashes, sizes, package, activity, device,
and tool identities are recorded in provenance.

## Known gaps

- The bounded oracle consumes device accessibility semantics and deterministic
  declared colors; it does not run the complete Android Accessibility Test
  Framework instrumentation library or infer contrast from antialiased pixels.
- No physical TalkBack speech output, focus announcement timing, Switch Access,
  Voice Access, braille, magnification, font-scale, physical/OEM device, or
  additional API-level validation was performed.
- Execution used the ADR-approved agent-in-the-loop path, not a fully unattended
  Journey runner.

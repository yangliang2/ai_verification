# Installed-APK accessibility verification slice

On one API-35 `aiverify_api35` emulator, inspect the installed fixture's main,
dialog, and navigation states. Preserve Android CLI layout trees, screenshots,
logs, density, APK identity, and ExecutionRecord evidence. The baseline must
pass the preregistered semantic-name, traversal, actionable-control, 48dp touch
target, and deterministic contrast checks. The matched candidate removes only
the Continue button from the accessibility tree and must be rejected while
completing the same Journey.

This is a bounded fixture result, not WCAG certification or complete TalkBack,
device-fleet, Goldset, benchmark-wide coverage, or detection-rate evidence.

# T425733 — onboarding theme admission preflight

Candidate: T425733 (approved replacement rank 3, G-04 locale/theme)

Frozen source base: `79ef892e5e88dfea705350bbfa1be2ee14458b47`

Fixture source:
`bench/m6/admission-fixtures/prospective/replacement-t425733/M6T425733OnboardingThemeTest.kt`

Fixture SHA-256:
`36485f95b5cbf6a40c6dca19eb7f36451fc8a9e551960067c8b02dc63c377cbe`

Accountable command:

```bash
/usr/bin/time -p adb -s emulator-5554 shell am instrument -w \
  -e class org.wikipedia.m6.M6T425733OnboardingThemeTest \
  org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Result: 1 test, 1 expected failure; runner 1.482s; shell wall 2.74s. Under a
LIGHT system/app theme, first-screen edge luminance was `0.0` and second-screen
edge luminance was `1.0` (delta `1.0`), violating the fixture's light-theme
consistency oracle.

Screenshots were visually inspected:

- `first.png` — black first onboarding page
- `second.png` — light second onboarding page

This is a bounded API-35 emulator G-04 oracle. It does not claim an OEM or
physical-device matrix. No upstream source tree, task, branch, commit, PR, or
external repository state was changed.

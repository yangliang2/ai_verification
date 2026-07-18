# M4 T426989 preflight

## Task snapshot

Fetched `https://phabricator.wikimedia.org/T426989` on 2026-07-18. Current task state: `Open, Low`; assignee: `None`; project board: Wikipedia-Android-App Product Backlog. No upstream task was edited.

## Frozen base

- Isolated worktree: `/Users/peter/hosts/wikipedia-t426989`
- Base commit: `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- Baseline APK SHA-256: `81c0a00222a4ac30fce5cf21042583badd3eadefcc5da7bb7c29d9dffe07f076`
- APK package/version: `org.wikipedia`, `50594-fdroid-2026-07-18`
- Install: `adb -s emulator-5554 install -r .../app-fdroid-debug.apk` → `Success`

## Page-type preflight matrix

Each page was opened by an Android VIEW intent, allowed to load, scrolled toward the footer, and captured with `uiautomator dump` plus a screenshot. The machine-readable oracle is presence of `Read more`/`READ MORE` in the UI dump.

| Page type | URL | Read More observed |
|---|---|---|
| Main article | `https://en.wikipedia.org/wiki/Albert_Einstein` | No |
| User | `https://en.wikipedia.org/wiki/User:Example` | Yes |
| Project | `https://en.wikipedia.org/wiki/Wikipedia:About` | Yes |
| Talk | `https://en.wikipedia.org/wiki/Talk:Albert_Einstein` | Yes |
| Special | `https://en.wikipedia.org/wiki/Special:RecentChanges` | Yes |
| Category | `https://en.wikipedia.org/wiki/Category:Physics` | Yes |

Artifacts are under `preflight/` (`*.xml` UI dumps and `*.png` screenshots). This reproduces the reported behavior on the frozen base for non-article page types and provides the pre-implementation page-type matrix.

## Remaining work

The candidate oracle and Development Agent session have not yet been created. No implementation has been started in this worktree.

## Candidate attempt

Candidate commit `5bd7d24d5bcf3da503afb3de4246743014abf168` moves the read-more decision into the footer setup and gates it on article/mainspace status, with URI-prefix defenses for non-article namespaces. Candidate APK SHA-256: `30fb3fd0e3941eecb159688a25fb9d8f1d3ecd6f83aa4a9b18855329b9b23591`.

Fresh cold-launch candidate verification (APK installed successfully, `pm clear` before each VIEW intent, 8-second load) showed no `Read more` for article, user, project, talk, special, or category pages. UI dumps are retained under `candidate/`; #64 remains open pending independent verification.

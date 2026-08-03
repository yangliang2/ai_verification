# M6 historical admission fixtures

These fixtures are pre-formal-lane admission checks for issue #84. They are
copied without modification into both revisions of one frozen historical pair.
The expected result is:

- declared pre-fix revision: the fixture compiles and its regression assertion
  fails;
- declared fixed revision: the same fixture compiles and passes.

The copies in an upstream worktree are temporary, local-only test sources. They
must not be committed or pushed to the upstream repository. Formal
qualification lanes are not created by these checks.

| Case | Fixture | Regression contract |
| --- | --- | --- |
| H-01 | `h-01/M6H01WiktionaryStyleTagsTest.kt` | RESTBase style payload is not rendered as Wiktionary definition text. |
| H-02 | `h-02/M6H02LocalSearchLanguageTest.kt` | Local history, reading-list, and open-tab suggestions are restricted to the selected wiki language. |
| H-03 | `h-03/M6H03ActivityResultCodesTest.kt` | Search link-success and language-change Activity result codes are distinct. |

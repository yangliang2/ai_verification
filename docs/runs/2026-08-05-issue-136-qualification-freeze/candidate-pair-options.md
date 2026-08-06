# Candidate matched-pair options (not selected)

This is decision material for the human gate only. It is not a frozen defect
or control, is not a verifier/generator/planner input, and does not assign any
option to an opaque lane. The unchanged `architecture-samples@ee66e152…`
snapshot is the proposed control baseline for each option. No option has been
patched, built, installed, launched, or executed.

The final pair must be selected and approved by a human. After approval, the
chosen mutation must be materialized in a separate clean local checkout,
identified by an immutable patch/tree/build checksum, and admitted only as
part of the final freeze contract.

## Option A — edit persistence boundary

- Candidate defect locator: `app/src/main/java/com/example/android/architecture/blueprints/todoapp/data/DefaultTaskRepository.kt`, current `updateTask` local upsert at lines 67–75.
- Candidate mutation: make a successful edit report completion while omitting
  the local `TaskDao.upsert` persistence operation.
- Matched control: unchanged source at the same commit.
- Observable contract: after editing a task and returning/reopening it, the
  edited title and description must remain the source-of-truth values.
- Evidence surface: UI task detail/list plus Room-backed state after a
  navigation/process-boundary observation.
- Risk: the mutation is deliberately simple and may be too easy to diagnose;
  human approval must decide whether it is an acceptable M9 target.

## Option B — filter semantic boundary

- Candidate defect locator: `app/src/main/java/com/example/android/architecture/blueprints/todoapp/tasks/TasksViewModel.kt`, current `filterTasks` branches at lines 148–163.
- Candidate mutation: swap the predicates used by the active and completed
  filters while leaving the all-task path unchanged.
- Matched control: unchanged source at the same commit.
- Observable contract: the active filter must show only incomplete tasks and
  the completed filter only completed tasks.
- Evidence surface: visible list contents and filter selection state.
- Risk: this is a UI-semantics defect rather than a persistence/lifecycle
  defect; human approval must decide whether it matches the M9 question.

## Option C — refresh replacement ordering

- Candidate defect locator: `app/src/main/java/com/example/android/architecture/blueprints/todoapp/data/DefaultTaskRepository.kt`, current `refresh` replacement sequence at lines 157–162.
- Candidate mutation: reverse the local replacement order so the fetched
  network tasks are written before the existing rows are deleted.
- Matched control: unchanged source at the same commit.
- Observable contract: a refresh must replace local state with the fetched
  task set, not erase the fetched result.
- Evidence surface: refresh loading transition and post-refresh task list.
- Risk: this interacts with the intentionally fake network data source and
  should be host-tested only after human selection; it is not a formal result.

No option above is an agent decision. The packet intentionally contains no
lane-role mapping, no clear defect/control assignment, and no oracle outcome.

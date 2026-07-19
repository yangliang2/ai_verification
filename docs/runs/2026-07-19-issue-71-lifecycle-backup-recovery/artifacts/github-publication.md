# GitHub publication evidence

Date: 2026-07-19

## Durable evidence push

Command:

~~~sh
git push -u origin issue-71-lifecycle-recovery
~~~

Result: branch created and tracking origin/issue-71-lifecycle-recovery.
Evidence commit:
626d290707a4a6cffc9b58dcb52f0dce29c67838.

## Issue and parent comments

Commands:

~~~sh
gh issue comment 71 --repo yangliang2/ai_verification --body-file docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/issue-comment.md
gh issue comment 68 --repo yangliang2/ai_verification --body-file docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/parent-comment.md
~~~

Results:

- Issue comment:
  https://github.com/yangliang2/ai_verification/issues/71#issuecomment-5015115661
- Parent comment:
  https://github.com/yangliang2/ai_verification/issues/68#issuecomment-5015115813

Raw-body verification commands:

~~~sh
shasum -a 256 docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/issue-comment.md
shasum -a 256 <(gh api repos/yangliang2/ai_verification/issues/comments/5015115661 | jq -rj .body)
shasum -a 256 docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/parent-comment.md
shasum -a 256 <(gh api repos/yangliang2/ai_verification/issues/comments/5015115813 | jq -rj .body)
~~~

Results:

- issue file and GitHub raw body:
  044cbe00f90a3d7a80cf13e9a27ff17eb2e34fa91ea645091a03d030af9682f5
- parent file and GitHub raw body:
  0a18dc55866aa39091c5fec9c3faa8f6519aa128d33922f3aa1495df7d2dcb78

## Label and state transition

Commands:

~~~sh
gh issue edit 71 --repo yangliang2/ai_verification --remove-label ready-for-agent
gh issue close 71 --repo yangliang2/ai_verification --reason completed
gh issue view 71 --repo yangliang2/ai_verification --json number,state,stateReason,labels,url,closedAt
gh issue view 68 --repo yangliang2/ai_verification --json number,state,labels,url
~~~

Results:

- #71: CLOSED, stateReason COMPLETED, closedAt 2026-07-19T08:57:48Z.
- #71 labels: enhancement only; ready-for-agent removed.
- #68: OPEN; parent remains open for unfinished child slices.

# Project board workflow

How our team uses the GitHub Project board. Keeping column meaning and label usage written down means we don't re-explain it every stand-up.

## Columns

Our board has three columns. An issue lives in exactly one at a time.

### To do
Issues that are agreed, scoped, and ready for someone to pick up. An issue only reaches this column when:
- It has a template-based description (bug / feature / task).
- It has at least one label (type, plus optional priority).
- It has an assignee, or is explicitly up for grabs.

### In progress
Someone is actively working on this. Whoever starts work moves the card and assigns themselves if they weren't already. Keep no more than one or two issues per person here at a time — if you're blocked, add the `blocked` label and comment with what you're waiting on.

### Done
The PR that closes the issue has been approved and merged to `main` with green CI. If the PR description includes `Closes #N`, GitHub auto-closes the issue and the Projects automation moves the card to Done — no manual move needed.

## Labels

| Label | When to use it |
| --- | --- |
| `bug` | Something isn't working as expected. Applied automatically by the bug report template. |
| `feature` | New capability or a meaningful change to existing behavior. Applied automatically by the feature request template. |
| `task` | Internal work — chores, refactors, docs, setup. Applied automatically by the task template. |
| `documentation` | Documentation-only changes. Can combine with `task`. |
| `blocked` | Work is paused waiting on something external. Always comment with what you're blocked on. |
| `priority: high` | Must be done this week for the Dec 15 demo. |
| `priority: low` | Nice-to-have — only picked up if higher-priority work is done. |

No explicit priority = medium. Do them roughly in the order they arrived.

## Who moves cards

- **Opener:** creates the issue (lands in To do).
- **Assignee:** moves To do → In progress when they start, and keeps progress comments on the issue.
- **Automation:** moves In progress → Done when the PR merges via `Closes #N`. 

---
name: aidelink-manager-worker
description: Coordinate AideLink main-IDE manager and auxiliary-IDE worker tasks through the AideLink MCP with low-context task packages, explicit user-approved dispatch, file ownership isolation, evidence-based result_ref feedback, manager verification, and final task completion. Use when an IDE should delegate work, receive an AideLink employee task, hand off to a new Codex session, inspect delegated results, or reduce model cost by assigning bounded research, testing, summaries, or isolated code changes to another open IDE.
---

# AideLink Manager Worker

Use AideLink MCP as the state authority. Do not reconstruct task history from chat or edit task state files directly.

## Choose the role

- Act as **manager** when deciding whether to delegate, selecting an IDE, reviewing evidence, or marking work done.
- Act as **worker** when the prompt contains `[AideLink 员工任务]` or a delegated `task_id`.
- Call `get_aidelink_workflow` with the selected role before an unfamiliar flow.

## Manager workflow

1. Read `get_aidelink_tasks` compactly. Expand only the task needed.
2. Call `prepare_aidelink_delegation` with the objective, current decisions, validation commands, `main_owned_paths`, and proposed `worker_owned_paths`.
3. Offer the returned choices. Always preserve “不派发，由主 Codex 完成”. Never dispatch without explicit user approval.
4. Prefer an actually open, idle worker for bounded research, tests, summaries, or isolated files. Do not select the manager IDE as its own worker.
5. After approval, call `delegate_aidelink_task` with `user_confirmed=true` and declared file ownership.
6. Inspect the worker response with `get_delegated_aidelink_task`. Independently check its `result_ref` and validation claims.
7. Call `verify_delegated_aidelink_task` with a concrete `verification_summary` only when the task is truly complete. Otherwise leave it uncompleted and give corrective feedback or create a narrowly scoped follow-up.

## Worker workflow

1. Call `get_delegated_aidelink_task` for the injected `task_id`.
2. Work only on the stated objective. Never modify `main_owned_paths`; for code tasks, stay within `owned_paths`.
3. Run the requested validation and keep a concise evidence reference.
4. On success, call `report_delegated_aidelink_task` with `summary` and `result_ref`.
5. On failure or blockage, call `fail_delegated_aidelink_task` with the error and any available `result_ref`.
6. Never call `verify_delegated_aidelink_task`; only the manager may mark the task done.

## Evidence references

Use a short durable reference instead of pasting large output:

- `commit:<sha>` for committed code.
- `file:<path>` for a report, patch, or log.
- `test:<command/result>` for a bounded verification result.
- `inline:<concise evidence>` only when no durable artifact exists.

Keep summaries focused on outcome, changed scope, validation, and remaining risks.

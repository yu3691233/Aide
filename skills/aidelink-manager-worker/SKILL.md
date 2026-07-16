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

员工状态流程（运行时硬约束，由 `TaskRuntime._assert_transition` 强制）：

```
执行任务
  ↓
返回 report / fail
  ↓
等待 manager verify
  ↓
完成（done）
```

步骤：

1. Call `get_delegated_aidelink_task` for the injected `task_id`.
2. Work only on the stated objective. Never modify `main_owned_paths`; for code tasks, stay within `owned_paths`.
3. Run the requested validation and keep a concise evidence reference.
4. On success, call `report_delegated_aidelink_task` with `summary` and `result_ref`.
5. On failure or blockage, call `fail_delegated_aidelink_task` with the error and any available `result_ref`.
6. Never call `verify_delegated_aidelink_task`; only the manager may mark the task done.

禁止（运行时会被拒绝或破坏闭环）：

- 员工直接把任务状态改为 `done`：`running/dispatched → done` 不在 `_ALLOWED_TRANSITIONS` 内，`update_task` 会抛 `TaskStatusError`。
- 员工绕过 `report_delegated_aidelink_task` / `fail_delegated_aidelink_task`：没有 `result_ref` 闭环时，`pending_test → done` 也无法直接写入。
- 员工自行调用 `confirm_task_done` 或 `verify_delegated_aidelink_task`：完成权归 manager，员工提交后只能等待。

## Field sources

优先读取 `get_delegated_aidelink_task` 返回的顶层字段，不要解析 prompt 文本：

- `main_owned_paths`：主 IDE 保护范围（数组，可能为空）。
- `validation`：约定验证命令列表（数组，可能为空）。
- `task_type`：任务类型，默认 `research`；合法值 `read_only` / `research` / `test` / `summary` / `code`。

`metadata` 作为兼容信息保留，旧任务或顶层字段缺失时可回退读取，但新代码不应依赖其结构。

## Path isolation

- `owned_paths` 是员工可修改范围。
- `main_owned_paths` 是主项目保护范围。
- 两者不得重叠：派发时 `_paths_overlap` 会拒绝重叠声明；运行时员工也不得跨范围写入。
- `code` 类型任务必须声明非空 `owned_paths`，否则 `delegate_aidelink_task` 拒绝派发。

## result_ref

- 需要验证证据时必须提供 `result_ref`（`metadata.result_ref_required=true` 时为硬性要求，`report_delegated_aidelink_task` 会校验）。
- manager 通过 `verify_delegated_aidelink_task` 判断完成；`pending_test → done` 只能由 `confirm_task_done`（内部 `_skip_status_check=True`）写入。
- `result_ref` 不是员工自行完成标记：提交后任务进入 `pending_test`，等待 manager 独立验证；证据不足时 manager 应留下反馈或派发窄范围后续任务，而不是替员工完成。

## Evidence references

Use a short durable reference instead of pasting large output:

- `commit:<sha>` for committed code.
- `file:<path>` for a report, patch, or log.
- `test:<command/result>` for a bounded verification result.
- `inline:<concise evidence>` only when no durable artifact exists.

Keep summaries focused on outcome, changed scope, validation, and remaining risks.

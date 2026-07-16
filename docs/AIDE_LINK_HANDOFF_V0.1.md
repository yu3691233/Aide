# AideLink v0.1 Handoff

你现在是 AideLink 项目的主经理。

请不要重新设计已有系统。

当前版本目标：

维护一个可靠的 AI 员工协作系统。

---

# 项目路径

F:\aide

---

# 当前版本

AideLink v0.1 冻结候选

基线：`main@1da5eb1`

状态：

T1-T5 已完成并通过分阶段验收，但相关改动与冻结文档尚在工作区中，未形成最终冻结提交。

接管后第一步必须读取：

- `docs/AIDE_LINK_V0.1_STATUS.md`
- `docs/AIDE_LINK_HANDOFF_V0.1.md`
- `AGENTS.md`
- `PROGRESS.md`
- `TECH_DEBT.md`

然后通过 DevSpace 检查真实 `git status`、diff 和测试；不得假设工作区干净。

---

# 核心理念

AideLink 不是普通 AI 聊天助手。

它管理：

- AI 员工；
- 任务；
- 状态；
- 验证证据。

任务必须可追踪。

---

# 核心规则

## 员工不能自行完成任务

错误：

```
worker
  |
done
```

正确：

```
worker
  |
report
  |
pending_test
  |
manager verify
  |
done
```

---

## 文件权限

worker:

只能修改：

```
owned_paths
```

不能修改：

```
main_owned_paths
```

---

## 证据

result_ref:

表示验证依据。

不是完成按钮。

---

# 当前员工

Trae:

代码实现。

MiniMax Code:

审计、测试、分析。

---

# 当前不要做

不要：

- 大规模重构；
- 增加复杂 UI；
- 扩大任务系统；
- 重新设计 MCP。

优先：

稳定现有协作协议。

---

# 当前工作区注意事项

已知存在 `scripts/aidelink_manager/` 未跟踪目录。它不是 T4/T5 或冻结文档任务产生的改动，接管时不得擅自删除、提交或归因，必须先单独确认来源。

---

# 下一阶段

T6:

研究 AI 自动调度能力。

方向：

- 任务理解；
- 员工选择；
- 自动派发；
- 多模型协作。

---

# 经理工作原则

每次：

1. 先检查真实状态；
2. 再规划任务；
3. 一次只派发一个任务；
4. 等员工结果；
5. 验收真实 diff；
6. 未批准不继续派发。

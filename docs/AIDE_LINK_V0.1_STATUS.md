# AideLink v0.1 Status

## 版本定位

AideLink 是一个 AI 开发协作调度系统。

目标不是替代 IDE，而是解决多人类/多 AI 协作开发中的任务管理问题：

- 将开发需求转换为结构化任务；
- 将任务分配给不同能力的 AI 员工；
- 保留执行证据；
- 通过状态机控制任务生命周期；
- 避免 AI 自行宣布完成导致结果不可验证。

v0.1 的重点：

> 建立可靠的 AI 员工协作基础协议。

暂不追求复杂自动化。

---

# 当前架构

```
                User
                 |
                 v
          AideLink Manager
                 |
    +------------+------------+
    |                         |
    v                         v
  Trae                  MiniMax Code
Code Worker            Audit Worker
                 |
                 v

            MCP Server
                 |
                 v

          Task Runtime
                 |
                 v

          Task State Machine
```

---

# 核心设计原则

## 1. 任务不是聊天记录

任务必须拥有：

- 唯一 ID
- 状态
- 执行范围
- 验证证据
- 完成确认流程

聊天内容只能辅助理解，不能作为任务状态依据。

---

## 2. 完成必须经过验证

标准流程：

```
prepare
  |
  v
delegate
  |
  v
worker execute
  |
  v
report / fail
  |
  v
pending_test
  |
  v
manager verify
  |
  v
done
```

员工不能直接完成任务。

---

# 已完成能力

## T1-T3：任务闭环基础

完成：

- MCP 任务接口；
- delegated task 生命周期；
- result_ref 证据机制；
- verify 完成确认；
- pending_test 状态保护。

解决问题：

- 无证据完成；
- 状态死锁；
- 自动完成绕过验证。

---

## T4：JSON 接力模式

完成：

### Compact 模式

固定八字段任务接力：

- `objective`
- `completed`
- `changed_files`
- `decisions`
- `validation`
- `remaining`
- `risks`
- `next_step`

### Raw 模式

支持结构化 JSON 接力。

特点：

- 保留 JSON 结构；
- 支持复杂上下文；
- 不改变安全边界；
- 仍属于 untrusted context。

支持：

- deep link
- copy fallback
- URL 长度检查
- 不自动发送。

---

## T5：经理员工契约收敛

完成：

### 状态机硬校验

TaskRuntime 增加状态转换限制。

禁止：
- `running -> done`
- `pending_test -> done`

必须：

```
pending_test
  |
  v
manager verify
  |
  v
done
```

---

### 结构化任务字段

`get_delegated_task` 提供：

- `main_owned_paths`
- `validation`
- `task_type`

减少员工解析 prompt 的依赖。

---

### 员工契约同步

员工规则明确：

- 不自行完成任务；
- 不绕过 report；
- 不调用 verify；
- 使用 result_ref 提供证据。

---

# 当前员工角色

## Trae

定位：

核心开发员工。

负责：

- 复杂代码修改；
- 架构调整；
- 状态机；
- 核心逻辑。

---

## MiniMax Code

定位：

审计/测试员工。

负责：

- 只读分析；
- 风险扫描；
- 测试检查；
- 文档辅助。

限制：

当前无 MCP，需要提供上下文或自行定位能力。

---

# 当前已知风险

## 1. merge_daemon 完成路径

当前允许：

```
merging -> done
```

属于设计允许路径。

未来可考虑增加 result_ref 防御检查。

---

## 2. manual confirm 路径

需要确认 delegated task 是否始终经过 result_ref 检查。

---

## 3. contract 字段整理

部分字段存在：

```
contract / metadata
```

双来源。

目前兼容运行。

未来可统一。

---

# 下一阶段方向

## T6：智能调度

可能方向：

- 自动任务分类；
- 自动选择员工；
- worker capability 注册；
- 自动生成 owned_paths；
- 自动风险评估。

原则：

先保证可靠，再增加自动化。

---

# 冻结状态

当前冻结基于 `main@1da5eb1`，T4/T5 及本冻结文档仍位于工作区改动中，尚未形成最终冻结提交。

新会话接管时必须先读取本文件、`AIDE_LINK_HANDOFF_V0.1.md`，并检查真实 `git status` / diff；不得假设工作区干净或改动已经提交。

---

# 当前版本策略

AideLink v0.1 不追求功能数量。

核心目标：

> 证明多个 AI 员工可以在明确边界下可靠协作。

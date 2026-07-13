# AideLink 文档中心

> 文档较多，部分内容可能是历史方案。当前状态以根目录 `README.md`、`PROGRESS.md`、`TECH_DEBT.md` 为准。

## 常用入口

| 文档 | 用途 |
|---|---|
| [`../README.md`](../README.md) | 项目入口和快速开始 |
| [`../AGENTS.md`](../AGENTS.md) | AI Agent 最小项目规则 |
| [`../PROGRESS.md`](../PROGRESS.md) | 当前状态、任务、未解决 Bug |
| [`../TECH_DEBT.md`](../TECH_DEBT.md) | 技术债、安全风险、清理项 |
| [`product-principles.md`](product-principles.md) | AideLink 的产品边界、任务流原则和差异化定位 |

## 目录说明

| 目录 | 内容 |
|---|---|
| `developer/` | 开发环境、服务端、Android、API、测试等开发文档 |
| `architecture/` | 架构概述、组件、数据流、设计决策、图表 |
| `deployment/` | 安装部署、配置、环境要求、监控 |
| `user/` | 面向用户的安装、配置、使用和故障排查 |
| `changelog/` | 旧版本变更、迁移和开发会话记录 |
| `maintenance/` | 审计、硬编码清理、模块化计划等维护文档 |

## 维护原则

- 新的当前状态不要写进 `docs/` 的历史文档，优先更新 `PROGRESS.md`。
- 技术债统一写入 `TECH_DEBT.md`。
- 长方案和历史记录可以放入 `docs/`，但要标明日期和时效。

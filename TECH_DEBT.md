# AideLink 技术债清单

> 本文件只维护仍需跟进的技术债。项目状态看 `PROGRESS.md`，AI 规则看 `AGENTS.md`。
>
> 状态：❌ 未完成 / ⚠️ 待核查 / ✅ 已完成
>
> 更新时间：2026-07-10

---

## P0 — 安全与稳定性

| ID | 状态 | 技术债 | 位置 | 建议动作 |
|---|---|---|---|---|
| P0-001 | ⚠️ | MiniMax API Key 是否仍有历史明文残留 | `server/` | 搜索并确认；如有真实 key，轮换并改环境变量 |
| P0-002 | ⚠️ | JSON 状态文件写入是否已全部走安全读写 | `server/`、`server/state/` | 复查 `json.dump/load` 调用和状态文件写入路径 |
| P0-003 | ⚠️ | `evolution_daemon.py` / `self_evolution.py` 当前可用性待确认 | `server/` | 用 `py_compile` 和最小导入测试更新状态 |

---

## P1 — 产品化阻碍

| ID | 状态 | 技术债 | 位置 | 建议动作 |
|---|---|---|---|---|
| P1-001 | ⚠️ | 本机路径硬编码是否仍有残留 | 全仓库 | 搜索 `C:\\Users\\mi`、`F:\\AideLink` 等私有路径 |
| P1-002 | ⚠️ | 上传接口鉴权与文件生命周期仍需补齐 | `server/` 上传相关路由 | 已完成扩展名白名单、文件名清理及请求前置限流；继续补鉴权、所有权校验和过期清理 |
| P1-003 | ❌ | `/send` 等耗时链路可能仍同步阻塞 | Server 消息 / 任务链路 | 评估队列化、异步化或状态轮询 |
| P1-004 | ⚠️ | `/evolution/submit` 当前定位需确认 | Server evolution 相关路由 | 明确是正式功能、实验功能还是兼容入口 |
| P1-005 | ⚠️ | 多 IDE 规则文件是否仍重复 | `.github/`、IDE 规则文件 | 保留一个权威源，其它文件只做极短跳转 |

---

## P2 — 代码质量与维护成本

| ID | 状态 | 技术债 | 位置 | 建议动作 |
|---|---|---|---|---|
| P2-001 | ⚠️ | JSON 读取逻辑可能仍有重复 | `server/` | 统一到现有安全读写工具 |
| P2-002 | ⚠️ | `mascot.py` 与 `mascot_tray.py` 可能仍重复 | `server/` | 抽共享逻辑或确认是否还能删除旧入口 |
| P2-003 | ❌ | `call_co_workers.py` 串行调用多个 AI | `server/call_co_workers.py` | 增加超时、失败降级，必要时并发 |
| P2-004 | ⚠️ | 子进程调用退出码/错误处理需复查 | `server/` | 捕获 stdout / stderr / returncode |
| P2-005 | ⚠️ | `shell=True` 使用需复查 | `server/` | 能用参数列表就不用 shell |
| P2-006 | ⚠️ | watchdog / daemon 重启策略需复查 | `server/` | 加退避、上限、日志 |
| P2-007 | ⚠️ | Android 大文件仍需拆分 | `AideLink-app/` | 优先拆职责过多的 Screen / ViewModel |
| P2-008 | ⚠️ | Web 控制台仍有既有初始化错误 | `dashboard.html`、`static/js/config.js` | 核查 `qrCodeInstance` 重复声明及 `loadConfig` 对缺失元素直接赋值 |

---

## P3 — 清理项

| ID | 状态 | 清理项 | 位置 | 建议动作 |
|---|---|---|---|---|
| P3-001 | ⚠️ | 备份脚本、一次性脚本、调试文件 | `server/`、根目录 | 确认无引用后删除或归档 |
| P3-002 | ⚠️ | 测试图片、截图、日志、PID、APK、缓存 | 全仓库 | 确认 `.gitignore` 覆盖后清理 |
| P3-003 | ⚠️ | 运行状态 JSON 是否还在代码目录 | `server/` | 尽量迁移到 `server/state/` |
| P3-004 | ⚠️ | 历史文档过时引用 | `docs/`、`server/*.md` | 删除已不存在模块说明，标注历史文档时效 |

---

## 已完成 / 已删除

| ID | 状态 | 事项 | 说明 |
|---|---|---|---|
| D-001 | ✅ | 旧 Android 归档目录已删除 | 不再作为技术债跟踪 |
| D-002 | ✅ | Happy 集成已删除 | 后续只按需参考有用功能，不恢复为当前依赖 |
| D-003 | ✅ | 根目录 `README.md` 已精简 | 入口文档已更新到当前状态 |
| D-004 | ✅ | `AGENTS.md` 已精简 | 只保留项目特有 AI 规则 |
| D-005 | ✅ | `PROGRESS.md` 已精简 | 当前状态与历史日志分离 |
| D-006 | ✅ | 上传请求前置限流 | 超限请求在 Flask 解析请求体时返回 JSON 413，落盘后仍保留精确文件大小复核 |
| D-007 | ✅ | 分层测试基线 | `scripts/test.ps1` 提供 fast / standard / full，当前含 65 个 Server 和 16 个 Android JVM 测试 |
| D-008 | ✅ | IDE 窗口绑定与自愈 | 用户绑定优先于内置标题规则，按进程、可执行文件、窗口类和标题评分匹配；Web 可保存、测试和重置 |
| D-009 | ✅ | 日志 bug 自动扫描误报收敛 | `task_routes_scanner.py`：阈值改为同签名累计 5 次、改增量扫描（记录字节偏移）、扩展假阳性名单（site-packages / _core / 警告级）、用级别头正则防 UserWarning 误中；`task_routes.py` 增加 `/api/admin/scan_bugs` 独立端点，去除 `/api/tasks` 隐式扫描；删除 `_legacy_scan_logs_for_errors_and_create_tasks` 死代码 |

---

## 建议核查命令

```powershell
rg -n "MINIMAX|API_KEY|C:\\Users\\mi|F:\\AideLink|secure_filename|shell=True|json\.dump|json\.load" server AideLink-app
.\scripts\test.ps1 -Tier fast
.\scripts\test.ps1 -Tier standard
.\scripts\test.ps1 -Tier full
```

# AideLink 项目进度

> 所有 IDE 共用此文件。它只记录**当前状态、重要里程碑、正在进行的任务和未解决问题**。
>
> 维护规则：
> - 完成功能后，更新“已完成功能”。
> - 新增或解决 Bug 后，更新“当前未解决 Bug”。
> - 技术债统一维护到 `TECH_DEBT.md`。
> - 长篇变更日志、历史过程和审计细节不再继续追加到本文件。
>
> 最近整理：2026-07-09，ChatGPT / DevSpace。

---

## 1. 当前项目状态

AideLink 当前是一个 **PC 端 AI 副驾桥接工具**，由三部分组成：

| 模块 | 当前状态 | 说明 |
|---|---|---|
| Android 客户端 | ✅ 可用，持续重构中 | Kotlin + Compose，通过局域网 / FRP 连接 PC 服务 |
| PC 桥接服务 | ✅ 可用，模块化大部分完成 | Flask 服务，提供消息、截图、任务、IDE 管理等接口 |
| AI 协作层 | ✅ 可用，继续优化 | 支持任务派发、IDE 注入、模型调用、反馈通知等流程 |
| 文档治理 | 🔄 进行中 | `TECH_DEBT.md` 已建立，`PROGRESS.md` 已精简为当前状态文档 |

### 当前版本：0.9.16（Windows 产品化发布候选）

- **版本号**：`version.json` = 0.9.16；Android `versionCode` = 69，`versionName` = "0.9.16"
- **Windows 安装方式**：Release 安装包优先；内置 Python 运行时、依赖锁定、安装/卸载自检和单一托盘互斥已纳入发布流程。
- **基线 tag**：`v0.8.0-productization-baseline`
- **用途**：产品化工作（见 `docs/productization/productization-plan.md`）的回滚锚点。任何阶段把功能改坏时，`git checkout v0.8.0-productization-baseline` 可精确回到此基线。
- **基线建立时间**：2026-07-12

---

## 2. 已完成功能

### 2.1 后端 / Server

| 功能 | 主要文件 | 状态 |
|---|---|---|
| Aide 模型切换 API | `phone_chat_bridge.py` `/api/active-models` | ✅ 正常 |
| Aide 对话功能 | `phone_chat_bridge.py` `/evolution/submit` | ✅ 正常 |
| 模型管理 API | `manager.py` `/api/models` | ✅ 正常 |
| 设置 API 与模型设置同步 | `phone_chat_bridge.py`, `SETTINGS_SCHEMA` | ✅ 正常 |
| `model_registry` 集成 | `phone_chat_bridge.py` | ✅ 正常 |
| IDE 扫描器 | `ide_scanner.py` | ✅ 正常 |
| IDE 扫描安全修复 | `ide_scanner.py` | ✅ 正常，不再启动 GUI IDE 进程 |
| 桌面 IDE API | `/api/desktop-ides`, `/api/scan-ides` | ✅ 正常 |
| OC Web 停止进程兜底 | `routes/ide_routes.py` | ✅ 正常 |
| Aide 显示名统一 | `routes/*`, `static/*`, `templates/dashboard.html` | ✅ 正常 |
| 任务派发默认直派模式 | `dispatch_utils.py`, `task_runtime.py`, `task_routes.py` | ✅ 正常 |
| 直发消息 / 快捷回复不入任务列表 | `/send`, `/send/stream`, `task_routes.py` | ✅ 正常 |
| 任务反馈手机通知 | `/api/tasks/feedback`, `TaskNotificationHandler.kt` | ✅ 正常 |
| 任务会话历史与反馈可见性 | `/send`, `/api/tasks/feedback` | ✅ 正常 |
| App 任务专属会话与任务编辑模式 | App + Server 任务接口 | ✅ 正常 |
| 目标项目路径分隔符统一 | 项目配置与 `/api/projects` | ✅ 正常 |
| 目标项目 Android 工程与 APK 自动识别 | `android_project.py`, `/api/projects/android/scan` | ✅ 支持根目录/一级子目录、多应用模块与多 APK 变体 |
| 目标项目 APK 安装 | `/api/adb/project-install` | ✅ 仅允许安装已配置项目扫描出的 APK，安装后按 applicationId 启动 |
| IDE Key 重命名迁移 | `ide_registry.json` 等关联状态 | ✅ 正常 |
| 桌面 IDE 扫描回归修复 | `ide_scanner.py`, `/api/desktop-ides` | ✅ 正常 |
| IDE 别名 / Key 管理 | `state/ide_aliases.json`、IDE 管理表 | ✅ 正常 |
| IDE 窗口绑定 / 自愈 | `window_binding.py`、IDE 管理页 | ✅ 用户可选择当前窗口，监控优先按持久化进程指纹匹配 |
| 上传请求前置限流 | `upload_policy.py`、`routes/phone_routes.py` | ✅ 50 MB 文件上限，请求体解析前拒绝超限请求 |
| Server 分层测试入口 | `tests/server/`、`scripts/test.ps1` | ✅ 65 个单元测试，支持 fast / standard / full |
| 独立提示词生成 API | `prompt_composer.py`、`/api/prompt/compose` | ✅ 支持 MiniMax 截图理解；图片压缩后单次调用，失败自动回退基础模板 |
| IDE 独立适配配置 | `ide_profiles.py`、`defaults/ide_profiles/` | ✅ ChatGPT / AGY 的启动、项目、历史能力按版本化配置加载，可单独检查更新 |
| OpenCode 结构化任务派发 | `opencode_client.py`、`dispatch_utils.py` | ✅ 按当前项目复用或创建会话，通过 `prompt_async` 派发并记录会话 ID |

### 2.2 Android 客户端

| 功能 | 主要文件 | 状态 |
|---|---|---|
| 设置页面 Aide 模型选择 | `SettingsScreen.kt` | ✅ 正常 |
| Aide 专屏对话功能 | `AideLinkTabScreen.kt` | ✅ 正常 |
| 桌面 IDE 选择和扫描 | `SettingsScreen.kt` | ✅ 正常 |
| Aide 显示名统一 | `strings.xml`, `MainScreen.kt`, `ChatScreen.kt`, `ChatViewModel.kt` | ✅ 正常 |
| 目标项目列表删除与服务器切换刷新 | `BridgeApi.kt`, `SettingsScreen.kt` | ✅ 正常 |
| 聊天屏幕首批组件拆分 | `ChatStatusCards.kt`, `ChatFileUtils.kt`, `ZoomableLiveMonitorDialog.kt` | ✅ 正常 |
| 聊天 bitmap 工具拆分 | `ChatBitmapUtils.kt`, `ChatViewModel.kt` | ✅ 正常 |
| 任务提示词内容解析抽离 | `ChatTaskPromptUtils.kt`, `TaskListPanel.kt`, `ChatViewModel.kt` | ✅ 正常 |
| App 端对话发送回归修复 | `ChatViewModel.kt` 等 | ✅ 正常 |
| App 端启动 IDE 与输入栏修复 | 桌面 IDE 页、输入框 | ✅ 正常 |
| 启动目标无闪切 | `ChatViewModel.kt` | ✅ 并行读取 IDE 列表与运行状态，首次渲染直接选择唯一运行 IDE |
| 任务专属会话与修改模式 | `ChatScreen.kt`, `ChatViewModel.kt` | ✅ 正常 |
| Android JVM 测试基线 | `app/src/test/` | ✅ 16 个任务解析、启动目标和 ADB 端口测试 |
| Root 无线 ADB 固定端口 | `WirelessAdbManager.kt` | ✅ Root 优先 5555，非 Root 保留系统随机 TLS 端口 |
| 监控失配友好提醒 | `ScreenMonitorPanel.kt` | ✅ 提示用户前往 Web IDE 管理重新绑定窗口 |
| 边距调整跨显示器提交保护 | `ChatViewModel.kt`, `MonitorIdentityUtils.kt` | ✅ 应用裁剪前重新校验窗口显示器，变化时阻止旧配置误写并切换确认 |
| 悬浮窗独立提示词生成 | `UiLocatorService.kt` | ✅ 自动附当前屏幕截图，MiniMax 识别组件后生成并复制到剪贴板 |
| Android 项目辅助设置页 | `SettingsScreen.kt`, `SettingsScreenContent.kt`, `BridgeApi.kt` | ✅ 目标项目识别、APK 列表、重新扫描与局域网安装 |
| 离线任务创建兜底 | `ChatViewModel.kt`, `OfflineTaskCache.kt` | ✅ 未成功创建/派发时统一保存手机本地；点击离线任务后同步并派发，失败则继续留在离线列表 |
| 项目与 IDE 功能入口收敛 | `ChatScreen.kt`、`ChatDialogs.kt` | ✅ 左上角统一切换 AideLink 当前项目；IDE 下拉只切目标，独立弹窗负责启动、关闭、项目、历史和适配功能 |
| OpenCode 统一会话入口 | `MainScreen.kt`、`SessionListScreen.kt`、`OpenCodeApi.kt` | ✅ 用户侧合并桌面/Web 身份，旧 `oc` 自动迁移；主页显示并自动刷新会话列表，输入首条消息后创建会话并进入官方 Web；兼容 OpenCode 1.17.4 的项目目录查询参数 |

### 2.3 管理面板 / Web

| 功能 | 主要文件 | 状态 |
|---|---|---|
| 模型管理页面 | `manager.py` | ✅ 正常 |
| 添加 / 编辑模型弹窗 | `manager.py` | ✅ 正常 |
| Web / Android 通用组件名称词典 | `dashboard.html`, `core.js`, `ui-dictionary.js` | ✅ 229 项，支持中英文名称和用途搜索 |
| FRP 配置模块化 | `config.js`, `frp.js`, `dashboard.html` | ✅ 正常 |
| 浏览器组件提示词侧栏 | `tools/component-locator/locator-extension/` | ✅ Ctrl+点击提取组件语义，直接生成、选择并复制提示词 |
| IDE 输入框可选校准 | `static/js/config.js`、`screenshot_engine.py`、`inject_to_ide.py` | ✅ 可按 IDE/显示器选择启用，按归一化区域在派发前点击聚焦 |
| IDE 校准流程与手机截图对齐 | `static/js/config.js`、`ide_routes.py`、Android `ChatScreen.kt` | ✅ 恢复启动/最大化/确认后截图；持久显示截图框和输入框框；手机端使用同一裁剪区域 |

---

## 3. 当前进行中的任务

### 高优先级

| ID | 任务 | 负责 | 状态 |
|---|---|---|---|
| P-AUDIT-001 | 根据最新代码重新核查 `TECH_DEBT.md` 中仍未完成的项目 | 待分配 | ⏳ 待开始 |
| P-TEST-001 | 按 `docs/developer/testing.md` 扩充任务状态、IDE Key 迁移和 API 契约测试 | 便宜 Agent / 待分配 | ⏳ 待开始 |

### 中优先级

| ID | 任务 | 负责 | 状态 |
|---|---|---|---|
| P-ANDROID-001 | 继续拆分巨型 `ChatScreen` / `ChatViewModel` | Trae / 待分配 | ⏳ 待开始 |
| P-SERVER-001 | 继续清理 `server/` 运行产物、日志、缓存和历史调试文件 | 待分配 | ⏳ 待开始 |
| P-SERVER-002 | 核查 `merge_daemon.py` 命令注入风险与 `shell=True` 使用 | 待分配 | ⏳ 待开始 |
| P-SERVER-003 | 分批为 bare `except Exception:` 增加日志或更具体异常处理 | 待分配 | ⏳ 待开始 |

### 低优先级

| ID | 任务 | 负责 | 状态 |
|---|---|---|---|
| P-DOC-002 | 建立历史归档文档或 CHANGELOG，承接旧版 `PROGRESS.md` 的长变更日志 | 待分配 | ⏳ 待开始 |

---

## 4. 当前未解决 Bug

当前没有已确认且未解决的编译阻塞 Bug。

> B3 已于 2026-07-10 通过 Android JVM 测试和 `assembleDebug` 重新验证；旧记录中的 B1 到 B13 均已关闭。

---

## 5. 当前重构计划

### 5.1 Server 端模块化

当前状态：**大部分完成**。

| 步骤 | 任务 | 状态 |
|---|---|---|
| 1.1 | 提取共享函数到 `dispatch_utils.py` | ✅ 完成 |
| 1.2 | 提取截图引擎到 `screenshot_engine.py` | ✅ 完成 |
| 1.3 | 新建 Blueprint（ui_locator / evolution / oc_web） | ✅ 完成 |
| 1.4 | 迁移 monolith 路由到 Blueprint | ✅ 完成 |
| 1.5 | 删除重复路由 | ✅ 完成 |
| 1.6 | 状态文件迁移到 `state/` | ✅ 完成 |
| 1.7 | 统一 JSON 读写使用 `json_utils` | ✅ 完成 |
| 1.8 | 消除重复代码（mascot、read_history） | ✅ 完成 |

历史记录显示：`phone_chat_bridge.py` 已从约 1829 行减少到约 256 行。

### 5.2 Android 端模块化

当前状态：**大部分完成，剩余大屏幕 / 大 ViewModel 拆分**。

| 步骤 | 任务 | 状态 |
|---|---|---|
| 2.1 | 提取 DTO 到 `domain/model/bridge/` | ✅ 完成 |
| 2.2 | 拆分 `BridgeApi` God class | ✅ 完成 |
| 2.3 | 合并 `ServerRepository` + `IdeServerRepository` | ✅ 完成 |
| 2.4 | 清理未使用依赖 | ✅ 跳过，历史记录显示依赖仍在使用 |
| 2.5 | 清理死代码 | ✅ 完成 |
| 2.6 | 拆分巨型 `ChatScreen` / `ChatViewModel` | ⏳ 待做 |

---

## 6. 技术债入口

技术债不再在本文档中展开，统一查看：

- `TECH_DEBT.md`

当前重点包括：

| 方向 | 说明 |
|---|---|
| 安全 | 重新核查 API Key、命令注入、上传路径、安全默认值 |
| 可维护性 | 清理 bare `except Exception:`、重复代码、大文件 |
| 仓库卫生 | 清理运行时文件、日志、截图、缓存、备份脚本 |
| 文档一致性 | 精简 `AGENTS.md`，确保技术债与进度不重复维护 |

---

## 7. 历史记录处理规则

旧版 `PROGRESS.md` 曾长期承担变更日志、Bug 清单、审计记录和任务列表四种职责，导致文档膨胀且状态混乱。

从 2026-07-09 开始：

- 当前状态写在本文件。
- 技术债写在 `TECH_DEBT.md`。
- AI 协作规则写在 `AGENTS.md`。
- 后续如需保留详细历史，另建 `CHANGELOG.md` 或 `docs/history/`，不要继续把长日志追加到 `PROGRESS.md`。

---

## 8. 最近更新

| 日期 | 更新 | 执行方 |
|---|---|---|
| 2026-07-09 | 将 `PROGRESS.md` 从长日志重构为当前状态文档 | ChatGPT / DevSpace |
| 2026-07-09 | 建立 `TECH_DEBT.md`，将技术债从进度文档中分离 | ChatGPT / DevSpace |
| 2026-07-09 | 验证 DevSpace 读、写、编辑、Bash、`rg` 能力 | ChatGPT / DevSpace |
| 2026-07-10 | 完成文档职责整理并关闭 P-DOC-001 | Codex |
| 2026-07-10 | 版本统一到 0.7.12（versionCode 47） | Codex |
| 2026-07-10 | 建立 fast / standard / full 测试入口，新增 10 个 Server 与 3 个 Android 测试 | Codex |
| 2026-07-10 | 上传大小限制前移到 Flask 请求解析阶段；full 测试通过 | Codex |
| 2026-07-10 | 兼容 Codex 升级后的 ChatGPT 窗口标题，并消除 OpenCode 到 Codex 的启动闪切 | Codex |
| 2026-07-10 | 修复 WRITE_SECURE_SETTINGS 抢先返回随机端口；手机恢复 Root 5555，平板保持随机端口 | Codex |
| 2026-07-10 | 完成通用 IDE 窗口绑定、自愈匹配、Web 校准和 App 失配提醒 | Codex |
| 2026-07-10 | 优化 AideLink 日志 bug 扫描：5 次门槛、增量扫描、扩展假阳性名单、拆 `/api/admin/scan_bugs`；修复 `CURRENT_TASK.md` ID 渲染；TRAE 注入改为激活后直接 `Ctrl+V` | Codex |
| 2026-07-10 | 版本升级到 0.7.13（versionCode 48） | Trae |
| 2026-07-11 | 完成独立 AI 提示词第一版：统一低额度接口、浏览器插件直接复制、Android 悬浮窗直接生成与复制 | Codex |
| 2026-07-11 | 验证 MiniMax-M3 多模态截图理解并接入 Android 悬浮窗提示词生成 | Codex |
| 2026-07-14 | Android 任务列表新增“离线任务”选项卡；该页输入框直接创建本地任务，不依赖网络状态或写入聊天记录 | Codex |
| 2026-07-14 | 取消可见失败任务状态；未成功提交的任务统一保存在手机本地，离线任务点击后尝试同步派发，成功进入进行中、失败继续留存本地 | Codex |
| 2026-07-14 | 修复任务派发后像是消失：所有派发入口成功后自动切到“进行中”；移除 App 过期项目路径的重复过滤，返回聊天页时刷新当前目标项目与任务 | Codex |
| 2026-07-14 | 修复任务卡片异步生成标题时 IDE 标签从右上角跳到中间；左侧状态/标题固定占剩余空间，IDE 标签保持尾部对齐 | Codex |
| 2026-07-14 | 统一聊天页临时提示生命周期：所有 `toastMessage` 横幅 3 秒自动消失并提供关闭按钮，移除分散延时避免旧提示误清新提示 | Codex |
| 2026-07-14 | 修复 Windows 桌面快捷方式缺失：正式安装默认勾选，一键安装完成后主动创建 | Codex |
| 2026-07-11 | 将快速安装扩展为目标 Android 项目 APK 自动发现、选择和安装；设置“工具”页改为“Android” | Codex |
| 2026-07-11 | 修复任务列表将缺少 `task_type` 的历史/新任务误判为聊天并全部过滤；恢复 49 条任务和新增后可见性 | Codex |
| 2026-07-11 | 修复边距调整期间目标窗口换屏后裁剪配置误写到旧显示器；提交前重新校验并保留调整页 | Codex |
| 2026-07-11 | 修复启动 IDE 运行态接口超时：单次进程快照替代逐 IDE 重扫，排除 OC Web，并统一唯一运行 IDE / 上次 IDE / Aide 兜底规则 | Codex |
| 2026-07-12 | IDE 管理新增唯一“主 IDE”角色；多个 IDE 同时运行时 App 优先进入运行中的主 IDE，并为后续协作编排提供稳定角色字段 | Codex |
| 2026-07-12 | AideLink MCP 新增 `ask_aide`，主 IDE 可直接调用 Aide 做分析或轻量委派；修复自动模型别名解析为伪模型 key | Codex |
| 2026-07-12 | Web 校准新增可选输入框区域标记；启用后任务派发会按客户区比例点击聚焦，未启用保持原逻辑 | Codex |
| 2026-07-12 | 修复校准流程跳过启动确认、已保存截图框不重绘及手机监控裁剪区域不对齐 | Codex |
| 2026-07-13 | 去重 TaskRuntime 超时扫描线程、共享任务状态锁；修复设置页 GlobalScope 和悬浮窗服务作用域泄漏；安装器端口参数持久化 | Codex |
| 2026-07-13 | 完成 Windows 安装包流水线：Embedded Python、锁定依赖、staging 验证、Inno Setup 编译、安装/卸载烟囱测试；托盘保证单实例 | Codex |
| 2026-07-14 | 工具箱界面清单改为 Web / Android 通用组件词典，移除对 AideLink 现有页面的依赖并增加搜索 | Codex |
| 2026-07-14 | 修复 Web 校准截图全白：补齐 Windows Graphics Capture 依赖、兼容不支持切换捕获边框的系统，并识别 PrintWindow 黑/白空图后回退 | Codex |
| 2026-07-14 | 修复全新安装自动扫描不到 IDE：加入公共默认 IDE 注册表模板，空状态首次扫描时自动初始化 | Codex |
| 2026-07-14 | Codex 桌面扫描改为识别并显示 ChatGPT 主程序，避免误选无界面的 codex.exe 后端 | Codex |
| 2026-07-14 | Web 校准 WinRT 捕获跳过窗口恢复/最大化后的空白首帧，连续空白时自动触发屏幕截图兜底 | Codex |
| 2026-07-15 | 版本升级到 0.9.14（versionCode 67） | Trae |
| 2026-07-15 | 完成当前版本 IDE 入口收敛：ChatGPT 项目/历史能力、独立 IDE 功能弹窗、OpenCode 单一目标与原生会话入口；OpenCode 任务改走正式会话 API | Codex |
| 2026-07-15 | 修复 OpenCode 原生“打开项目”被锁在用户目录：支持探测并切换 Windows 盘符、输入绝对路径，返回上级与搜索范围兼容跨盘目录 | Codex |
| 2026-07-15 | OpenCode 主界面改为会话列表；输入栏的发送动作改为“创建会话”，输入内容作为首条消息后直达官方 Web 会话，同时保留加入任务与任务列表切换 | Codex |
```

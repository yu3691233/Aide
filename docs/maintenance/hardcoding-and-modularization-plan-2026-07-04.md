# AideLink 可移植性与模块化优化计划

日期：2026-07-04

目标：让 AideLink 可以在任意用户电脑上安装运行，同时降低大文件被多 IDE 并发修改后丢功能的风险。

## 一、硬编码审计结论

### P0：必须配置化，影响用户电脑运行

1. App 默认桥接地址仍绑定维护者局域网

位置：
- `AideLink-app/app/src/main/java/cc/aidelink/app/data/repository/SettingsRepository.kt`
- `AideLink-app/app/src/main/java/cc/aidelink/app/di/NetworkModule.kt`
- `server/config.py`

现状：
- 默认值仍有 `http://192.168.3.50:5000`。
- App 已有 mDNS/NSD 自动发现，但首次启动、服务未启动、发现失败时仍会显示或尝试旧地址。

建议：
- 新增 `DefaultBridgeEndpoint` 或 `BridgeDiscoveryPolicy`，默认状态为“未配置 + 自动发现中”。
- 首次启动优先 NSD 扫描；扫描失败再提示用户输入 PC IP。
- 后端 `server_url` 默认改为空字符串或由 `get_local_ip()` 启动时生成，不写死具体 LAN IP。

2. FRP/NAS 私有配置不能作为默认配置

位置：
- `server/manager_utils.py`
- `server/frp_service.py`
- `server/static/js/config.js`
- `server/templates/dashboard.html`

现状：
- 本次已将 `manager_utils.py` 的 NAS 默认地址、用户名、密码、容器名清空。
- UI 仍保留端口、域名示例，这是可接受示例，但不能内置真实 token。

建议：
- 新增 `server/config_templates/frp.example.json`，仅放占位值。
- `config.json` 首次生成时只写空配置。
- 管理面板对空 FRP 配置显示“未配置”，不要自动启动。

3. ADB 路径不能绑定维护者 Android SDK

位置：
- `server/network_utils.py`
- `server/manager_tray.py`
- 其他直接调用 `adb` 的路由和脚本

现状：
- 本次已改为优先 `AIDELINK_ADB_PATH`，否则使用 PATH 中的 `adb`。
- 仍需统一所有 ADB 调用入口，避免某些文件绕过 `network_utils.ADB_PATH`。

建议：
- 新增 `server/adb_utils.py`，集中 `adb_path()`、`run_adb()`、`list_devices()`、`connect()`。
- 所有 `subprocess.run(["adb", ...])` 改走该模块。

### P1：应配置化，但有本地开发语义

1. 端口默认值

位置：
- Flask `5000`
- OpenCode Web `4096`
- MimoCode `4097`
- ADB classic wireless `5555`
- 已删除的旧实验集成曾使用 `3005`，不再作为当前默认端口维护

判断：
- 这些是协议或本项目默认端口，不属于坏硬编码。
- 问题是散落在多处，后续改端口容易漏。

建议：
- 后端新增 `server/defaults.py`：`DEFAULT_FLASK_PORT`、`DEFAULT_OC_WEB_PORT`、`DEFAULT_MIMO_PORT`、`DEFAULT_ADB_PORT`。
- Android 新增 `BridgeDefaults.kt`。
- 文档和 UI 从统一默认值读取。

2. 安装脚本默认设备

位置：
- `i.ps1`
- `i.bat`

现状：
- 本次已去掉维护者手机 IP 默认值。
- 脚本现在优先使用传入设备，否则取 `adb devices` 第一台在线设备。

建议：
- 后续统一为 `scripts/install-app.ps1`，支持 `-Device`、`-Build`、`-Launch`。

### P2：示例/文档硬编码，影响认知但不影响运行

位置：
- `AGENTS.md`
- `docs/**`
- `brand/README.md`
- `brand/BRIEF.md`
- Android placeholder 文案

现状：
- 本次已清理 `AGENTS.md` 中的私有 ADB 路径、设备 IP、FRP token 和旧实验集成私有域名。
- 本次已把 App 服务器地址提示改为通用示例。

建议：
- 文档分为 `user` 和 `maintainer-local`。
- 用户文档只使用 `<PC_IP>`、`<device-id>`、`<your-domain>`。
- 维护者私有拓扑放到不入仓的本地笔记。

## 二、已完成的低风险修正

- 删除 `AGENTS.md` 空 Lock List 模板项。
- `build_apk.bat` 改为基于脚本所在目录定位仓库。
- `i.ps1` / `i.bat` 去掉维护者设备 IP 默认值。
- `brand/_split.py` 改为参数化输入输出路径。
- `server/network_utils.py` 支持 `AIDELINK_ADB_PATH`。
- `server/manager_tray.py` 复用统一 ADB 路径。
- `server/manager_utils.py` 清空 NAS/FRP 私有默认值。
- App 和 PC 设置页中的固定 IP placeholder 改为通用示例。

## 三、模块化风险清单

以下文件超过 500 行，且包含多种职责，属于后续优先拆分对象。

### P0：最容易丢功能

1. `AideLink-app/.../ui/screens/chat/ChatViewModel.kt`（约 1700+ 行）

职责混杂：
- 桥接连接状态
- 截图监控
- 任务列表与批量操作
- 项目地图
- OpenCode Web 配置
- 消息发送与附件

拆分建议：
- `ChatMessageController`：消息发送、附件、重试。
- `MonitorController`：截图轮询、窗口检测、裁剪状态。
- `TaskPanelController`：任务列表、筛选、批量派发。
- `ProjectMapController`：项目地图加载、扫描、选择。
- ViewModel 只保留 UI state 聚合和事件分发。

验收：
- 拆前先补 `ChatViewModelContractTest` 或最小 JVM 单测，覆盖目标切换、任务派发、监控开关。
- 每次只迁移一个 controller，迁移后跑 `assembleDebug`。

2. `AideLink-app/.../ui/screens/chat/ChatScreen.kt`（约 1300+ 行）

职责混杂：
- 主聊天布局
- 目标 IDE 选择
- 截图监控面板
- 任务面板
- 多个 Dialog

拆分建议：
- `ChatTopBar`
- `ChatMessageList`
- `ChatInputBar`
- `MonitorPreviewPanel`
- `ChatDialogs`
- `TargetSelector`

验收：
- 拆分前截图当前关键界面，拆分后人工或截图比对。
- 不改变 ViewModel API，先纯 UI 提取。

3. `server/routes/task_routes.py`（约 1400+ 行）

职责混杂：
- CRUD
- 队列/租约
- 派发
- Worktree
- 自动 bug 检测
- 批量合并派发

拆分建议：
- `task_crud_routes.py`
- `task_dispatch_routes.py`
- `task_queue_routes.py`
- `task_worktree_routes.py`
- `task_bug_routes.py`
- `task_serializers.py`

验收：
- 路由迁移前导出当前 URL map。
- 迁移后对比 URL map，确保旧 App/Web 调用不变。

### P1：大但可以分阶段拆

1. `server/project_scanner.py`

拆分：
- 文件发现
- Android/Kotlin 解析
- Web/HTML/JS 解析
- 分类器
- 响应序列化

2. `AideLink-app/.../ui/screens/settings/SettingsScreen.kt`

拆分：
- 服务器设置
- 项目列表
- 设备管理
- IDE 设置
- 监控设置
- App 偏好

3. `AideLink-app/.../data/api/OpenCodeApi.kt`

拆分：
- Session API
- Message API
- File API
- Provider/Auth API
- Terminal/SSE API

4. `AideLink-app/.../data/api/BridgeApi.kt`

现状已经有子 API，但 facade 仍残留大量端点。

建议：
- 新代码只加到 `Bridge*Api` 子类。
- facade 每次删一组委托方法，直到只保留兼容层。

## 四、推荐执行顺序

1. 可移植性 Phase 1：统一默认值

- 新增 `server/defaults.py` 和 Android `BridgeDefaults.kt`。
- 替换散落的 `5000/4096/4097/5555`。
- 不改变行为，只集中来源。

2. 可移植性 Phase 2：首次连接策略

- App 默认服务器 URL 从固定 IP 改为“未配置”。
- 启动时进入 NSD 自动发现。
- 发现失败展示手动输入 PC IP。
- 后端 `/settings` 不再默认返回维护者 LAN IP。

3. 可移植性 Phase 3：ADB 统一入口

- 新增 `server/adb_utils.py`。
- 替换 `device_routes.py`、`manager_tray.py`、`aidelink_adb.py` 的直接 `adb` 调用。
- 保留 `AIDELINK_ADB_PATH` 和 PATH fallback。

4. 模块化 Phase 1：先拆 Android UI，不碰行为

- 先拆 `ChatScreen.kt` 组件。
- 不改 ViewModel，不改 API，不改状态。
- 目标：单文件降到 600 行以下。

5. 模块化 Phase 2：拆 ChatViewModel 控制器

- 以截图监控和任务面板为第一批。
- 每批只迁移状态和函数，不同时改 UI。

6. 模块化 Phase 3：拆后端任务路由

- 先提 serializer/helper。
- 再按 blueprint 拆路由。
- 每次迁移后对比 URL map。

## 五、必须加的保护措施

- 增加 `python -m py_compile` 和 Gradle assemble 为提交前最低验证。
- 增加 `scripts/list_routes.py`，用于模块化前后对比 Flask 路由。
- 增加 Android smoke checklist：连接、发送消息、截图监控、任务派发、项目切换。
- 对 `ChatViewModel.kt`、`task_routes.py` 这种大文件，要求每次 PR/提交只做单一职责迁移。


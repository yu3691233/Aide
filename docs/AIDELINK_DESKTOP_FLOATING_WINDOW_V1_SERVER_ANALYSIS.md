# AideLink 桌面浮窗第一版：服务端真实代码核对与最小适配方案

- 日期：2026-07-18
- 任务性质：只读代码审计与服务端方案
- 上游任务包：`docs/AIDELINK_DESKTOP_FLOATING_WINDOW_V1_SERVER_ANALYSIS_TASK.md`
- 产品输入：
  - “任务优先、快速派发、智能提示词、随记保存”的浮窗界面草图；
  - Web 项目与 Android 项目两种首页适配草图；
  - `docs/AIDELINK_DESKTOP_CAPTURE_FLOATING_WINDOW_TASKS.md`。
- 本轮结果：只新增本报告，不修改 Server、Android、插件、Web 或托盘业务代码。

## 0. 结论摘要

现有 AideLink 已经具备浮窗第一版的大部分底层能力：项目选择、桌面 IDE 注册、IDE 注入、直接消息历史、任务创建和派发、任务反馈、待测试确认、Android 项目识别、APK 安装并启动、ADB 截图、智能提示词和通用事件总线都可以复用。

第一版不需要新建第二套任务系统或模型调用中心，但不能只给现有 Web 接口套一个小窗口。服务端至少需要冻结并补齐六个薄契约：

1. 在现有项目列表上增加计算型 `capabilities`，同时支持 Web、Android、混合和通用项目；
2. 统一 IDE “已运行”和任务运行时 `idle/busy/current_task_id`，浮窗不得使用当前三套互相不一致的进程判断；
3. 为 `/send` 的显式 IDE 直发增加严格运行校验和稳定错误字段，同时保留现有会话历史；
4. 由服务端返回关键任务统计和“状态对应可用操作”，前端不自行猜测状态机；
5. 建立短期、结构化、不会自动调用模型的上下文收件箱，把浏览器组件和 Android 截图接入同一协议；
6. 增加只读薄聚合 `GET /api/floating-window/bootstrap`，提供同一时点的首页快照；后续变化复用 `/events/stream`，外部 IDE/设备存在性使用低频轮询补足。

建议实现顺序仍为“契约 → 只读首页 → 直发/快捷回复 → 任务操作 → 上下文接力 → 项目专属操作 → 窗口壳”。这并不要求等全部后端功能完成才做界面：S0 契约冻结后即可用真实 Bootstrap 数据做可点击首页壳，界面验证与后续能力实现可以交替进行。

## 1. 审计范围与代码依据

本轮实际读取或检索了以下权威实现：

| 领域 | 真实代码 |
|---|---|
| 项目与设置 | `server/config.py`、`server/routes/config_routes.py`、`server/android_project.py` |
| IDE 注册、运行与调度 | `server/routes/ide_routes.py`、`server/dispatch_utils.py`、`server/task_runtime.py` |
| 直接消息 | `server/routes/phone_routes.py`、`server/routes/task_routes_injection.py`、`server/shared_runtime.py` |
| 任务 | `server/routes/task_routes.py`、`task_routes_flow.py`、`task_routes_workflow.py`、`task_routes_management.py`、`server/task_runtime.py` |
| 智能提示词 | `server/routes/prompt_routes.py`、`server/prompt_composer.py` |
| 浏览器组件定位 | `tools/component-locator/locator-extension/content.js`、`background.js`、`sidepanel.js`、`manifest.json` |
| Android / ADB | `server/routes/device_routes.py`、`server/routes/ui_locator_routes.py`、`server/ui_locator.py`、`server/device_manager.py` |
| 事件 | `server/event_bus.py`、`server/routes/misc_routes.py`、`server/routes/project_routes.py` |
| 托盘 | `server/manager_tray.py` |
| Android 快捷回复和任务 | `SettingsRepository.kt`、`ChatViewModel.kt`、`ChatInputBar.kt`、`OfflineTaskCache.kt`、`BridgeApi.kt` |
| 测试基线 | `tests/server/test_task_runtime_transitions.py`、`test_task_list_classification.py`、`test_ide_running_status.py`、`test_android_project.py`、`test_prompt_composer.py` 等 |

`PROGRESS.md` 当前标明 Server 模块化大部分完成，直接消息不进任务、目标项目 Android 识别、APK 安装自动启动、IDE 可见窗口识别、提示词 API 和事件流均为已完成功能。`TECH_DEBT.md` 中仍有 API 鉴权、同步阻塞、状态 JSON 安全写入、子进程和大文件等待核查项，本功能不应借机扩大这些战线，但新增上下文接口必须避免放大现有鉴权和文件生命周期风险。

## 2. 当前实现清单

### 2.1 当前项目

`GET /api/projects` 位于 `server/routes/config_routes.py:278-289`。它从 Server settings 中读取同一份项目列表，并为每个项目调用 `inspect_android_project()`；当前返回的明确能力只有：

- `path`
- `name`
- `last_used`
- `android`

`POST /api/projects/select` 位于 `server/routes/config_routes.py:328-369`，会：

- 更新 `current_project` 和兼容字段 `project_dir`；
- 必要时把项目加入现有项目列表；
- 触发项目地图扫描；
- 通过 `routes.project_routes._broadcast_sse()` 广播 `project_changed`。

确认缺口：

- 没有 Web 项目检测；
- 没有 `capabilities`；
- 混合项目没有面板偏好；
- `project_changed` 只进入项目地图的独立 SSE，不进入 `event_bus.bus`；
- `GET /api/projects` 每次都会执行 Android 检测，浮窗不应高频调用。

### 2.2 IDE 配置、已运行和 busy

当前有三类数据：

1. `GET /api/desktop-ides`：返回配置、展示名、路径和 IDE profile 能力；
2. `GET /ide/processes`：使用 `dispatch_utils.get_ide_running_statuses()`，要求目标可执行文件拥有可见顶层窗口；
3. `GET /api/ide/active_status`：自己重新遍历进程，且把 OpenCode 4096 端口视为桌面 OpenCode 已运行；
4. `TaskRuntime.get_ide_status()`：返回 `idle/busy/current_task_id/lease_expires_at/error`，这是任务占用状态，不代表窗口一定存在。

`dispatch_utils.get_ide_running_statuses()`（`server/dispatch_utils.py:88-115`）是当前最可靠的桌面存在性来源。它还会排除 `opencode serve` 和 MiniMax MCP 等同名辅助进程。

`is_ide_reachable()`（`server/dispatch_utils.py:129-141`）不能用于浮窗的“正在运行”标签：对所有受支持 IDE，它即使没有检测到运行也会保守返回 `True`，让注入层最后尝试窗口匹配。

### 2.3 不创建任务的直接发送

`POST /send` 位于 `server/routes/phone_routes.py:343-506`。

已有行为：

- 接收 `text/target/image/task_id/owned_paths`；
- 用户消息先写入现有聊天历史；
- 显式目标是支持的 IDE 时，调用现有 `_inject_to_ide()`；
- 注入结果也写入历史；
- 不创建任务；
- 返回 `ok/raw/routed_to/screen_woke`。

确认缺口：

- 显式目标不会先按“可见运行窗口”严格校验；
- `target=auto` 使用 `is_ide_reachable()`，可能选择未运行 IDE；
- 空内容返回 HTTP 200，而不是稳定的 400；
- 错误字段主要在 `raw` 中，客户端难以区分 IDE 未运行、窗口未找到、权限不足和注入失败；
- `/send/stream` 的 IDE 路径仍是一次性注入，不应成为浮窗直发入口。

### 2.4 任务列表、状态和操作

`GET /api/tasks` 位于 `server/routes/task_routes.py:520-665`，支持：

- `keyword`
- `target_ide`
- 逗号分隔 `status`
- `since`
- `project`

它会映射 App/Web 兼容字段、过滤 `chat` 类型并按创建时间倒序。

现有任务状态机定义于 `server/task_runtime.py:23-66`。主要当前态为：

- `draft`
- `queued`
- `dispatched`
- `running`
- `pending_test`
- `merging`
- `done`
- `failed`
- `test_failed`
- `merge_conflict`
- `timeout`
- 兼容历史状态 `pending/completed/cancelled`

已有操作：

- 创建：`POST /api/tasks/create`
- 单条或多条注入：`POST /api/tasks/dispatch`
- 反馈：`POST /api/tasks/feedback`
- 确认通过：`POST /api/tasks/<id>/confirm`
- 失败：`POST /api/tasks/<id>/fail`
- 分配：`POST /api/tasks/<id>/assign`
- 重试：`POST /api/tasks/<id>/retry`
- 编辑：`POST /api/tasks/edit`
- 删除：`DELETE /api/tasks/<id>`

确认缺口：

- 没有专门的首页统计或首页关键任务接口；
- 没有后端输出的 `allowed_actions`；
- `project` 过滤会让所有缺少 project 的旧任务匹配任何项目，浮窗首页统计可能被旧任务污染；
- `assign` 实际只改为 `queued`，并不保证立即注入，接口注释“分配并派发”与真实行为不完全一致；
- 没有真实的百分比进度字段，界面图中的 `62%/48%` 不能由现有数据可靠生成；
- 没有单任务详情 GET；“查看”第一版可使用列表中已有字段或跳转完整任务页。

### 2.5 智能提示词

`POST /api/prompt/compose` 位于 `server/routes/prompt_routes.py:49-71`，核心逻辑位于 `server/prompt_composer.py:175-236`。

可直接复用：

- `component`
- `user_text`
- `task_type`
- Bridge 管理范围内的 `image`
- 最多三个候选提示词
- AI 失败时基础模板降级

只有实际调用 `/api/prompt/compose` 且 `user_text` 非空时才尝试模型。因此“上下文到达后不自动生成”不需要修改提示词核心，只需要确保上下文捕获接口与浮窗事件不调用 compose。

当前 `normalize_component()` 只保留十个 technical 字段且每个字段被清洗截断。长期结构化上下文不应直接塞进 compose 的 `technical`；应由上下文收件箱保存原始安全字段，生成时再映射为兼容的 `component`。

### 2.6 浏览器插件

`content.js:45-70` 当前采集：

- tag、id、className；
- 可见文本、ARIA、role、inputType；
- 组件类型和组件名；
- 页面标题、附近位置；
- XPath、CSS selector；
- bounding rect；
- 去掉查询参数后的 URL；
- 时间戳。

`background.js:16-34` 只把组件保存到 `chrome.storage.local` 并打开浏览器侧栏。`sidepanel.js:57-73` 在用户填写描述并点击后直接调用 `/api/prompt/compose`。

确认缺口：

- 没有 Bridge 上下文收件箱；
- 没有 `context.captured` 事件；
- 没有浮窗置前请求；
- 没有稳定的项目归属；
- 没有 viewport、DPI、候选选择器、附近文字和截图引用；
- 敏感判断只清空 `password/email/tel` 输入框，普通文本输入框、`contenteditable` 和周边文字仍需更严格处理。

### 2.7 Android / ADB

`GET /api/devices` 位于 `server/routes/device_routes.py:318-389`，返回别名、IP、设备 ID、型号、品牌、App 在线、ADB 在线、最近活跃等信息。

`POST /api/adb/project-install` 位于 `server/routes/device_routes.py:854-915`：

- 只接受已配置项目；
- 只安装 `inspect_android_project()` 发现的 APK；
- 默认选择 `primary_apk`，也可传已发现的 `apk_path`；
- 要求 `ip/port`；
- 安装成功后按 APK 对应 `application_id` 用 monkey 启动。

因此界面不需要单独“启动 App”按钮。

`POST /ui-locator/screenshot` 位于 `server/routes/ui_locator_routes.py:42-59`，复用无线 ADB 截图；但是：

- 截图固定覆盖 `server/screen.png`；
- 多设备时由 `ui_locator.select_best_device()` 优先匹配上报 IP，否则取第一台；
- 截图没有唯一 ID、项目关联、过期时间或并发隔离；
- `/ui-locator/screen.png` 只是当前最后一张图，不适合作为长期上下文引用。

现有“实时监控”主要是 Android App 查看 PC/IDE 截图的流程，不等价于 Windows 浮窗持续查看 Android 设备屏幕。第一版浮窗的 Android “实时监控”尚无可直接复用的完整桌面页面/API 契约。

### 2.8 快捷回复

快捷回复仅在 Android DataStore：

- key：`aidelink_quick_replies`；
- 类型：`StringSet`；
- 默认值在 `ChatViewModel.kt:2820-2828` 中临时初始化为“继续”“安装到手机”“升级版本号并提交git”；
- 当前点击快捷回复直接调用 `sendDirect()`，见 `ChatViewModel.kt:2872-2875`。

确认缺口：

- Server 不可读取；
- `StringSet` 不保证稳定顺序；
- 桌面再复制一份默认值会造成多端漂移；
- 所有模板都直接发送，缺少“先填入输入框”和“立即发送”的安全差异。

### 2.9 事件和托盘

通用事件总线位于 `server/event_bus.py`，已有：

- 进程内最多 300 条 backlog；
- 按类型订阅；
- `/events/stream`；
- `/events/recent`；
- task 和 runtime IDE 事件。

限制：

- Server 重启后事件 ID 和 backlog 清空；
- IDE 外部启动/关闭没有通用事件；
- 设备 ADB 连接/断开没有完整事件；
- 项目切换当前走项目地图独立 SSE；
- 事件应作为“数据已变化”的通知，不能替代首次 Bootstrap 真相。

托盘默认项位于 `server/manager_tray.py:650-667`，默认左键动作仍是 `show_main_window()`，后者打开 `http://127.0.0.1:5000`。`pystray` 只提供托盘菜单和默认动作，不提供浮窗容器。

## 3. 界面区域到真实数据和接口映射

| 界面区域 / 操作 | 真实来源 | 第一版判断 | 必要调整 |
|---|---|---|---|
| 标题栏项目名 | `GET /api/projects` | 直接复用 | Bootstrap 聚合当前项目；项目切换补通用事件 |
| Web/Android 标签 | 目前只有 `android.is_android` | 轻量调整 | 增加 `capabilities[]`，不使用单一 project_kind |
| 正在运行的 IDE | `/ide/processes` 最接近真相 | 轻量调整 | 统一到一份状态契约 |
| IDE 绿/黄/灰状态 | 进程运行 + TaskRuntime busy | 新增薄组合 | 返回 `presence/runtime_status/dispatchable/reason` |
| 当前派发目标 | App 本地或 Server 全局 `desktop_ide` | 需确认并调整 | 建议按项目记忆，目标失效时自动清空 |
| Web 快捷区 | 插件本地 + prompt API | 需新增接力 | Context Inbox 和事件 |
| Android 设备摘要 | `GET /api/devices` | 直接复用 | Bootstrap 只取当前设备摘要；多设备需明确选择 |
| 安装最新 APK | `/api/adb/project-install` | 直接复用 | UI 传明确设备；返回结构统一 |
| Android 截图 | `/ui-locator/screenshot` | 轻量调整 | 生成唯一快照后再作为 context |
| Android 实时监控 | 没有同义的桌面端完整能力 | 暂不直接承诺 | 第一版先跳转/打开现有监控能力，待用户确认语义 |
| 关键任务统计 | `/api/tasks` 原始列表 | 新增薄聚合 | Server 计算分组，严格当前项目 |
| 关键任务列表 | `/api/tasks?project=...` | 复用并调整 | 限量、严格项目、排除 chat/inspiration |
| 任务进度百分比 | 无 | 暂不做 | 第一版不得伪造百分比，显示状态和时间 |
| 快捷回复 | `/api/tasks/feedback` 或 `/send` | 复用 | 任务卡走 feedback；IDE 快捷回复走 `/send` |
| 查看任务 | 列表字段/完整任务页 | 复用 | 第一版打开完整页或本地详情抽屉 |
| 测试通过 | `/api/tasks/<id>/confirm` | 复用并加守卫 | 仅 pending_test 可见且 Server 再校验 |
| 反馈问题 | `/api/tasks/feedback` | 当前有状态缺口 | 修复 pending_test 反馈状态转换后使用 |
| 派发/重新派发 | `/api/tasks/dispatch`、retry | 按状态复用 | 由 `allowed_actions` 指定端点 |
| 统一输入框直发 | `/send` | 直接复用并增强契约 | 显式目标、严格运行校验、明确错误码 |
| 智能提示词 | `/api/prompt/compose` | 直接复用 | Context 映射后由用户主动调用 |
| 创建任务 | `/api/tasks/create` | 复用 | 预览确认后创建，是否立即派发由 UI 显式传入 |
| 保存随记 | `/api/tasks/inspiration` | 轻量调整 | 不能进入关键任务；补来源、项目、幂等和 context_refs |
| 关联上下文胶囊 | 当前无 Server 实体 | 新增薄接口 | Context Inbox |
| 设置 | `/settings` + 完整 Web | 部分复用 | 第一版高级配置可跳转完整 Web |
| 托盘显示/隐藏 | 当前只打开浏览器 | 后续窗口壳任务 | 保留右键完整 Web 入口 |

## 4. “直接复用 / 轻量调整 / 新增薄接口 / 暂不做”分类

### 4.1 直接复用

- `/api/projects` 和 `/api/projects/select` 作为唯一项目列表和切换入口；
- `inspect_android_project()`；
- `dispatch_utils.get_ide_running_statuses()`；
- `_inject_to_ide()`；
- `/send` 的消息历史与注入路径；
- `/api/tasks/create`；
- `/api/tasks/dispatch`；
- `/api/tasks/feedback` 的正常 running/draft/queued 路径；
- `/api/tasks/<id>/confirm`、`/fail`、`/retry` 的核心 runtime 方法；
- `/api/prompt/compose` 与 `prompt_composer`；
- `/api/devices`；
- `/api/adb/project-install`；
- `ui_locator.capture_screenshot_only()`；
- `/events/stream` 和 `/events/recent`；
- 托盘单实例、退出、完整 Web 入口等现有生命周期能力。

### 4.2 轻量调整

- 项目响应增加 `capabilities/web/preferred_surface`；
- 项目切换同时发布通用 `project.changed`；
- `/api/ide/active_status` 改为复用唯一进程快照；
- `/send` 显式目标严格运行校验和稳定错误；
- `/api/tasks` 增加严格项目模式、限量或内部聚合 helper；
- TaskRuntime/feedback 修正 pending_test 反馈状态路径；
- confirm/fail/assign 等入口增加状态守卫，避免前端误操作绕过状态机；
- `/api/tasks/inspiration` 补来源、项目、客户端幂等 ID 和上下文引用，并从关键任务中排除；
- Android 截图从覆盖型临时文件复制成唯一 Context 快照；
- Server settings 增加有序快捷回复和浮窗偏好；
- Android App 读取 Server 快捷回复并保留离线 fallback。

### 4.3 新增薄接口

- `GET /api/floating-window/bootstrap`
- Context Inbox：
  - `POST /api/contexts`
  - `GET /api/contexts?project=...&status=pending`
  - `DELETE /api/contexts/<id>` 或等价移除接口
  - Android 截图可使用 `POST /api/contexts/android-screenshot`，内部只复用现有截图函数并持久化唯一副本
- 如不希望复用通用 `/settings` 写入复杂对象，可增加极薄的：
  - `PUT /api/floating-window/preferences`
  - 但底层仍写现有 settings，不建立第二份配置文件。

### 4.4 第一版暂不做

- 伪造任务百分比进度；
- 完整 Android 设备画面实时流；
- 完整网络日志、控制台日志和 rrweb 回放；
- 根据 selector 自动定位源码；
- 自动生成提示词；
- 自动创建或派发任务；
- 完整任务历史和全部管理功能嵌入浮窗；
- 为浮窗复制一套 IDE 启停、绑定、校准后端；
- 新建独立模型服务或第二套事件总线；
- 永久保存完整 DOM、全部页面文字或无限期截图。

## 5. 项目能力识别方案

### 5.1 数据结构

继续扩展 `GET /api/projects` 的每个现有项目条目：

```json
{
  "path": "F:\\project",
  "name": "project",
  "last_used": "",
  "capabilities": ["web", "android"],
  "preferred_surface": "android",
  "android": {
    "is_android": true,
    "modules": [],
    "apks": [],
    "primary_apk": ""
  },
  "web": {
    "is_web": true,
    "roots": ["web"],
    "markers": ["web/package.json", "web/vite.config.ts"]
  }
}
```

原则：

- `capabilities` 是集合，可以同时包含 `web` 和 `android`；
- 没识别到时使用 `["general"]`；
- 不新增另一份浮窗项目列表；
- `preferred_surface` 只决定混合项目首页首先展开哪个快捷区，不删除另一个能力；
- 单能力项目自动选择对应 surface；
- 混合项目的 `preferred_surface` 建议保存到现有项目条目中，而不是全局字符串。

### 5.2 Android 检测

直接复用 `inspect_android_project()`。不要把 APK 再扫描逻辑写进 Bootstrap。

### 5.3 Web 检测

当前没有权威 Web 检测。建议增加小型、只读 `inspect_web_project()`，检查项目根和一级子目录，不递归扫描 `node_modules`：

强标记：

- `vite.config.*`
- `next.config.*`
- `nuxt.config.*`
- `angular.json`
- `svelte.config.*`
- `astro.config.*`
- `src` 配合前端入口和 `package.json`

弱标记：

- `package.json` 中的前端 framework/build tool dependency 或 script；
- `public/index.html`、根 `index.html` 配合前端资源目录。

单独存在 `package.json` 不足以证明是 Web UI，避免把纯 Node 服务误判成 Web 项目。响应可包含 `markers` 以便排查误判，但不需要对用户暴露完整探测细节。

### 5.4 性能

能力检测只在以下时机刷新：

- 添加项目；
- 选择项目；
- 用户点击重新扫描；
- Bootstrap 发现缓存缺失；
- 关键 marker 的目录 mtime 改变。

不建议浮窗每 2 秒重新跑 Android APK rglob 或 Web marker 扫描。

## 6. IDE 运行、busy 与当前派发目标统一

### 6.1 唯一状态契约

建议让 `/api/ide/active_status` 内部一次调用：

```python
running = get_ide_running_statuses(all_ides)
runtime_status = runtime.get_ide_status()
```

然后返回：

```json
{
  "key": "trae",
  "name": "Trae",
  "configured": true,
  "running": true,
  "runtime_status": "busy",
  "busy": true,
  "current_task_id": "task-...",
  "lease_expires_at": "...",
  "dispatchable": true,
  "dispatch_block_reason": null,
  "is_primary": false
}
```

定义：

- `running`：拥有符合配置的可见顶层窗口；
- `busy`：TaskRuntime 认为有正在执行任务；
- `dispatchable`：当前运行且属于可注入目标；busy 不一定禁止显式发送，但必须在 UI 明示；
- `current_task_id`：仅来自 TaskRuntime；
- `configured but not running`：灰色，可进入启动/管理，不可成为直发目标；
- `running + idle`：绿色，默认派发候选；
- `running + busy`：黄色，用户仍可显式选择，自动选择时排在 idle 后；
- 运行窗口消失但 runtime 仍 busy：返回 `dispatchable=false` 和 `runtime_presence_mismatch`，不要显示成正常忙碌。

`/ide/processes` 和旧客户端可以继续保留，但浮窗只使用上述统一契约。

### 6.2 当前派发目标

建议按项目记忆，理由：

- 不同项目常由不同 IDE 负责；
- 项目切换后沿用另一个项目的目标容易误发；
- 界面标题和快捷区本来就是项目级上下文。

建议保存：

```json
{
  "floating_window": {
    "dispatch_targets": {
      "<normalized-project-key>": "trae"
    },
    "surface_preferences": {
      "<normalized-project-key>": "android"
    }
  }
}
```

恢复顺序：

1. 该项目已记忆且仍 `running` 的目标；
2. 唯一 `running + idle` IDE；
3. 运行中的主 IDE；
4. 唯一 running IDE；
5. 否则不选择，发送按钮禁用并说明原因。

不得自动启动未运行 IDE，也不得因旧配置把“未运行”显示成可发送。

## 7. 直接派发复用方案

浮窗继续调用 `POST /send`，不新增 `/floating-window/send`。

请求必须显式传：

```json
{
  "text": "把这个按钮再缩小一点",
  "target": "trae",
  "task_id": null,
  "image": null
}
```

第一版不从浮窗使用 `target=auto`。Server 在写入/注入前应完成：

1. 文本非空和长度限制；
2. 目标存在且是支持的桌面 IDE；
3. 用统一 running 语义确认可见窗口；
4. 若 busy，仍允许用户显式直发，但响应返回 busy/current_task_id；
5. 调用原有 `_inject_to_ide()`；
6. 保留原有用户消息和注入结果历史。

建议稳定响应：

```json
{
  "ok": false,
  "code": "ide_not_running",
  "message": "Trae 未运行或未找到可见窗口",
  "routed_to": "trae",
  "history_saved": true,
  "busy": false,
  "current_task_id": null
}
```

建议错误码：

- `empty_text`
- `unknown_target`
- `ide_not_running`
- `ide_not_bound`
- `ide_permission_required`
- `ide_busy`
- `inject_failed`
- `service_unavailable`（客户端本地使用）

是否把失败尝试写入历史应保持现有兼容行为：用户内容和明确失败结果都记录；但不能把目标从 `auto` 静默改成另一个 IDE。

界面草图中的“追加到当前对话 / 新建对话”目前不是所有 IDE 都有统一会话 API。第一版建议：

- 通用桌面 IDE：仅支持现有注入语义，文案使用“发送到当前 IDE”；
- OpenCode 等具备正式会话 API 的目标可以后续单独展示会话选择；
- 不在通用确认页承诺所有 IDE 都能结构化创建新会话。

## 8. 任务首页统计、关键任务和操作矩阵

### 8.1 首页分组

Bootstrap 应返回原始状态计数和 UI 分组，避免前端复制规则：

```json
{
  "task_summary": {
    "needs_attention": 2,
    "pending_test": 1,
    "active": 2,
    "unassigned": 1,
    "raw": {
      "running": 1,
      "queued": 1,
      "pending_test": 1,
      "failed": 1,
      "draft": 1
    }
  }
}
```

推荐映射：

- `needs_attention`：`failed/timeout/test_failed/merge_conflict`
- `pending_test`：`pending_test`
- `active`：`running/dispatched/queued/merging`
- `unassigned`：`draft/pending`
- `done/completed/cancelled`：不进入首页四个主统计

`queued` 不等于正在执行，因此卡片必须显示“排队中”；若界面按钮仍写“执行中”，统计 tooltip 应解释其包含排队。更准确的 UI 文案建议是“进行中”。

关键任务排序：

1. `needs_attention`
2. `pending_test`
3. `running/dispatched`
4. `queued`
5. `draft/pending`
6. 最近更新时间倒序

建议第一版返回 5 条，界面紧凑时显示 3 条并保留“查看全部”。数量可由用户最终确认。

严格项目规则：

- 首页只统计 `task.project` 与当前项目规范化后相等的任务；
- 缺少 project 的历史任务不应自动计入每个项目；
- 完整任务页保留现有兼容行为；
- 可给 `/api/tasks` 增加不破坏旧客户端的 `strict_project=1`，或只在 Bootstrap 内严格过滤。

必须排除：

- `task_type=chat`
- `metadata.content_kind=inspiration`

### 8.2 状态到操作矩阵

建议 Bootstrap 每条任务返回 `allowed_actions`，值由 Server helper 产生：

| 状态 | 主操作 | 次要操作 | 当前接口与注意事项 |
|---|---|---|---|
| `draft/pending` | 派发 | 编辑、查看、删除 | 单条可用 `/api/tasks/dispatch`；`assign` 只保证 queued |
| `queued` | 查看/取消排队 | 改派、反馈 | 当前缺显式取消队列接口；第一版可放“更多”并暂不提供取消 |
| `dispatched/running` | 快捷回复/反馈 | 查看、标记失败 | `/api/tasks/feedback` 会沿同任务重新注入 |
| `pending_test` | 测试通过 | 反馈问题、查看 | confirm 可复用；反馈问题当前有状态缺口，修复后开放 |
| `merging` | 查看 | 无破坏性操作 | 等待自动流程，不显示通过/重新派发 |
| `failed/timeout` | 重试 | 查看、记录反馈 | retry 限 3 次；若要修改反馈后重试需补协议 |
| `test_failed/merge_conflict` | 查看处理 | 重新验证/重试 | 应按现有合并流程决定，不与普通 failed 混用 |
| `done/completed` | 查看 | 创建后续/记录反馈 | 当前 feedback 只记录，不自动重开 |
| `cancelled` | 查看 | 删除 | 不自动重新派发 |

### 8.3 已确认的 pending_test 缺口

当前 `/api/tasks/feedback` 对除 `done/failed` 外的任务会：

1. 先向 IDE 注入反馈；
2. 再调用 `runtime.mark_task_running()`。

但 `_ALLOWED_TRANSITIONS` 不允许 `pending_test → running`。这意味着用户在待测试任务上点击“反馈问题”时，可能已经把内容注入 IDE，随后 Server 才抛非法状态转换，形成“实际已发送但 UI 显示失败”的危险状态。

S3 必须先修正再开放该按钮。建议复用现有状态而不是新建状态机：

- pending_test 收到问题反馈时先进入 `test_failed`；
- 成功重新注入后进入允许的执行态；
- 为现有状态机补明确、受测试保护的 `test_failed → running`；
- 注入失败时保留 `test_failed` 和错误，不伪装为正在执行；
- 旧 `result_ref` 保留为上一轮证据，不能覆盖为新一轮结果。

同时建议在 `confirm_task_done()` 内验证来源状态。当前实现使用 `_skip_status_check=True`，路由虽然文案写“pending_test → done”，但方法本身没有检查旧状态，浮窗不能只靠隐藏按钮保证安全。

### 8.4 进度百分比

现有任务实体没有进度百分比，也没有可稳定换算的阶段总数。第一版任务卡应显示：

- 精确状态；
- IDE；
- 更新时间/开始时间；
- 可选 result/summary 摘要。

不要从运行时长、日志数量或截图变化伪造百分比。以后若 Agent 主动回报结构化 progress，再单独设计字段和更新协议。

## 9. 快捷回复数据源和多端兼容

### 9.1 建议权威源

Server settings 成为联网状态下的权威源，使用有序列表而不是集合：

```json
{
  "quick_replies": [
    {
      "id": "continue",
      "label": "继续",
      "text": "继续",
      "behavior": "fill"
    }
  ]
}
```

`behavior`：

- `fill`：填入统一输入框，由用户补充或再次确认；
- `send`：允许立即发送，但必须在管理界面明确设置。

默认建议全部为 `fill`。尤其“安装到手机”“升级版本号并提交git”包含外部动作，不应在桌面端第一次点击菜单项就直接发送。用户可以把“继续”显式改成 `send`。

### 9.2 Android 迁移

兼容步骤：

1. App 离线时继续读本地 DataStore；
2. Server 没有初始化 quick replies 时，App 第一次同步可上传其现有本地列表；
3. Server 已初始化时，以 Server 顺序列表为准并回写本地缓存；
4. 旧 `StringSet` 只作为一次性迁移来源；
5. 新 App 版本本地改用有序序列化结构；
6. 老 App 不认识新字段时仍保持自己的本地行为，不阻塞连接。

不要在浮窗代码里再硬编码同一组三条默认值。

## 10. Web / Android 上下文接力协议

### 10.1 第一版定位

Context Inbox 是“短期结构化收件箱”，不是任务、随记或聊天历史。上下文到达只做三件事：

1. 保存安全的结构化引用；
2. 发布 `context.captured`；
3. 请求浮窗提示/置前。

它不得：

- 调用 `/api/prompt/compose`；
- 创建任务；
- 创建随记；
- 直接派发 IDE。

### 10.2 最小结构

```json
{
  "id": "ctx-20260718-...",
  "project": "F:\\project",
  "source": "browser_plugin",
  "type": "web_component",
  "label": "通知方式下拉框",
  "payload": {
    "page_title": "用户设置",
    "page_url": "https://example.test/settings",
    "component_type": "select",
    "role": "combobox",
    "visible_text": "邮件通知",
    "accessible_name": "通知方式",
    "nearby_text": "通知设置",
    "stable_attributes": {
      "id": "",
      "name": "",
      "data_testid": "",
      "aria_label": "通知方式"
    },
    "selector_candidates": [],
    "dom_path_summary": "",
    "bounding_rect": {},
    "viewport": {}
  },
  "screenshot_ref": null,
  "status": "pending",
  "created_at": "...",
  "expires_at": "..."
}
```

### 10.3 存储与生命周期

第一版建议使用现有 Server state 目录中的小型安全 JSON 存储，不只放内存，避免 Server 重启后组件瞬间丢失：

- 元数据默认 24 小时过期；
- pending 上下文最多保留 50 条；
- 截图默认 24 小时清理；
- 用户把 context 附到随记或任务后，保存其引用或复制到正式受管位置；
- 浮窗移除只改变 inbox，不应删除已经附到正式记录的证据；
- 不保存完整 DOM。

### 10.4 浏览器插件接力

插件捕获后：

1. 继续保存 `chrome.storage.local`，作为 Bridge 不在线时的本地 fallback；
2. 尝试 `POST /api/contexts`；
3. Server 校验来源、大小、字段白名单和项目；
4. 未能可靠确定项目时标记 `project=null`，由浮窗确认，禁止默认为错误项目；
5. Server 发布 `context.captured`；
6. 窗口壳收到事件后按用户设置执行“置前”或“任务栏闪烁”；
7. 打开智能提示词页面，但不生成。

安全注意：

- 插件当前有 `<all_urls>` 和 localhost host permission；
- `/api/prompt/compose` 当前 CORS 是 `*`；
- 新 Context 写接口不能因为运行在 localhost 就完全信任任意网页；
- 最小方案可限制本机请求、校验扩展 Origin/一次性本地 token，并限制 payload 大小；
- 不采集任何输入控件当前 value；
- `contenteditable`、普通文本输入框和疑似敏感附近文本也需要清洗。

### 10.5 Android 截图接力

Android 截图进入同一 Context 结构：

```json
{
  "source": "desktop_float",
  "type": "android_screenshot",
  "label": "Redmi Pad 当前屏幕",
  "payload": {
    "device_id": "...",
    "device_alias": "Redmi Pad",
    "width": 1600,
    "height": 2560
  },
  "screenshot_ref": "captures/ctx-...jpg"
}
```

服务端必须把当前 `screen.png` 复制/转换成唯一受管文件后再返回 context ID，避免下一次截图覆盖已关联证据。

### 10.6 映射到智能提示词

浮窗在用户主动点击“生成智能提示词”时：

1. 读取所选 context；
2. 映射为现有 `/api/prompt/compose` 的兼容 `component`；
3. 把唯一受管截图引用传入 `image`；
4. 传用户补充的 `user_text`；
5. 进入现有候选预览。

Context 原始安全 payload 继续独立保存，compose 的精简 component 只是一次生成输入，不能反向覆盖原引用。

## 11. Android 当前设备与项目专属操作

### 11.1 当前设备选择

`GET /api/devices` 当前没有可靠的“桌面浮窗当前设备”持久字段，`is_active` 实际只是 App 在最近窗口内在线。

建议设备选择顺序：

1. 该项目/浮窗显式记忆且仍在线或 ADB 已连接的设备；
2. 唯一 ADB 已连接设备；
3. 唯一 App 在线设备；
4. 多台设备时要求用户选择；
5. 不允许静默选择列表第一项执行安装。

保存稳定标识优先级：alias/serial，其次最后 IP；不要只持久化会变化的局域网 IP。

### 11.2 安装 APK

浮窗调用现有 `/api/adb/project-install`：

```json
{
  "project_path": "F:\\project",
  "apk_path": "",
  "ip": "device-current-ip",
  "port": 5555
}
```

空 `apk_path` 使用当前扫描出的 `primary_apk`。成功响应已经有 `device/apk_path/application_id/output`。UI 应显示：

- 使用的 APK 变体；
- 目标设备；
- 安装是否成功；
- applicationId 是否成功识别并尝试启动。

当前响应只表明 monkey 命令被调用，没有单独返回 App 启动是否成功；第一版若要显示“已自动启动”，应把启动子进程 return code/output 纳入结果，而不是无条件显示成功。

### 11.3 截图

复用 ADB 截图函数，但通过 Context 接口生成唯一快照。UI “截图”成功后把 context 胶囊加入统一输入区，不自动生成、不自动发送。

### 11.4 实时监控

需要用户确认“实时监控”的对象：

- 若指 PC 上 IDE 的现有截图监控：可跳转/打开现有监控页，第一版不新增 Android 专属流；
- 若指 Android 设备屏幕连续预览：现有服务端只有单次 ADB screenshot，不足以直接承诺实时流。

建议第一版按钮先命名为“打开监控”并复用已有 PC/IDE 监控入口；Android 设备实时流作为后续独立任务评估性能、ADB 带宽、前后台和截图文件并发。

## 12. 事件、刷新与 Bootstrap

### 12.1 需要 Bootstrap

建议新增 `GET /api/floating-window/bootstrap`，理由：

- 首页同时需要项目、能力、IDE presence、runtime busy、当前派发目标、任务统计、关键任务、设备摘要、快捷回复和 pending context；
- 如果客户端分别请求 6～8 个接口，项目可能在请求中途切换，形成标题、任务和快捷区不一致；
- Android 项目扫描和 IDE 进程扫描不应被多个组件重复触发；
- Bootstrap 可以只组合现有 helper，不复制业务规则。

示意：

```json
{
  "ok": true,
  "schema_version": 1,
  "generated_at": "...",
  "project": {},
  "ides": [],
  "selected_target": null,
  "task_summary": {},
  "tasks": [],
  "device": null,
  "quick_replies": [],
  "contexts": [],
  "warnings": []
}
```

Bootstrap 是只读聚合层：

- 项目来源仍是 settings/projects；
- IDE presence 来源仍是 dispatch_utils；
- busy 来源仍是 TaskRuntime；
- 任务来源仍是 TaskRuntime；
- 设备来源仍是 device helper；
- 不另存首页副本；
- 不新增状态机。

可支持 `sections=project,ides,tasks`，但第一版不是必须。

### 12.2 事件策略

复用 `/events/stream`，新增或补齐：

- `project.changed`
- `context.captured`
- `context.removed`
- `settings.quick_replies_changed`
- 可选 `floating_window.focus_requested`

继续复用：

- `task.created`
- `task.queued`
- `task.assigned`
- `task.running`
- `task.pending_test`
- `task.done`
- `task.failed`
- `task.feedback`
- `ide.idle`
- `ide.busy`
- `ide.heartbeat`

事件只作为失效通知。客户端收到任务事件后刷新 task section；收到项目变化后重新请求完整 Bootstrap；收到 context 时读取 context inbox。

### 12.3 轮询补足

外部 IDE 启停和 ADB 断连不一定经过 AideLink，所以纯事件不足。

建议：

- 浮窗可见：IDE/设备 presence 每 5～10 秒刷新；
- 浮窗隐藏：每 30 秒或暂停，显示时立即刷新；
- 任务状态主要靠事件，断流时 15～30 秒兜底；
- SSE 重连后先请求 `/events/recent`；若 Server 已重启或 ID 无法衔接，直接重新 Bootstrap；
- 不高频调用完整 `/api/projects` 和 Android APK 扫描。

## 13. 建议修改文件范围

以下是后续实现建议，不是本轮改动。

### S0：服务端契约冻结

建议修改：

- `server/config.py`
- `server/routes/config_routes.py`
- `server/android_project.py`（只复用，不建议混入 Web 判断）
- 新增小型 `server/project_capabilities.py`
- `server/routes/ide_routes.py`
- `server/dispatch_utils.py`（优先复用；如需只增加组合 helper）
- `server/task_runtime.py`
- `server/routes/task_routes.py`
- `server/routes/task_routes_flow.py`
- `server/routes/task_routes_workflow.py`
- 新增 `server/routes/floating_window_routes.py`
- `server/routes/__init__.py`

建议测试：

- `tests/server/test_project_capabilities.py`
- 扩展 `test_ide_running_status.py`
- 扩展 `test_task_runtime_transitions.py`
- 新增 `test_floating_window_bootstrap.py`
- 新增 `test_task_allowed_actions.py`

### S1：只读首页

建议修改：

- `server/routes/floating_window_routes.py`
- 必要的前端浮窗静态资源（由窗口/UI任务决定）

测试：

- Web/Android/混合/通用项目 Bootstrap；
- 严格项目任务过滤；
- 旧无 project 任务不污染首页；
- IDE presence 与 busy 组合；
- Server 无设备/无 IDE/无任务空状态；
- 任务百分比字段不存在时 UI 不展示假进度。

### S2：直接派发与快捷回复

建议修改：

- `server/routes/phone_routes.py`
- `server/config.py`
- `server/routes/config_routes.py` 或浮窗 preferences 薄路由
- Android `SettingsRepository.kt`
- Android settings DTO/API 映射
- `ChatViewModel.kt`

测试：

- 显式目标运行/未运行/窗口缺失/权限不足；
- busy IDE 显式发送；
- 不创建任务；
- 成功和失败历史；
- 快捷回复顺序、fill/send 行为；
- Server 未初始化时的 Android 一次迁移；
- 老 App 兼容。

### S3：任务快捷操作

建议修改：

- `server/task_runtime.py`
- `server/routes/task_routes.py`
- `server/routes/task_routes_flow.py`
- `server/routes/task_routes_workflow.py`
- Bootstrap `allowed_actions` helper

测试：

- 每个状态的动作矩阵；
- pending_test 测试通过；
- pending_test 反馈问题不会出现“已注入但接口失败”；
- confirm 不能从非法状态直接 done；
- fail/retry/assign 非法状态返回 409 而不是 500；
- retry 上限；
- feedback 保持同一任务历史；
- inspiration 不出现在关键任务。

### S4：上下文接力

建议修改：

- 新增 `server/routes/context_routes.py`，或把很薄的实现放入 `floating_window_routes.py`
- 新增 `server/context_store.py`
- `server/routes/__init__.py`
- `server/routes/ui_locator_routes.py`
- `server/ui_locator.py`
- `tools/component-locator/locator-extension/content.js`
- `background.js`
- `sidepanel.js`
- 必要时 `manifest.json`

测试：

- 捕获不调用模型、不创建任务、不派发；
- Bridge 离线时插件本地 fallback；
- 项目未知时不误关联；
- TTL、容量、删除和重启恢复；
- 唯一 Android 截图不会被下一次覆盖；
- 大字段、恶意 selector、超长文本和敏感输入清洗；
- iframe/Shadow DOM 明确降级；
- `context.captured` 事件。

### S5：项目专属操作

建议修改：

- `server/routes/device_routes.py`
- Bootstrap device summary
- 浮窗 Web/Android 快捷区

测试：

- 多设备不静默选错；
- APK 不在扫描清单内时拒绝；
- 没有 APK、ADB 断开、连接超时；
- 安装成功但 applicationId 缺失；
- App 启动命令失败的独立结果；
- 混合项目 surface 切换和记忆。

### S6：桌面窗口壳

建议修改范围由 UI/窗口技术方案单独冻结，至少包括：

- `server/manager_tray.py`
- 新增单实例浮窗外壳入口；
- 浮窗 UI 静态资源；
- 安装包/依赖文件（仅在选定技术方案确有需要时）。

服务端只需保证：

- Bootstrap；
- SSE；
- `floating_window.focus_requested` 或本地 IPC 信号；
- 服务不可用时窗口壳能显示错误而不是静默退出。

窗口壳测试：

- 托盘左键显示/隐藏；
- 右键仍可打开完整 Web 和退出；
- 单实例；
- 置顶、隐藏、关闭不退出服务；
- 多显示器和 DPI；
- 服务重启后重连。

## 14. 兼容性、隐私与失败恢复风险

### 14.1 兼容性

- 不改变 `/api/projects`、`/api/tasks`、`/send` 现有字段，只增字段或可选严格模式；
- 旧 App 不认识 `capabilities/allowed_actions` 时可忽略；
- 旧 `/api/ide/active_status` 的 key/name/running/status/current_task_id 保留；
- `/api/prompt/compose` 输入格式保持兼容；
- 旧插件仍可只使用 sidepanel；
- 快捷回复迁移必须支持 Server 不在线时的 Android 本地 fallback；
- 不更改完整 Web 任务页的历史项目兼容筛选。

### 14.2 隐私

- 浏览器插件不采集 input/textarea/contenteditable 的当前值；
- URL 默认只保存 origin + pathname；
- 页面文字、ARIA 和附近文字设置长度上限并清洗；
- Context API 严格字段白名单；
- 不保存完整 DOM；
- 截图唯一化后必须有 TTL 和归属；
- prompt 只接收用户主动选中的 context；
- 不把截图或敏感 context 自动送入模型；
- 不在报告、代码或默认配置中写私有 IP、token 或用户路径。

### 14.3 失败恢复

| 失败 | 第一版降级 |
|---|---|
| Bridge 不在线 | 浮窗显示离线；输入暂存窗口本地草稿；插件保留 chrome.storage |
| IDE 消失 | 清空不可用目标，保留输入，返回 `ide_not_running` |
| IDE 注入失败 | 明确错误，消息历史记录失败结果，不创建任务 |
| SSE 断开 | 指数退避重连；重连后 recent 或完整 Bootstrap |
| Server 重启 | Context 元数据从 state 恢复；过期项清理 |
| 设备断开 | 禁用安装/截图，保留所选设备标识并提示重连 |
| APK 不存在 | 返回重新扫描/先编译提示，不回退到仓库外文件 |
| Prompt AI 失败 | 继续使用现有基础模板并明确 `used_ai=false` |
| Context 过期 | 胶囊显示已过期，可移除；不自动换成另一张截图 |
| 项目切换 | 清空未确认的错误项目 context 关联，重新 Bootstrap |
| pending_test 反馈注入失败 | 保持 test_failed 和原证据，不能显示 running |

浮窗本地草稿属于窗口壳职责，但必须定义：只有 `/send`、创建任务或保存随记明确成功后才清空输入；网络请求发出不等于成功。

## 15. 建议拆给不同 IDE 的后续任务

### 任务 A：S0 项目能力与 Bootstrap

- 范围：Server Python + Server tests；
- 产出：capabilities、统一 IDE 状态、strict task summary、Bootstrap；
- 不做：窗口 UI、插件、Android；
- 适合：熟悉 Flask 和状态契约的 IDE。

### 任务 B：S2 直发错误契约与快捷回复

- 范围：`phone_routes.py`、Server settings、Android settings 同步；
- 产出：显式 IDE 运行校验、错误码、有序快捷回复；
- 不做：任务状态机和 Context；
- 适合：跨 Server/Android 的 IDE，文件范围需与 Android 大文件重构错开。

### 任务 C：S3 任务动作矩阵

- 范围：TaskRuntime、task routes、tests；
- 产出：`allowed_actions`、pending_test 反馈修复、非法状态守卫；
- 不做：首页视觉；
- 建议由 Codex 或熟悉现有任务闭环的 IDE完成并独立审查。

### 任务 D：S4 浏览器 Context 接力

- 范围：Context store/routes + Chrome extension；
- 产出：结构化组件、短期收件箱、事件、离线 fallback；
- 不做：自动 Prompt、任务创建、源码定位；
- 适合：前端/浏览器扩展能力较强的 IDE。

### 任务 E：S5 Android 快捷区

- 范围：device routes 结果完善 + 浮窗快捷区；
- 产出：设备选择、APK 安装结果、唯一截图 context；
- 不做：Android 设备实时视频流；
- 适合：熟悉 ADB 的 IDE。

### 任务 F：S6 浮窗壳和首页 UI

- 范围：桌面窗口、托盘、浮窗 UI；
- 输入：已经冻结的 Bootstrap/事件/操作契约；
- 产出：可真实点击的首页、Web/Android/混合布局；
- 不做：复制完整 Web 管理页；
- 可以在 S1 完成后先做真实数据 UI，再与 S2～S5 交替迭代。

## 16. 仍需用户确认的问题

以下问题会改变第一版行为，需要在对应阶段开始前确认：

1. 混合项目默认首先展开 Web 还是 Android；本报告建议记忆每个项目最后选择。
2. 当前派发目标是否按项目记忆；本报告建议“按项目”。
3. 快捷回复是否 App/桌面统一；本报告建议 Server 权威、App 离线缓存。
4. 快捷回复点击默认填入还是立即发送；本报告建议默认填入，单条可显式配置立即发送。
5. 浏览器捕获后窗口行为：强制置前、任务栏闪烁或只显示角标；建议默认闪烁/提示，用户可开启强制置前。
6. Context 过期时间；本报告建议 pending 元数据和截图第一版均为 24 小时。
7. Android “实时监控”究竟指 PC/IDE 画面还是 Android 设备画面；两者现有能力不同。
8. 首页关键任务显示 3 条还是 5 条；本报告建议 Server 返回 5 条，UI 视高度展示 3～5 条。
9. `queued` 是否计入界面“执行中”；本报告建议统计归入 active，但卡片明确显示排队中，主标签改为“进行中”更准确。
10. 待测试“反馈问题”是否沿同一任务重新执行；本报告建议沿同一任务保存反馈并开始新一轮执行，不创建新任务。
11. 保存随记第一版是否继续底层复用 `metadata.content_kind=inspiration`；本报告建议先兼容复用，但从关键任务中排除并补幂等/context 字段，后续按上游开发随记任务升级。
12. 浮窗壳技术方案；服务端分析只要求单实例、Web UI 复用、服务离线可显示状态和本地草稿，不在本轮指定 WebView/pywebview/原生技术。

## 17. 最终推荐

第一版应增加薄 Bootstrap 和 Context Inbox，但不增加平行后端。先完成 S0 后立即做一个接真实数据的首页壳，随后按界面使用反馈迭代 S2～S5；这样既保留“看到界面才能判断功能”的产品验证方式，又避免 UI 先绑定到不稳定或错误的状态语义。

开始 UI 前唯一必须先修正的服务端高风险点是：

1. IDE running 唯一语义；
2. pending_test 反馈状态转换；
3. 严格当前项目任务统计；
4. 不展示伪造任务百分比；
5. Android 截图唯一化后才能作为上下文；
6. 捕获 context 与调用模型彻底分离。

完成这六项契约后，界面图中的主要交互都可以逐步落到现有 AideLink 能力上，而不需要重做任务系统。

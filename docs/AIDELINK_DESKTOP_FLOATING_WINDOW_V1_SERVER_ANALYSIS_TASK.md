# AideLink 桌面浮窗第一版：服务端适配分析任务包

- 状态：可交给 Codex 执行
- 日期：2026-07-18
- 当前阶段：只读分析 + 输出方案
- 本轮禁止：直接修改业务代码、实现完整浮窗、提交 Git
- 上游产品文档：`docs/AIDELINK_DESKTOP_CAPTURE_FLOATING_WINDOW_TASKS.md`
- 分析结果建议写入：`docs/AIDELINK_DESKTOP_FLOATING_WINDOW_V1_SERVER_ANALYSIS.md`

## 1. 任务目标

基于已经确认的浮窗第一版界面布局，核对 AideLink 现有 Web、Android App、浏览器插件、任务系统、IDE 调度、ADB 和托盘实现，分析服务端为了支持浮窗需要做哪些最小调整。

本轮不是重新设计一套桌面系统，也不是立即实现浮窗 UI，而是回答以下问题：

1. 界面上的每一块数据和操作，现有服务端是否已经支持；
2. 已有接口能否直接复用，还是需要轻量调整；
3. 哪些能力目前只存在于 Android App 本地，浮窗无法复用；
4. 浏览器插件和 Android 上下文怎样进入浮窗，而不自动调用模型或派发；
5. 如何根据当前项目能力动态显示 Web、Android 或通用快捷操作；
6. 是否需要薄聚合接口或事件补充，避免浮窗同时请求过多接口和状态互相打架；
7. 最小实现应分成哪些阶段，分别修改哪些文件。

## 2. 已确认的产品决定

以下结论视为本任务的固定输入，不再重新讨论方向。

### 2.1 浮窗定位

1. 浮窗是 AideLink 现有核心能力的桌面快捷入口，不是缩小版完整 Web 管理页。
2. 第一版优先复用现有 Web 和 App 功能，不新增平行后端、平行任务系统或第二套状态机。
3. 首页以任务状态、关键任务列表、IDE 快速派发和统一输入框为核心。
4. 用户应能在 1 到 2 步内完成高频操作。

### 2.2 标题栏

1. 标题栏直接显示当前项目名称，不显示“AideLink 浮窗”等固定标题。
2. 不提供最大化按钮。
3. 第一版标题栏只保留：
   - 置顶；
   - 隐藏；
   - 设置。
4. 项目切换后标题栏应立即刷新。

### 2.3 IDE 与直接派发

1. 首页显示当前正在运行的 IDE。
2. 用户可点击 IDE 标签切换当前派发目标。
3. 输入框内容可以不创建任务，直接派发到目标 IDE。
4. 发送按钮必须明确显示目标，例如“发送到 Trae”。
5. 直接派发沿用手机端现有行为，不进入任务列表，但应保留现有会话历史。
6. 不自动向未运行的 IDE 派发；无法派发时必须明确返回原因。

### 2.4 任务区

1. 首页优先显示当前项目的关键任务，而非完整历史。
2. 优先级建议为：
   - 需要用户处理；
   - 待测试；
   - 正在执行；
   - 未派发；
   - 最近完成可放到次级入口。
3. 任务卡片支持与状态相关的快捷操作，例如：
   - 快捷回复 / 补充反馈；
   - 查看；
   - 测试通过；
   - 反馈问题或测试失败；
   - 派发 / 重新派发；
   - 更多操作。
4. 任务卡片不能把所有按钮永久铺开，应由状态决定主按钮，其余放入菜单。

### 2.5 统一输入框

同一个输入框支持四条路径：

1. 直接发送到当前 IDE，不创建任务；
2. 智能提示词，进入预览后再发送或创建任务；
3. 创建任务，确认后进入现有任务系统；
4. 保存随记，只保存原文，不派发。

快捷回复作为输入区和任务卡片都可使用的现有能力保留。

### 2.6 项目能力适配

浮窗不固定显示 Web 和 Android 的全部操作，而是根据当前项目动态显示。

#### Web 项目

可显示：

- 浏览器插件连接或捕获状态；
- 已捕获 Web 组件；
- 页面截图或页面上下文；
- 打开或引导组件定位；
- 进入智能提示词。

不显示 Android 设备、APK、ADB 操作。

#### Android 项目

优先显示真正需要 PC / ADB 辅助的能力：

- 设备连接状态；
- 安装当前项目最新或已选 APK，并自动启动 App；
- 截图；
- 实时监控；
- “更多 ADB”入口。

不单独显示“启动 App”按钮，因为正常安装流程已经自动启动，用户在设备上手动启动也很方便。

#### 通用或混合项目

本轮必须分析：

- 项目仅为 Web；
- 项目仅为 Android；
- 同一仓库同时包含 Web 和 Android；
- 无法识别的通用项目。

不要假设所有项目只能拥有一个类型。优先考虑“能力集合”而不是脆弱的单一字符串分类；是否需要为混合项目记住当前开发面板，由分析结果提出最小方案。

### 2.7 浏览器插件和上下文

1. 浏览器插件捕获组件后，浮窗可以置前并进入智能提示词界面。
2. 捕获到上下文时不得自动调用模型。
3. 不得自动创建任务或派发。
4. 用户可补充一句修改要求，再主动点击生成提示词或直接发送。
5. Web 组件、Android 截图、页面截图等统一视为“关联上下文”，不为每个平台建立完全不同的工作流。

## 3. 第一版界面信息层级

### 3.1 始终可见

- 当前项目名，位于标题栏；
- 置顶、隐藏、设置；
- 正在运行的 IDE；
- 当前派发目标；
- 当前项目关键任务状态统计；
- 当前项目关键任务列表；
- 统一输入框；
- 发送到目标 IDE；
- 快捷回复；
- 智能提示词；
- 创建任务；
- 保存随记。

### 3.2 根据项目能力显示

- Web 组件、页面截图、浏览器插件相关入口；
- Android 设备状态、安装 APK、截图、实时监控、更多 ADB。

### 3.3 条件显示

- 已关联的 Web 组件；
- Android 当前截图；
- 页面截图；
- 当前关联任务；
- IDE 忙碌状态；
- 派发失败原因；
- APK 安装结果。

### 3.4 点击后再显示

- 完整任务列表；
- 已完成历史；
- IDE 启停、绑定、校准等管理功能；
- 完整组件技术信息；
- APK 全部变体；
- 完整 ADB 工具；
- 随记列表；
- 高级任务转换选项。

## 4. 最小用户流程

### 4.1 直接派发

```text
选择运行中的 IDE
→ 输入内容
→ 点击“发送到 IDE”
→ 不创建任务，直接注入当前 IDE
```

只有一个可用 IDE 时可默认选中，但发送按钮仍显示目标名称。

### 4.2 快捷回复

```text
选择任务或当前 IDE
→ 点击快捷回复
→ 选中模板填入输入框或直接发送
```

需要分析哪些回复适合直接发送，哪些应先填入输入框让用户补充。

### 4.3 手动智能提示词

```text
输入内容
→ 点击智能提示词
→ 用户主动生成
→ 预览和修改
→ 发送到 IDE / 创建任务 / 复制
```

### 4.4 浏览器组件触发

```text
浏览器插件捕获组件
→ 服务端保存或暂存结构化上下文
→ 通知浮窗置前并进入智能提示词界面
→ 用户补充要求
→ 用户主动生成或直接发送
```

组件到达时不自动调用模型。

### 4.5 Android 快捷安装

```text
Android 项目 + 已连接设备
→ 点击安装最新 APK
→ 使用现有项目 APK 识别结果
→ 安装
→ 自动启动 applicationId
→ 返回明确结果
```

### 4.6 任务快捷处理

```text
任务卡片
→ 根据任务状态显示主操作
→ 调用现有反馈、确认、失败、派发等接口
→ 状态实时或快速刷新
```

## 5. 已核对的真实代码现状

以下结论来自 2026-07-18 对当前代码的只读检查。Codex 必须继续复核，不得只按本任务包猜测。

### 5.1 当前项目

文件：`server/routes/config_routes.py`

已有接口：

- `GET /api/projects`
- `POST /api/projects/select`
- `POST /api/projects/android/scan`

现状：

- 项目列表已返回当前项目；
- 每个项目仅明确附加 `android = inspect_android_project(path)`；
- 项目切换会广播 `project_changed`；
- 没有统一的 `project_kind` 或 `capabilities`；
- 没有同等级的 Web 项目识别结果；
- 项目条目目前主要是 `path/name/last_used`。

分析重点：是否在现有项目接口中增加计算型能力描述，而不是新建另一套项目配置。

### 5.2 IDE 列表与运行状态

文件：

- `server/routes/config_routes.py`
- `server/routes/ide_routes.py`
- `server/dispatch_utils.py`
- `server/task_runtime.py`

已有接口：

- `GET /api/desktop-ides`
- `GET /api/ide/active_status`

现状：

- IDE 配置、展示信息和运行状态分别由不同路径提供；
- `dispatch_utils.get_ide_running_statuses()` 已包含“配置可执行文件 + 可见顶层窗口”的较严格识别；
- `/api/ide/active_status` 仍有一套独立进程扫描逻辑，可能与真实可派发状态不一致；
- `TaskRuntime` 保存 IDE 的 `idle/busy/current_task_id`；
- `dispatch_utils.is_ide_reachable()` 对已支持 IDE 有保守兜底，即使未检测到运行也可能返回可达，让注入层最后失败。

分析重点：浮窗使用的“正在运行”必须有唯一语义，避免 UI 显示可派发但实际没有窗口。

### 5.3 不创建任务的直接派发

文件：`server/routes/phone_routes.py`

已有接口：

- `POST /send`
- `POST /send/stream`

`POST /send` 已支持：

- `text`
- `target`
- `image`
- 可选 `task_id`
- 可选 `owned_paths`

目标为受支持 IDE 时，会直接调用 `_inject_to_ide()`，写入现有会话历史，不创建任务。

现状判断：

- 这是浮窗“直接发送”的首选复用路径；
- 不应为了浮窗再复制一条注入 API；
- 需要分析是否补充更明确的输入校验、目标运行状态和统一响应字段；
- `/send/stream` 的 IDE 路径实际仍是非流式注入，不需要浮窗另做流式派发。

### 5.4 任务列表与任务操作

文件：

- `server/routes/task_routes.py`
- `server/routes/task_routes_flow.py`
- `server/routes/task_routes_workflow.py`
- `server/task_runtime.py`

已有接口包括：

- `GET /api/tasks`
- `POST /api/tasks/create`
- `POST /api/tasks/inspiration`
- `POST /api/tasks/dispatch`
- `POST /api/tasks/feedback`
- `POST /api/tasks/<task_id>/confirm`
- `POST /api/tasks/<task_id>/fail`
- `POST /api/tasks/<task_id>/assign`
- `POST /api/tasks/<task_id>/retry`
- `DELETE /api/tasks/<task_id>`

现状：

- `GET /api/tasks` 已支持 `project/status/target_ide/since/keyword` 过滤；
- 列表会过滤 `chat` 类型；
- 无 `project` 字段的旧任务在项目过滤时仍会匹配；
- `feedback` 会按任务状态决定记录或重新派发；
- `pending_test → done` 已有确认接口；
- 失败反馈已有状态机入口；
- 任务运行时会发布部分任务事件。

分析重点：为任务卡片建立“状态 → 可用动作”契约，前端不能自行猜测状态机规则。

### 5.5 智能提示词

文件：

- `server/routes/prompt_routes.py`
- `server/prompt_composer.py`

已有接口：`POST /api/prompt/compose`

现状：

- 已由浏览器插件和 Android 悬浮窗共享；
- 接收 `component/user_text/task_type/image`；
- 返回候选提示词、组件、难度和任务类型；
- 仅在实际调用接口且有 `user_text` 时尝试模型；
- AI 失败会回退基础模板；
- 截图只允许 Bridge 管理范围内的文件。

现状判断：

- “捕获上下文后不自动生成”主要是客户端与事件流程要求，不需要改提示词核心；
- 需要分析是否扩展组件结构或增加统一 `context_refs`，但禁止破坏现有浏览器插件和 Android 调用格式。

### 5.6 浏览器插件

文件：`tools/component-locator/locator-extension/`

现状：

- `content.js` 已采集标签、文本、ARIA、角色、组件类型、页面标题、CSS selector、XPath、坐标和 URL；
- 组件暂存在浏览器 `chrome.storage.local`；
- `sidepanel.js` 直接调用 `/api/prompt/compose`；
- 当前没有将“刚捕获的组件”推送到 Bridge 浮窗的统一入口；
- 当前没有服务端上下文收件箱或 `context.captured` 事件。

分析重点：设计最小的组件上下文接力，不把完整 DOM 或大量浏览器状态写进任务文本。

### 5.7 Android / ADB

文件：

- `server/routes/device_routes.py`
- `server/routes/ui_locator_routes.py`
- `server/android_project.py`

已有接口包括：

- `GET /api/devices`
- `POST /api/adb/project-install`
- `POST /ui-locator/capture`
- `POST /ui-locator/screenshot`
- `GET /ui-locator/screen.png`
- `POST /ui-locator/locate`
- 以及其他 ADB 连接、日志和维护接口。

现状：

- `/api/adb/project-install` 只允许配置项目中扫描出的 APK；
- 安装后已经按识别出的 `application_id` 自动启动；
- 设备接口同时返回在线状态和 ADB 连接状态；
- Android 截图与 UI 树定位已有基础能力。

现状判断：

- 第一版无需新增单独“启动 App”接口或按钮；
- 应优先复用安装并自动启动、截图和监控；
- 需要分析“当前目标设备”的选择和浮窗最小参数来源。

### 5.8 快捷回复

文件：

- `AideLink-app/.../SettingsRepository.kt`
- `AideLink-app/.../ChatViewModel.kt`
- `AideLink-app/.../ChatInputBar.kt`

现状：

- 快捷回复目前保存在 Android App 本地 DataStore；
- 默认值为“继续”“安装到手机”“升级版本号并提交git”；
- 服务端没有统一快捷回复读取/写入接口；
- 浮窗无法直接读取手机本地 DataStore。

分析重点：

- 第一版快捷回复的唯一数据源应放在哪里；
- 是否迁移为服务端设置并兼容 App，或先提供桌面端独立但明确的本地配置；
- 禁止在多个端继续复制默认列表而没有同步策略。

### 5.9 事件流

文件：

- `server/event_bus.py`
- `server/routes/misc_routes.py`
- `server/routes/project_routes.py`
- `server/task_runtime.py`

已有能力：

- `/events/stream`
- `/events/recent`
- 项目地图 SSE；
- `project_changed`；
- 任务完成、待测试、失败、反馈等事件。

现状判断：

- 浮窗应优先复用现有事件总线，不新建独立 SSE 系统；
- 需要分析 IDE 运行状态、设备状态和上下文捕获是采用事件还是低频轮询；
- 不应让浮窗靠高频全量轮询所有接口维持状态。

### 5.10 托盘和桌面窗口

文件：

- `server/manager_tray.py`
- `server/tray_app.py`
- `tools/component-locator/locator-app/main.py`

现状：

- 当前 AideLink 托盘左键主要打开浏览器 Web 管理页；
- 还没有正式的浮窗外壳；
- 组件定位器小工具已有 Tkinter + 托盘 + 显示/隐藏 + 置顶的可参考实现，但不能直接视为最终浮窗方案。

服务端分析只需说明窗口壳需要哪些状态与接口，不在本轮实现窗口。

## 6. 必须分析的服务端缺口

Codex 至少逐项判断以下内容是“直接复用 / 轻量调整 / 新增薄接口 / 暂不做”。

1. 当前项目能力描述：Web、Android、混合、通用。
2. 当前项目切换后浮窗标题和快捷操作刷新。
3. 统一 IDE 运行状态与忙碌状态。
4. 当前派发目标的保存位置，是否按项目记忆。
5. 直接发送到 IDE 的运行校验、错误和历史行为。
6. 任务首页所需的状态统计和关键任务筛选。
7. 任务状态对应的允许操作矩阵。
8. 快捷回复的服务端来源与 App 兼容方案。
9. 浏览器插件组件进入浮窗的上下文收件箱或事件协议。
10. Android 截图和 Web 组件统一为上下文引用的最小数据结构。
11. 智能提示词预览如何复用现有 `/api/prompt/compose`。
12. Android 当前设备选择、安装 APK 所需参数和结果展示。
13. 浮窗首次打开时需要的 Bootstrap 数据是否应由薄聚合接口返回。
14. 后续状态更新采用现有事件总线、轮询还是两者结合。
15. 服务异常、IDE 消失、设备断开、插件上下文过期时的降级方式。

## 7. 建议评估的数据契约

以下只用于引导分析，不代表必须按原样实现。

### 7.1 项目能力

```json
{
  "path": "F:/project",
  "name": "project",
  "capabilities": ["web", "android"],
  "primary_surface": "android",
  "android": {},
  "web": {}
}
```

要求：

- 单一项目自动选择；
- 混合项目不丢失任一能力；
- `primary_surface` 是否需要持久化由分析决定；
- 不为浮窗建立另一份项目列表。

### 7.2 捕获上下文

```json
{
  "id": "capture-...",
  "project": "F:/project",
  "source": "browser_plugin",
  "type": "web_component",
  "label": "通知方式下拉框",
  "payload": {},
  "screenshot": null,
  "created_at": "...",
  "expires_at": "..."
}
```

要求：

- 捕获上下文不自动成为任务或随记；
- 可被浮窗查看、移除和消费；
- 结构化保存，不能只拼成一句提示词；
- 敏感输入不得采集；
- 是否持久保存或仅短期暂存，由分析给出最小方案。

### 7.3 首页 Bootstrap

可评估是否需要类似：

```text
GET /api/floating-window/bootstrap
```

可能聚合：

- 当前项目和能力；
- 正在运行的 IDE 与 busy/current_task_id；
- 当前派发目标；
- 关键任务和统计；
- 当前设备摘要；
- 待处理上下文；
- 快捷回复。

要求：

- 只能是复用现有模块的薄聚合层；
- 不复制业务规则；
- 若客户端并行调用现有接口已足够稳定，应明确说明无需新增。

## 8. 界面到现有接口的初始映射

| 浮窗区域 / 操作 | 当前实现 | 初始判断 |
|---|---|---|
| 标题栏项目名 | `GET /api/projects` + `project_changed` | 复用，可能补能力字段 |
| 运行 IDE | `GET /api/desktop-ides`、`GET /api/ide/active_status` | 需统一运行语义 |
| 当前派发目标 | App 本地选择 + 服务端目标参数 | 需确定桌面保存策略 |
| 直接发送 | `POST /send` | 直接复用，补契约或校验 |
| 任务列表 | `GET /api/tasks?project=...` | 复用，可能补首页筛选/统计 |
| 快捷反馈 | `POST /api/tasks/feedback` | 复用 |
| 测试通过 | `POST /api/tasks/<id>/confirm` | 复用 |
| 测试失败 | `POST /api/tasks/<id>/fail` 或反馈流程 | 需明确 UI 语义 |
| 任务派发 | `/api/tasks/assign`、`/api/tasks/dispatch`、`/api/tasks/create` | 按场景复用 |
| 智能提示词 | `POST /api/prompt/compose` | 直接复用，扩展需兼容 |
| 保存随记 | `POST /api/tasks/inspiration` | 当前仅简化灵感，需结合上游任务包分析 |
| Web 组件捕获 | 插件 `chrome.storage.local` | 缺少 Bridge 接力 |
| Android 设备 | `GET /api/devices` | 复用 |
| 安装最新 APK | `POST /api/adb/project-install` | 复用，已自动启动 |
| Android 截图 | `/ui-locator/screenshot` | 复用 |
| Android 组件定位 | `/ui-locator/capture` + `/locate` | 复用或次级入口 |
| 状态刷新 | `/events/stream` + 现有任务事件 | 复用并补缺口 |
| 托盘显示/隐藏 | 当前打开 Web；组件定位器有参考壳 | 后续独立 UI 任务 |

## 9. Codex 本轮具体任务

### 9.1 只读检查

必须读取并核对：

- `AGENTS.md`
- `PROGRESS.md`
- `TECH_DEBT.md`
- `docs/AIDELINK_DESKTOP_CAPTURE_FLOATING_WINDOW_TASKS.md`
- 本任务包
- `server/routes/config_routes.py`
- `server/routes/phone_routes.py`
- `server/routes/task_routes*.py`
- `server/routes/ide_routes.py`
- `server/routes/device_routes.py`
- `server/routes/ui_locator_routes.py`
- `server/routes/prompt_routes.py`
- `server/prompt_composer.py`
- `server/dispatch_utils.py`
- `server/task_runtime.py`
- `server/event_bus.py`
- `server/routes/misc_routes.py`
- `server/manager_tray.py`
- `tools/component-locator/locator-extension/**`
- Android 快捷回复和任务相关实现。

如发现更权威的新文件，以实际代码为准，并在报告中说明。

### 9.2 输出分析报告

创建：

```text
docs/AIDELINK_DESKTOP_FLOATING_WINDOW_V1_SERVER_ANALYSIS.md
```

报告必须包含：

1. 当前实现清单；
2. 每个界面区域对应的数据来源和操作接口；
3. 可直接复用、需要调整、需要新增、暂不做的分类；
4. 项目能力识别方案；
5. IDE 运行与 busy 状态统一方案；
6. 直接派发复用方案；
7. 任务卡片状态和操作矩阵；
8. 快捷回复数据源方案；
9. Web / Android 上下文接力协议；
10. 事件和刷新方案；
11. 是否需要 Bootstrap 聚合接口及理由；
12. 建议修改文件范围；
13. 分阶段实现顺序；
14. 每阶段测试范围；
15. 兼容性、隐私和失败恢复风险；
16. 仍需用户确认的问题。

### 9.3 禁止事项

本轮不得：

- 修改 Server、App、插件或 Web 业务代码；
- 建立新任务状态机；
- 实现完整浮窗；
- 新增大型框架或依赖；
- 把 Android、Web、桌面各自做成一套独立后端；
- 自动提交；
- 改动当前工作区已有未提交文件。

只允许新增分析报告文档。

## 10. 推荐后续实现顺序

Codex 的分析报告应验证或调整以下顺序：

### S0：服务端契约冻结

- 项目能力；
- IDE 状态；
- 任务操作矩阵；
- 上下文结构；
- 快捷回复来源；
- 事件类型。

### S1：只读首页数据

- 当前项目；
- IDE；
- 任务摘要；
- 项目专属能力；
- 设备摘要。

### S2：直接派发和快捷回复

- 复用 `/send`；
- 运行 IDE 校验；
- 明确错误；
- 快捷回复配置。

### S3：任务快捷操作

- 反馈；
- 通过；
- 失败；
- 派发；
- 状态刷新。

### S4：上下文接力

- 浏览器组件进入 Bridge；
- Android 截图进入统一上下文；
- 浮窗收到事件；
- 用户主动生成智能提示词。

### S5：项目专属操作

- Web 项目能力；
- Android 安装、截图、监控、更多 ADB；
- 混合项目面板选择。

### S6：桌面窗口壳

- 标题栏项目名；
- 置顶；
- 隐藏；
- 设置；
- 托盘切换显示；
- 位置和大小持久化。

## 11. 分析任务验收标准

完成报告后应满足：

1. 所有判断都有实际代码路径或接口依据；
2. 不凭旧文档假设功能存在；
3. 明确指出 `/send` 可复用直接派发；
4. 明确指出项目接口当前只正式附加 Android 检测；
5. 明确指出 IDE 运行状态存在重复识别逻辑；
6. 明确指出浏览器组件目前只在插件本地保存；
7. 明确指出快捷回复目前只在 Android 本地保存；
8. 明确指出 APK 项目安装已经自动启动 App；
9. 明确指出现有事件总线可复用；
10. 最终方案保持第一版最小范围，不借机重构整个服务端；
11. 给出可以直接拆给不同 IDE 的后续实现任务；
12. 检查 `git diff`，确认只新增分析报告，不提交。

## 12. 仍需在分析后由用户确认

1. 混合项目默认显示 Web 还是 Android 快捷区；
2. 当前派发目标是否按项目记忆；
3. 快捷回复是否在 App 和桌面之间统一同步；
4. 捕获上下文是短期收件箱还是长期开发随记证据；
5. 浏览器插件捕获后是否强制浮窗置前，还是只闪烁提醒；
6. Android 第一版“实时监控”具体复用哪个现有画面和接口；
7. 任务首页默认显示多少条；
8. 测试失败是直接调用 fail，还是先通过 feedback 让当前 IDE 修复；
9. 是否为浮窗增加薄 Bootstrap 接口；
10. 浮窗壳最终使用 WebView、pywebview、原生窗口或其他现有技术。

## 13. 给 Codex 的执行口令

```text
打开 F:\aide，读取项目规则和 docs/AIDELINK_DESKTOP_FLOATING_WINDOW_V1_SERVER_ANALYSIS_TASK.md。按任务包只读核对真实代码，创建 docs/AIDELINK_DESKTOP_FLOATING_WINDOW_V1_SERVER_ANALYSIS.md。不要修改任何业务代码，不提交。完成后检查 git diff，确认只有分析报告是本轮新增。
```

# 数据流

> 本文档描述 AideLink 中各个核心功能的数据流。

---

## 消息桥接流

### 流程图

```
手机 App
  │
  │ 1. 用户输入消息
  ▼
ChatViewModel
  │
  │ 2. 调用 BridgeApi.sendMessage()
  ▼
BridgeApi
  │
  │ 3. HTTP POST /send
  │    {"message": "帮我写一个排序算法"}
  ▼
Flask 服务端
  │
  │ 4. 解析请求
  ▼
message_routes.py
  │
  │ 5. 写入 phone_in.txt
  ▼
IDE AI 助手
  │
  │ 6. 读取消息并执行
  ▼
执行结果
  │
  │ 7. HTTP 响应
  │    {"status": "ok", "response": "好的，我来帮你写..."}
  ▼
BridgeApi
  │
  │ 8. 解析响应
  ▼
ChatViewModel
  │
  │ 9. 更新 UI
  ▼
手机 App
```

### 数据格式

**请求**:

```json
POST /send
Content-Type: application/json

{
  "message": "帮我写一个排序算法",
  "source": "android",
  "timestamp": "2026-06-30T12:00:00Z"
}
```

**响应**:

```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "ok",
  "response": "好的，我来帮你写一个快速排序算法..."
}
```

---

## 剪贴板同步流

### 手机 → PC

```
手机 App
  │
  │ 1. 用户点击「同步剪贴板」
  ▼
ChatViewModel
  │
  │ 2. 获取手机剪贴板内容
  ▼
BridgeApi
  │
  │ 3. HTTP POST /clipboard
  │    {"content": "剪贴板内容"}
  ▼
Flask 服务端
  │
  │ 4. 解析请求
  ▼
message_routes.py
  │
  │ 5. 更新 PC 剪贴板
  ▼
PC 剪贴板
```

### PC → 手机

```
PC 剪贴板
  │
  │ 1. 用户复制内容
  ▼
手机 App
  │
  │ 2. 用户点击「获取剪贴板」
  ▼
BridgeApi
  │
  │ 3. HTTP GET /clipboard
  ▼
Flask 服务端
  │
  │ 4. 读取 PC 剪贴板
  ▼
message_routes.py
  │
  │ 5. HTTP 响应
  │    {"content": "剪贴板内容", "timestamp": "..."}
  ▼
BridgeApi
  │
  │ 6. 更新手机剪贴板
  ▼
手机 App
```

---

## 截图流

### 全屏截图

```
手机 App
  │
  │ 1. 进入监控页面
  ▼
ScreenMonitorPanel
  │
  │ 2. 定时请求截图
  ▼
BridgeApi
  │
  │ 3. HTTP GET /screenshot
  ▼
Flask 服务端
  │
  │ 4. 调用截图工具
  ▼
screenshot_utils.py
  │
  │ 5. 截取屏幕
  │    - Windows: ImageGrab.grab()
  │    - 截取客户区
  ▼
图像处理
  │
  │ 6. 压缩 + 裁剪
  │    - JPEG 压缩
  │    - 按质量参数调整
  ▼
Flask 服务端
  │
  │ 7. HTTP 响应 (JPEG 二进制)
  ▼
BridgeApi
  │
  │ 8. 读取字节流
  ▼
ScreenMonitorPanel
  │
  │ 9. 显示截图
  ▼
手机 App
```

### 裁剪截图

```
手机 App
  │
  │ 1. 用户选择裁剪区域
  ▼
ScreenMonitorPanel
  │
  │ 2. 获取裁剪配置
  │    {"left": 100, "top": 50, "right": 1820, "bottom": 1030}
  ▼
BridgeApi
  │
  │ 3. HTTP GET /screenshot/crop?left=100&top=50&right=1820&bottom=1030
  ▼
Flask 服务端
  │
  │ 4. 调用截图工具
  ▼
screenshot_utils.py
  │
  │ 5. 截取屏幕
  │    - 截取客户区
  │    - 按参数裁剪
  ▼
图像处理
  │
  │ 6. 压缩
  │    - JPEG 压缩
  ▼
Flask 服务端
  │
  │ 7. HTTP 响应 (JPEG 二进制)
  ▼
BridgeApi
  │
  │ 8. 读取字节流
  ▼
ScreenMonitorPanel
  │
  │ 9. 显示裁剪后的截图
  ▼
手机 App
```

---

## 任务管理流

### 创建任务

```
手机 App
  │
  │ 1. 用户输入任务描述
  ▼
TaskListScreen
  │
  │ 2. 调用 BridgeApi.createTask()
  ▼
BridgeApi
  │
  │ 3. HTTP POST /api/tasks
  │    {"title": "写一个排序算法", "type": "coding"}
  ▼
Flask 服务端
  │
  │ 4. 解析请求
  ▼
task_routes.py
  │
  │ 5. 创建任务
  │    - 生成任务 ID
  │    - 保存到 tasks.json
  ▼
任务队列
  │
  │ 6. HTTP 响应
  │    {"status": "ok", "task_id": "task-001"}
  ▼
BridgeApi
  │
  │ 7. 更新任务列表
  ▼
TaskListScreen
  │
  │ 8. 显示新任务
  ▼
手机 App
```

### 任务执行

```
任务队列
  │
  │ 1. 任务进入队列
  ▼
Flask 服务端
  │
  │ 2. 调用任务委派
  ▼
call_co_workers.py
  │
  │ 3. Coder 生成代码
  │    - 调用 MiniMax API
  │    - 生成初始代码
  ▼
Coder 结果
  │
  │ 4. Reviewer 审查代码
  │    - 调用 MiniMax API
  │    - 生成审查意见
  ▼
Reviewer 结果
  │
  │ 5. Refactor 优化代码
  │    - 调用 MiniMax API
  │    - 优化代码
  ▼
最终结果
  │
  │ 6. 更新任务状态
  │    - 标记为完成
  │    - 保存结果
  ▼
tasks.json
```

---

## IDE 控制流

### 启动 IDE

```
手机 App
  │
  │ 1. 用户点击「启动 IDE」
  ▼
SettingsScreen
  │
  │ 2. 调用 BridgeApi.startIde()
  ▼
BridgeApi
  │
  │ 3. HTTP POST /ide/start
  │    {"ide": "cursor", "project_path": "F:\\AideLink"}
  ▼
Flask 服务端
  │
  │ 4. 解析请求
  ▼
ide_routes.py
  │
  │ 5. 启动 IDE 进程
  │    - 查找 IDE 路径
  │    - 启动进程
  │    - 记录 PID
  ▼
IDE 进程
  │
  │ 6. HTTP 响应
  │    {"status": "ok", "pid": 12345}
  ▼
BridgeApi
  │
  │ 7. 更新 IDE 状态
  ▼
SettingsScreen
  │
  │ 8. 显示启动成功
  ▼
手机 App
```

### 停止 IDE

```
手机 App
  │
  │ 1. 用户点击「停止 IDE」
  ▼
SettingsScreen
  │
  │ 2. 调用 BridgeApi.stopIde()
  ▼
BridgeApi
  │
  │ 3. HTTP POST /ide/stop
  │    {"ide": "cursor"}
  ▼
Flask 服务端
  │
  │ 4. 解析请求
  ▼
ide_routes.py
  │
  │ 5. 停止 IDE 进程
  │    - 查找进程 PID
  │    - 终止进程
  ▼
IDE 进程
  │
  │ 6. HTTP 响应
  │    {"status": "ok"}
  ▼
BridgeApi
  │
  │ 7. 更新 IDE 状态
  ▼
SettingsScreen
  │
  │ 8. 显示停止成功
  ▼
手机 App
```

---

## 设置同步流

### 从服务端拉取设置

```
手机 App
  │
  │ 1. 应用启动
  ▼
SettingsRepository
  │
  │ 2. 调用 syncFromServer()
  ▼
BridgeApi
  │
  │ 3. HTTP GET /settings
  ▼
Flask 服务端
  │
  │ 4. 读取 settings.json
  ▼
settings_routes.py
  │
  │ 5. HTTP 响应
  │    {"server_url": "...", "desktop_ide": "...", ...}
  ▼
BridgeApi
  │
  │ 6. 解析响应
  ▼
SettingsRepository
  │
  │ 7. 保存到 DataStore
  ▼
手机 App
```

### 推送设置到服务端

```
手机 App
  │
  │ 1. 用户修改设置
  ▼
SettingsScreen
  │
  │ 2. 调用 pushToServer()
  ▼
SettingsRepository
  │
  │ 3. 获取本地设置
  ▼
BridgeApi
  │
  │ 4. HTTP POST /settings
  │    {"server_url": "...", "desktop_ide": "...", ...}
  ▼
Flask 服务端
  │
  │ 5. 解析请求
  ▼
settings_routes.py
  │
  │ 6. 更新 settings.json
  ▼
settings.json
  │
  │ 7. HTTP 响应
  │    {"status": "ok"}
  ▼
BridgeApi
  │
  │ 8. 同步完成
  ▼
SettingsRepository
  │
  │ 9. 更新 UI
  ▼
手机 App
```

---

## 事件流

### Server-Sent Events (SSE)

```
手机 App
  │
  │ 1. 建立 SSE 连接
  ▼
BridgeApi
  │
  │ 2. HTTP GET /events/stream
  ▼
Flask 服务端
  │
  │ 3. 保持连接
  ▼
event_routes.py
  │
  │ 4. 监听事件
  │    - 任务状态变更
  │    - 设备连接/断开
  │    - IDE 启动/停止
  ▼
事件源
  │
  │ 5. 发送事件
  │    event: task.completed
  │    data: {"task_id": "task-001", "status": "completed"}
  ▼
BridgeApi
  │
  │ 6. 解析事件
  ▼
手机 App
  │
  │ 7. 更新 UI
  ▼
用户看到更新
```

---

## 下一步

- [设计决策记录](decisions.md) - 了解技术选型原因
- [架构图表](diagrams.md) - 查看架构图
- [API 参考](../developer/api-reference.md) - 查看完整 API 文档

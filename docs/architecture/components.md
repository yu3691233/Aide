# 组件详解

> 本文档详细描述 AideLink 各组件的职责、接口和实现。

---

## Android 客户端

### 目录结构

```
AideLink-app/
├── app/src/main/java/cc/aidelink/app/
│   ├── ui/                    # UI 层
│   │   ├── screens/           # 页面组件
│   │   │   ├── HomeScreen.kt
│   │   │   ├── ChatScreen.kt
│   │   │   ├── SettingsScreen.kt
│   │   │   └── TaskListScreen.kt
│   │   ├── components/        # 通用组件
│   │   │   ├── TopAppBar.kt
│   │   │   ├── BottomNavBar.kt
│   │   │   └── ScreenMonitorPanel.kt
│   │   └── theme/             # 主题配置
│   │       ├── Theme.kt
│   │       ├── Color.kt
│   │       └── Type.kt
│   ├── data/                  # 数据层
│   │   ├── repository/        # 仓库实现
│   │   │   ├── SettingsRepository.kt
│   │   │   └── TaskRepository.kt
│   │   ├── model/             # 数据模型
│   │   │   ├── Task.kt
│   │   │   ├── Device.kt
│   │   │   └── Settings.kt
│   │   └── network/           # 网络请求
│   │       └── BridgeApi.kt
│   ├── di/                    # 依赖注入
│   │   ├── AppModule.kt
│   │   └── NetworkModule.kt
│   └── navigation/            # 导航配置
│       ├── NavGraph.kt
│       └── Destination.kt
└── app/build.gradle.kts       # 构建配置
```

### 关键组件

#### BridgeApi

**职责**: 封装所有与服务端的 HTTP 通信

**接口**:

```kotlin
class BridgeApi(private val baseUrl: String) {
    // 消息桥接
    suspend fun sendMessage(message: String): Response
    suspend fun getClipboard(): String
    suspend fun setClipboard(content: String)
    
    // 截图
    suspend fun getScreenshot(): ByteArray
    suspend fun getCroppedScreenshot(config: CropConfig): ByteArray
    
    // 任务管理
    suspend fun getTasks(): List<Task>
    suspend fun createTask(task: Task): String
    suspend fun deleteTask(taskId: String)
    
    // 设置
    suspend fun getSettings(): Settings
    suspend fun updateSettings(settings: Settings)
    
    // IDE 控制
    suspend fun getDesktopIdes(): List<IdeInfo>
    suspend fun startIde(ide: String, projectPath: String)
    suspend fun stopIde(ide: String)
}
```

#### SettingsRepository

**职责**: 管理应用设置，支持服务端同步

**接口**:

```kotlin
class SettingsRepository(
    private val dataStore: DataStore<Preferences>,
    private val bridgeApi: BridgeApi
) {
    // 本地设置
    suspend fun getServerUrl(): String
    suspend fun setServerUrl(url: String)
    
    // 服务端同步
    suspend fun syncFromServer()
    suspend fun pushToServer()
    suspend fun pushSettingToServer(key: String, value: Any)
}
```

#### ChatViewModel

**职责**: 聊天页面的业务逻辑

**接口**:

```kotlin
class ChatViewModel(
    private val bridgeApi: BridgeApi,
    private val settingsRepository: SettingsRepository
) : ViewModel() {
    // 消息管理
    val messages: StateFlow<List<Message>>
    fun sendMessage(message: String)
    
    // 连接状态
    val connectionState: StateFlow<ConnectionState>
    fun checkConnection()
}
```

---

## Flask 服务端

### 目录结构

```
server/
├── phone_chat_bridge.py       # 主入口
├── routes/                    # 路由模块
│   ├── __init__.py
│   ├── message_routes.py      # 消息桥接路由
│   ├── screenshot_routes.py   # 截图路由
│   ├── ide_routes.py          # IDE 控制路由
│   ├── settings_routes.py     # 设置路由
│   ├── xiaomengling_routes.py # Aide 路由
│   ├── device_routes.py       # 设备管理路由
│   ├── frp_routes.py          # FRP 管理路由
│   ├── app_routes.py          # 应用管理路由
│   └── event_routes.py        # 事件流路由
├── utils/                     # 工具模块
│   ├── __init__.py
│   ├── json_utils.py          # JSON 原子写
│   ├── adb_utils.py           # ADB 工具
│   ├── screenshot_utils.py    # 截图工具
│   ├── ide_scanner.py         # IDE 扫描器
│   └── model_registry.py      # 模型注册中心
├── mascot.py                  # 桌面吉祥物
├── mascot_tray.py             # 系统托盘
├── watchdog.py                # 进程监控
├── self_evolution.py          # 自演化引擎
├── evolution_daemon.py        # 自演化守护进程
├── call_co_workers.py         # 任务委派
└── delegate_task.py           # 任务拆分
```

### 关键组件

#### phone_chat_bridge.py

**职责**: Flask 应用主入口，注册所有 Blueprint

**代码**:

```python
from flask import Flask
from routes import (
    message_routes,
    screenshot_routes,
    ide_routes,
    settings_routes,
    xiaomengling_routes,
    device_routes,
    frp_routes,
    app_routes,
    event_routes
)

app = Flask(__name__)

# 注册 Blueprint
app.register_blueprint(message_routes.bp)
app.register_blueprint(screenshot_routes.bp)
app.register_blueprint(ide_routes.bp)
app.register_blueprint(settings_routes.bp)
app.register_blueprint(xiaomengling_routes.bp)
app.register_blueprint(device_routes.bp)
app.register_blueprint(frp_routes.bp)
app.register_blueprint(app_routes.bp)
app.register_blueprint(event_routes.bp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

#### routes/message_routes.py

**职责**: 消息桥接路由

**接口**:

```python
from flask import Blueprint, request, jsonify

bp = Blueprint('message', __name__)

@bp.route('/send', methods=['POST'])
def send_message():
    """发送消息到 PC 端 AI 助手"""
    data = request.get_json()
    message = data.get('message')
    
    # 处理消息
    response = process_message(message)
    
    return jsonify({
        'status': 'ok',
        'response': response
    })

@bp.route('/clipboard', methods=['GET'])
def get_clipboard():
    """获取 PC 端剪贴板内容"""
    content = get_clipboard_content()
    return jsonify({
        'content': content,
        'timestamp': datetime.now().isoformat()
    })

@bp.route('/clipboard', methods=['POST'])
def set_clipboard():
    """设置 PC 端剪贴板内容"""
    data = request.get_json()
    content = data.get('content')
    
    set_clipboard_content(content)
    
    return jsonify({'status': 'ok'})
```

#### utils/json_utils.py

**职责**: JSON 原子写入工具

**接口**:

```python
import json
import os
import tempfile
from threading import Lock

_file_locks = {}

def atomic_write_json(filepath: str, data: dict):
    """原子写入 JSON 文件"""
    lock = _file_locks.setdefault(filepath, Lock())
    
    with lock:
        # 写入临时文件
        dir_name = os.path.dirname(filepath)
        with tempfile.NamedTemporaryFile(
            mode='w',
            dir=dir_name,
            delete=False,
            suffix='.tmp'
        ) as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path = f.name
        
        # 原子替换
        os.replace(temp_path, filepath)

def read_json(filepath: str) -> dict:
    """读取 JSON 文件"""
    lock = _file_locks.setdefault(filepath, Lock())
    
    with lock:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
```

---

## AI 协作层

### 组件结构

```
AI 协作层
├── MiniMax API                # AI 模型服务
│   ├── model_registry.py      # 模型注册中心
│   └── tool_calling.py        # 工具调用支持
├── 任务委派                   # Coder→Reviewer→Refactor 闭环
│   ├── call_co_workers.py     # 多 AI 协作
│   └── delegate_task.py       # 任务拆分
└── 自演化                     # 失败记忆 + 工作绕过知识库
    ├── self_evolution.py      # 自演化引擎
    └── evolution_daemon.py    # 守护进程
```

### 关键组件

#### model_registry.py

**职责**: 动态模型管理

**接口**:

```python
class ModelRegistry:
    def __init__(self):
        self.models = {}
    
    def register_model(self, model_id: str, config: dict):
        """注册新模型"""
        self.models[model_id] = config
    
    def get_model(self, model_id: str) -> dict:
        """获取模型配置"""
        return self.models.get(model_id)
    
    def list_models(self) -> list:
        """列出所有模型"""
        return list(self.models.values())
    
    def call_model(self, model_id: str, prompt: str) -> str:
        """调用模型"""
        model = self.get_model(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")
        
        # 调用 API
        response = call_api(model, prompt)
        return response
```

#### call_co_workers.py

**职责**: 多 AI 协作

**接口**:

```python
def delegate_task(task: str) -> str:
    """委派任务给多个 AI"""
    # 1. Coder 生成代码
    code = call_coder(task)
    
    # 2. Reviewer 审查代码
    review = call_reviewer(code)
    
    # 3. Refactor 优化代码
    final_code = call_refactor(code, review)
    
    return final_code
```

#### self_evolution.py

**职责**: 自演化引擎

**接口**:

```python
class SelfEvolution:
    def __init__(self):
        self.failure_memory = {}
        self.workaround_knowledge = {}
    
    def record_failure(self, task: str, error: str):
        """记录失败任务"""
        self.failure_memory[task] = {
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_workaround(self, task: str) -> str:
        """获取工作绕过方案"""
        return self.workaround_knowledge.get(task)
    
    def learn_from_failure(self, task: str):
        """从失败中学习"""
        # 分析失败原因
        # 生成改进策略
        # 保存到知识库
        pass
```

---

## 组件交互

### 消息桥接流

```
Android App (BridgeApi)
    │
    │ HTTP POST /send
    ▼
Flask (message_routes.py)
    │
    │ 写入 phone_in.txt
    ▼
IDE AI 助手
    │
    │ 读取并执行
    ▼
执行结果
    │
    │ HTTP 响应
    ▼
Android App (ChatViewModel)
```

### 设置同步流

```
Android App (SettingsRepository)
    │
    │ HTTP GET /settings
    ▼
Flask (settings_routes.py)
    │
    │ 读取 settings.json
    ▼
返回设置数据
    │
    │ HTTP 响应
    ▼
Android App (SettingsRepository)
    │
    │ 保存到 DataStore
```

---

## 下一步

- [数据流](data-flow.md) - 了解完整数据流
- [设计决策记录](decisions.md) - 了解技术选型原因
- [架构图表](diagrams.md) - 查看架构图

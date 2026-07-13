package cc.aidelink.app.ui.screens.idechat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import cc.aidelink.app.data.api.BridgeApi
import cc.aidelink.app.data.repository.ConnectionStatus
import cc.aidelink.app.data.repository.IdeConnectionManager
import cc.aidelink.app.data.repository.ServerConfigRepository
import cc.aidelink.app.data.repository.SettingsRepository
import cc.aidelink.app.domain.model.ServerType
import dagger.hilt.android.lifecycle.HiltViewModel
import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.prepareRequest
import io.ktor.client.request.url
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsChannel
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.http.HttpMethod
import io.ktor.serialization.kotlinx.json.json
import io.ktor.utils.io.readUTF8Line
import kotlinx.coroutines.Job
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.util.UUID
import javax.inject.Inject
import android.content.Context
import android.content.SharedPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import io.ktor.client.request.header
import io.ktor.http.HttpHeaders

/**
 * 目标服务类型枚举
 */
enum class Target(val displayName: String, val defaultPort: Int) {
    OPENCODE("OpenCode", 4096),
    MIMOCODE("MimoCode", 4097),
    CLAUDE_CODE("Claude Code", 8000),
}

/**
 * 消息角色
 */
enum class MessageRole {
    USER,
    ASSISTANT,
    SYSTEM;
}

/**
 * 聊天消息数据类
 */
@Serializable
data class IdeChatMessage(
    val id: String = UUID.randomUUID().toString(),
    val role: String,
    val content: String,
    val timestamp: Long = System.currentTimeMillis(),
    val isStreaming: Boolean = false
)

/**
 * 会话信息
 */
@Serializable
data class SessionInfo(
    val id: String,
    val title: String = "",
    val updatedAt: Long = System.currentTimeMillis()
)

/**
 * UI 状态
 */
data class IdeChatUiState(
    val messages: List<IdeChatMessage> = emptyList(),
    val input: String = "",
    val sending: Boolean = false,
    val loading: Boolean = false,
    val error: String? = null,
    val toastMessage: String? = null,
    val currentSessionId: String? = null,
    val sessions: List<SessionInfo> = emptyList(),
    val target: Target = Target.OPENCODE,
    val availableModels: List<String> = listOf(
        "opencode/deepseek-v4-flash-free",
        "opencode/mimo-v2.5-free",
        "opencode/nemotron-3-ultra-free"
    ),
    val selectedModel: String? = "opencode/deepseek-v4-flash-free",
    val showWebPanel: Boolean = false,
    val serverUrl: String = "",
    val username: String = "",
    val token: String = "",
    val bridgeUrl: String = "",
    val startingServer: Boolean = false,
    val currentServerId: String? = null,
    val currentServerName: String? = null,
    val connectionStatus: ConnectionStatus = ConnectionStatus.DISCONNECTED,
    val autoSkipLock: Boolean = false,
    val selectedIdeList: List<String> = emptyList(),
    val availableIdes: List<cc.aidelink.app.domain.model.bridge.DesktopIde> = emptyList(),
    val ideRunningMap: Map<String, Boolean> = emptyMap(),
)

@HiltViewModel
class IdeChatViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val serverRepository: ServerConfigRepository,
    private val connectionManager: IdeConnectionManager,
    private val settingsRepository: SettingsRepository,
    private val bridgeApi: BridgeApi,
) : ViewModel() {

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        encodeDefaults = false
    }

    private val client = HttpClient(OkHttp) {
        install(io.ktor.client.plugins.contentnegotiation.ContentNegotiation) {
            json(json)
        }
        install(io.ktor.client.plugins.HttpTimeout) {
            requestTimeoutMillis = 120_000
            connectTimeoutMillis = 10_000
            socketTimeoutMillis = 120_000
        }
        engine {
            config {
                followRedirects(true)
                retryOnConnectionFailure(true)
            }
        }
    }

    private val prefs: SharedPreferences = context.getSharedPreferences("ide_chat_prefs", Context.MODE_PRIVATE)

    private val _uiState = MutableStateFlow(IdeChatUiState())
    val uiState: StateFlow<IdeChatUiState> = _uiState.asStateFlow()

    // WebView deep-link 导航流
    private val _navigateUrl = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val navigateUrl: SharedFlow<String> = _navigateUrl.asSharedFlow()

    private var sseJob: Job? = null
    private var connectionStatusJob: Job? = null

    init {
        // 不再自动加载设置，等待 initFromServerId() 或 initFromLastSelected() 调用
    }

    /**
     * 通过 serverId 初始化 ViewModel
     * 从 IdeServerRepository 加载服务器配置，设置连接
     */
    fun initFromServerId(serverId: String) {
        if (_uiState.value.currentServerId == serverId) return
        viewModelScope.launch {
            val server = serverRepository.getServers().firstOrNull { it.id == serverId }
            if (server != null) {
                val target = server.serverType.toTarget()
                val models = getModelsForTarget(target)
                val bridgeUrl = prefs.getString("bridge_url", bridgeApi.baseUrl)
                    ?: bridgeApi.baseUrl

                _uiState.update {
                    it.copy(
                        target = target,
                        serverUrl = server.url,
                        username = server.username,
                        token = server.password ?: "",
                        bridgeUrl = bridgeUrl,
                        availableModels = models,
                        selectedModel = models.firstOrNull(),
                        currentServerId = serverId,
                        currentServerName = server.displayName,
                        connectionStatus = ConnectionStatus.DISCONNECTED,
                        messages = emptyList(),
                        currentSessionId = null,
                        error = null,
                        sending = false,
                        loading = false,
                        showWebPanel = false,
                    )
                }

                // 通过连接管理器建立连接
                connectionManager.connect(serverId, server)

                // 观察连接状态
                observeConnectionStatus(serverId)

                // 加载会话列表
                loadSessions()
                // 加载已选 IDE 列表（用于设置弹窗）
                loadSelectedIdeList()
            } else {
                _uiState.update { it.copy(error = "未找到服务器配置 (ID: ${serverId.take(8)})") }
            }
        }
    }

    /**
     * 使用上次选中的服务器初始化
     */
    fun initFromLastSelected() {
        viewModelScope.launch {
            val selectedId = serverRepository.getSelectedServerId()
            if (selectedId != null) {
                initFromServerId(selectedId)
            }
            loadSelectedIdeList()
        }
    }

    private fun ServerType.toTarget(): Target = when (this) {
        ServerType.OPENCODE -> Target.OPENCODE
        ServerType.MIMOCODE -> Target.MIMOCODE
        ServerType.HAPPY -> Target.OPENCODE
    }

    private fun observeConnectionStatus(serverId: String) {
        connectionStatusJob?.cancel()
        connectionStatusJob = viewModelScope.launch {
            connectionManager.connectionStates.collect { states ->
                val status = states[serverId] ?: ConnectionStatus.DISCONNECTED
                _uiState.update { it.copy(connectionStatus = status) }
            }
        }
    }

    /**
     * 手动重连当前服务器
     */
    fun reconnect() {
        val serverId = _uiState.value.currentServerId ?: return
        viewModelScope.launch {
            val server = serverRepository.getServers().firstOrNull { it.id == serverId } ?: return@launch
            connectionManager.connect(serverId, server)
        }
    }

    private fun getModelsForTarget(target: Target): List<String> {
        return when (target) {
            Target.OPENCODE -> listOf(
                "opencode/deepseek-v4-flash-free",
                "opencode/mimo-v2.5-free",
                "opencode/nemotron-3-ultra-free"
            )
            Target.MIMOCODE -> listOf(
                "mimo-auto",
                "deepseek"
            )
            Target.CLAUDE_CODE -> emptyList()
        }
    }

    /**
     * 选择模型
     */
    fun selectModel(model: String) {
        _uiState.update { it.copy(selectedModel = model) }
    }

    /**
     * 切换 Web 面板状态
     */
    fun toggleWebPanel(show: Boolean) {
        _uiState.update { it.copy(showWebPanel = show) }
    }

    /**
     * 更新输入内容
     */
    fun updateInput(input: String) {
        _uiState.update { it.copy(input = input) }
    }

    /**
     * 清除错误信息
     */
    fun clearError() {
        _uiState.update { it.copy(error = null) }
    }

    /**
     * 获取基础 URL
     */
    private fun getBaseUrl(): String {
        return _uiState.value.serverUrl
    }

    /**
     * 保存当前 IDE 的连接设置
     * 通过 IdeServerRepository 更新服务器配置
     */
    fun saveSettings(url: String, user: String, pass: String, bridgeUrl: String) {
        val serverId = _uiState.value.currentServerId
        viewModelScope.launch {
            if (serverId != null) {
                val servers = serverRepository.getServers()
                val currentServer = servers.firstOrNull { it.id == serverId }
                if (currentServer != null) {
                    val updatedServer = currentServer.copy(
                        url = url,
                        username = user,
                        password = pass.ifBlank { null },
                    )
                    serverRepository.updateServer(updatedServer)
                }
            }

            // bridgeUrl 单独存储（ServerConfig 中无此字段）
            prefs.edit().putString("bridge_url", bridgeUrl).apply()

            _uiState.update {
                it.copy(
                    serverUrl = url,
                    username = user,
                    token = pass,
                    bridgeUrl = bridgeUrl,
                    messages = emptyList(),
                    currentSessionId = null
                )
            }
            // 保存后重新加载会话以应用新设置
            loadSessions()
        }
    }

    /**
     * 远程启动电脑端的对应 IDE 服务器
     */
    fun startIdeServer() {
        val bridgeUrl = _uiState.value.bridgeUrl
        if (_uiState.value.startingServer) return
        _uiState.update { it.copy(startingServer = true, error = null) }
        viewModelScope.launch {
            try {
                val ideKey = when (_uiState.value.target) {
                    Target.OPENCODE -> "oc"
                    Target.MIMOCODE -> "mimo"
                    Target.CLAUDE_CODE -> "happy"
                }
                val startUrl = "${bridgeUrl.trimEnd('/')}/ide/$ideKey/start"

                val response = client.post(startUrl)
                if (response.status.isSuccess()) {
                    _uiState.update { it.copy(startingServer = false) }
                    loadSessions()
                } else {
                    val body = response.bodyAsChannel().readUTF8Line() ?: "启动失败"
                    _uiState.update { it.copy(startingServer = false, error = "远程启动失败: $body") }
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(startingServer = false, error = "远程启动异常: ${e.message}") }
            }
        }
    }

    /**
     * 解锁 IDE（释放租约）
     */
    fun unlockIde() {
        val bridgeUrl = _uiState.value.bridgeUrl
        viewModelScope.launch {
            try {
                val ideKey = when (_uiState.value.target) {
                    Target.OPENCODE -> "oc"
                    Target.MIMOCODE -> "mimo"
                    Target.CLAUDE_CODE -> "happy"
                }
                val releaseUrl = "${bridgeUrl.trimEnd('/')}/ide/$ideKey/release"

                val response = client.post(releaseUrl) {
                    setBody("{}")
                }
                if (response.status.isSuccess()) {
                    _uiState.update { it.copy(error = null) }
                } else {
                    val body = response.bodyAsChannel().readUTF8Line() ?: "解锁失败"
                    _uiState.update { it.copy(error = "解锁失败: $body") }
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(error = "解锁异常: ${e.message}") }
            }
        }
    }

    /**
     * 唤醒电脑端屏幕（检测锁屏并唤醒）
     */
    fun wakeScreen() {
        viewModelScope.launch {
            val bridgeUrl = _uiState.value.bridgeUrl
            if (bridgeUrl.isBlank()) {
                _uiState.update { it.copy(error = "未配置电脑端桥接地址") }
                return@launch
            }
            try {
                val response = client.post("${bridgeUrl.trimEnd('/')}/screen/wake") {
                    contentType(ContentType.Application.Json)
                }
                if (response.status.isSuccess()) {
                    _uiState.update { it.copy(toastMessage = "已唤醒电脑屏幕") }
                    kotlinx.coroutines.delay(3000)
                    _uiState.update { it.copy(toastMessage = null) }
                } else {
                    _uiState.update { it.copy(error = "唤醒屏幕失败") }
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(error = "唤醒屏幕异常: ${e.message}") }
            }
        }
    }

    fun setAutoSkipLock(enabled: Boolean) {
        viewModelScope.launch(Dispatchers.IO) {
            val bridgeUrl = _uiState.value.bridgeUrl
            if (bridgeUrl.isBlank()) return@launch
            runCatching {
                val api = BridgeApi(bridgeUrl)
                api.setScreenSettings(enabled)
            }
            _uiState.update { it.copy(autoSkipLock = enabled) }
        }
    }

    fun loadSelectedIdeList() {
        viewModelScope.launch {
            val ides = settingsRepository.getDesktopIdeList()
            android.util.Log.d("IdeChatVM", "loadSelectedIdeList: $ides")
            _uiState.update { it.copy(selectedIdeList = ides) }
        }
    }

    fun loadAvailableIdes() {
        viewModelScope.launch(Dispatchers.IO) {
            val bridgeUrl = _uiState.value.bridgeUrl
            android.util.Log.d("IdeChatVM", "loadAvailableIdes: bridgeUrl=$bridgeUrl")
            if (bridgeUrl.isBlank()) return@launch
            try {
                val api = BridgeApi(bridgeUrl)
                val ides = api.getDesktopIdes()
                android.util.Log.d("IdeChatVM", "loadAvailableIdes: got ${ides.size} ides")
                _uiState.update { it.copy(availableIdes = ides) }
                // 加载完可用 IDE 后，同步获取运行状态
                loadIdeRunningStatus()
            } catch (e: Exception) {
                android.util.Log.e("IdeChatVM", "loadAvailableIdes failed: ${e.message}")
            }
        }
    }

    fun loadIdeRunningStatus() {
        viewModelScope.launch(Dispatchers.IO) {
            val bridgeUrl = _uiState.value.bridgeUrl
            if (bridgeUrl.isBlank()) return@launch
            try {
                val api = BridgeApi(bridgeUrl)
                val processes = api.getIdeProcesses()
                val runningMap = processes.associate { it.key to it.running }
                android.util.Log.d("IdeChatVM", "loadIdeRunningStatus: $runningMap")
                _uiState.update { it.copy(ideRunningMap = runningMap) }
            } catch (e: Exception) {
                android.util.Log.e("IdeChatVM", "loadIdeRunningStatus failed: ${e.message}")
            }
        }
    }

    fun startIde(ide: String) {
        viewModelScope.launch(Dispatchers.IO) {
            val bridgeUrl = _uiState.value.bridgeUrl
            if (bridgeUrl.isBlank()) {
                _uiState.update { it.copy(error = "未配置电脑端桥接地址") }
                return@launch
            }
            try {
                val api = BridgeApi(bridgeUrl)
                val success = api.startIde(ide)
                _uiState.update { it.copy(error = if (success) null else "启动 IDE 失败") }
            } catch (e: Exception) {
                _uiState.update { it.copy(error = "启动 IDE 异常: ${e.message}") }
            }
        }
    }

    fun stopIde(ide: String) {
        viewModelScope.launch(Dispatchers.IO) {
            val bridgeUrl = _uiState.value.bridgeUrl
            if (bridgeUrl.isBlank()) {
                _uiState.update { it.copy(error = "未配置电脑端桥接地址") }
                return@launch
            }
            try {
                val api = BridgeApi(bridgeUrl)
                val success = api.stopIde(ide)
                _uiState.update { it.copy(error = if (success) null else "停止 IDE 失败") }
            } catch (e: Exception) {
                _uiState.update { it.copy(error = "停止 IDE 异常: ${e.message}") }
            }
        }
    }

    // ==================== 会话管理 ====================

    /**
     * 加载会话列表
     */
    fun loadSessions() {
        viewModelScope.launch {
            _uiState.update { it.copy(loading = true, error = null) }
            try {
                val response = client.get("${getBaseUrl()}/sessions") {
                    val token = _uiState.value.token
                    if (token.isNotBlank()) {
                        header(HttpHeaders.Authorization, token)
                    }
                }
                if (response.status.isSuccess()) {
                    val body = response.bodyAsChannel()
                    val text = StringBuilder()
                    while (!body.isClosedForRead) {
                        val line = body.readUTF8Line() ?: break
                        text.append(line)
                    }
                    val sessions = parseSessions(text.toString())
                    _uiState.update { it.copy(sessions = sessions, loading = false) }
                } else {
                    // 如果获取会话列表失败，不阻塞 UI，仅记录
                    _uiState.update { it.copy(loading = false) }
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(loading = false, error = "加载会话失败: ${e.message}") }
            }
        }
    }

    /**
     * 解析会话列表响应
     */
    private fun parseSessions(responseText: String): List<SessionInfo> {
        return try {
            val jsonElement = json.parseToJsonElement(responseText)
            if (jsonElement is kotlinx.serialization.json.JsonArray) {
                jsonElement.mapNotNull { element ->
                    try {
                        val obj = element as? JsonObject ?: return@mapNotNull null
                        SessionInfo(
                            id = obj["id"]?.jsonPrimitive?.content ?: return@mapNotNull null,
                            title = obj["title"]?.jsonPrimitive?.contentOrNull ?: "",
                            updatedAt = obj["updatedAt"]?.jsonPrimitive?.contentOrNull?.toLongOrNull()
                                ?: obj["updated_at"]?.jsonPrimitive?.contentOrNull?.toLongOrNull()
                                ?: System.currentTimeMillis()
                        )
                    } catch (_: Exception) {
                        null
                    }
                }
            } else {
                emptyList()
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    /**
     * 切换到指定会话
     */
    fun switchSession(sessionId: String) {
        if (_uiState.value.currentSessionId == sessionId) return
        cancelSse()
        _uiState.update {
            it.copy(
                currentSessionId = sessionId,
                messages = emptyList(),
                error = null,
                sending = false
            )
        }
        // 加载会话历史消息
        loadSessionHistory(sessionId)
    }

    /**
     * 新建会话
     */
    fun newSession() {
        cancelSse()
        _uiState.update {
            it.copy(
                currentSessionId = null,
                messages = emptyList(),
                error = null,
                sending = false
            )
        }
    }

    /**
     * 加载会话历史
     */
    private fun loadSessionHistory(sessionId: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(loading = true) }
            try {
                val response = client.get("${getBaseUrl()}/session/$sessionId") {
                    val token = _uiState.value.token
                    if (token.isNotBlank()) {
                        header(HttpHeaders.Authorization, token)
                    }
                }
                if (response.status.isSuccess()) {
                    val historyMessages = mutableListOf<IdeChatMessage>()
                    val body = response.bodyAsChannel()
                    val lineBuffer = StringBuilder()
                    while (!body.isClosedForRead) {
                        val line = body.readUTF8Line() ?: break
                        lineBuffer.append(line)
                    }
                    val messages = parseHistoryMessages(lineBuffer.toString())
                    historyMessages.addAll(messages)
                    _uiState.update { it.copy(messages = historyMessages, loading = false) }
                } else {
                    _uiState.update { it.copy(loading = false) }
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(loading = false, error = "加载历史消息失败: ${e.message}") }
            }
        }
    }

    /**
     * 解析历史消息
     */
    private fun parseHistoryMessages(responseText: String): List<IdeChatMessage> {
        return try {
            val jsonElement = json.parseToJsonElement(responseText)
            when {
                jsonElement is kotlinx.serialization.json.JsonArray -> {
                    jsonElement.mapNotNull { element ->
                        parseMessageFromJson(element as? JsonObject) ?: parseMessageFromRaw(element)
                    }
                }
                jsonElement is JsonObject -> {
                    parseMessageFromJson(jsonElement)?.let { listOf(it) } ?: emptyList()
                }
                else -> emptyList()
            }
        } catch (_: Exception) {
            // 尝试按行解析 NDJSON
            responseText.lines().mapNotNull { line ->
                try {
                    val element = json.parseToJsonElement(line)
                    parseMessageFromJson(element as? JsonObject)
                } catch (_: Exception) {
                    null
                }
            }
        }
    }

    /**
     * 从 JsonObject 解析消息
     */
    private fun parseMessageFromJson(obj: JsonObject?): IdeChatMessage? {
        if (obj == null) return null
        return try {
            val role = obj["role"]?.jsonPrimitive?.content ?: return null
            val content = obj["content"]?.jsonPrimitive?.content ?: ""
            val id = obj["id"]?.jsonPrimitive?.content ?: UUID.randomUUID().toString()
            val timestamp = obj["timestamp"]?.jsonPrimitive?.contentOrNull?.toLongOrNull() ?: System.currentTimeMillis()
            IdeChatMessage(
                id = id,
                role = role,
                content = content,
                timestamp = timestamp,
                isStreaming = false
            )
        } catch (_: Exception) {
            null
        }
    }

    /**
     * 从原始元素解析消息（处理纯文本行）
     */
    private fun parseMessageFromRaw(element: kotlinx.serialization.json.JsonElement): IdeChatMessage? {
        return try {
            val content = element.jsonPrimitive.content
            if (content.isBlank()) return null
            IdeChatMessage(
                role = MessageRole.ASSISTANT.name.lowercase(),
                content = content,
                isStreaming = false
            )
        } catch (_: Exception) {
            null
        }
    }

    // ==================== 消息发送 ====================

    /**
     * 发送消息
     */
    fun send(message: String? = null) {
        val content = (message ?: _uiState.value.input).trim()
        if (content.isBlank()) return
        if (_uiState.value.sending) return
        if (getBaseUrl().isBlank()) {
            _uiState.update { it.copy(error = "未配置服务器地址，请先在设置中配置") }
            return
        }

        // 添加用户消息
        val userMessage = IdeChatMessage(
            role = MessageRole.USER.name.lowercase(),
            content = content,
            isStreaming = false
        )
        _uiState.update {
            it.copy(
                messages = it.messages + userMessage,
                input = "",
                sending = true,
                error = null
            )
        }

        // 添加占位的 assistant 消息（用于流式更新）
        val assistantPlaceholder = IdeChatMessage(
            id = UUID.randomUUID().toString(),
            role = MessageRole.ASSISTANT.name.lowercase(),
            content = "",
            isStreaming = true
        )
        _uiState.update {
            it.copy(messages = it.messages + assistantPlaceholder)
        }

        // 发送请求
        viewModelScope.launch {
            try {
                val requestBody = buildJsonObject {
                    put("message", JsonPrimitive(content))
                    _uiState.value.currentSessionId?.let {
                        put("session_id", JsonPrimitive(it))
                    }
                    _uiState.value.selectedModel?.let {
                        put("model", JsonPrimitive(it))
                    }
                }.toString()

                val response = client.post("${getBaseUrl()}/prompt_async") {
                    contentType(ContentType.Application.Json)
                    setBody(requestBody)
                    val token = _uiState.value.token
                    if (token.isNotBlank()) {
                        header(HttpHeaders.Authorization, token)
                    }
                }

                if (response.status.isSuccess()) {
                    // 启动 SSE 流接收
                    startSseStream()
                } else {
                    val errorBody = response.bodyAsChannel().readUTF8Line() ?: "未知错误"
                    _uiState.update { state ->
                        state.copy(
                            sending = false,
                            error = "发送失败 (${response.status.value}): $errorBody",
                            messages = state.messages.map {
                                if (it.id == assistantPlaceholder.id) {
                                    it.copy(content = "⚠️ 请求失败", isStreaming = false)
                                } else it
                            }
                        )
                    }
                }
            } catch (e: Exception) {
                _uiState.update { state ->
                    state.copy(
                        sending = false,
                        error = "发送异常: ${e.message}",
                        messages = state.messages.map {
                            if (it.id == assistantPlaceholder.id) {
                                it.copy(content = "⚠️ 请求异常: ${e.message}", isStreaming = false)
                            } else it
                        }
                    )
                }
            }
        }
    }

    // ==================== SSE 流式接收 ====================

    /**
     * 启动 SSE 流接收消息
     */
    private fun startSseStream() {
        cancelSse()
        sseJob = viewModelScope.launch {
            try {
                val sseUrl = "${getBaseUrl()}/session/${_uiState.value.currentSessionId ?: "current"}?stream=true"
                client.prepareRequest {
                    url(sseUrl)
                    method = HttpMethod.Get
                    val token = _uiState.value.token
                    if (token.isNotBlank()) {
                        header(HttpHeaders.Authorization, token)
                    }
                }.execute { response ->
                    val channel = response.bodyAsChannel()
                    while (isActive && _uiState.value.sending && !channel.isClosedForRead) {
                        val line = channel.readUTF8Line() ?: break
                        if (line.startsWith("data:")) {
                            val data = line.substringAfter("data:").trim()
                            if (data.isBlank() || data == "[DONE]") continue
                            val parsedContent = parseSseData(data)
                            if (parsedContent != null) {
                                updateAssistantMessage(parsedContent)
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                if (isActive) {
                    _uiState.update { state ->
                        state.copy(
                            sending = false,
                            error = "流式接收错误: ${e.message}",
                            messages = state.messages.map {
                                if (it.isStreaming) it.copy(isStreaming = false) else it
                            }
                        )
                    }
                }
            } finally {
                _uiState.update { state ->
                    state.copy(
                        sending = false,
                        messages = state.messages.map {
                            if (it.isStreaming) it.copy(isStreaming = false) else it
                        }
                    )
                }
            }
        }
    }

    /**
     * 解析 SSE 数据
     */
    private fun parseSseData(data: String): String? {
        return try {
            val jsonElement = json.parseToJsonElement(data)
            if (jsonElement is JsonObject) {
                // 尝试多种常见的 SSE 格式
                jsonElement["content"]?.jsonPrimitive?.contentOrNull
                    ?: jsonElement["delta"]?.let { delta ->
                        (delta as? JsonObject)?.get("content")?.jsonPrimitive?.contentOrNull
                    }
                    ?: jsonElement["text"]?.jsonPrimitive?.contentOrNull
                    ?: jsonElement["message"]?.jsonPrimitive?.contentOrNull
            } else if (jsonElement is JsonPrimitive) {
                jsonElement.contentOrNull
            } else {
                null
            }
        } catch (_: Exception) {
            data.takeIf { it.isNotBlank() }
        }
    }

    /**
     * 更新 assistant 消息内容（流式追加）
     */
    private fun updateAssistantMessage(newContent: String) {
        _uiState.update { state ->
            val messages = state.messages.toMutableList()
            val lastIndex = messages.lastIndex
            if (lastIndex >= 0 && messages[lastIndex].isStreaming) {
                val lastMsg = messages[lastIndex]
                messages[lastIndex] = lastMsg.copy(
                    content = lastMsg.content + newContent
                )
            } else {
                // 如果没有正在流式更新的消息，创建新的
                messages.add(
                    IdeChatMessage(
                        role = MessageRole.ASSISTANT.name.lowercase(),
                        content = newContent,
                        isStreaming = true
                    )
                )
            }
            state.copy(messages = messages)
        }
    }

    /**
     * 取消 SSE 流
     */
    private fun cancelSse() {
        sseJob?.cancel()
        sseJob = null
    }

    // ==================== 生命周期 ====================

    override fun onCleared() {
        super.onCleared()
        cancelSse()
        connectionStatusJob?.cancel()
        client.close()
    }
}

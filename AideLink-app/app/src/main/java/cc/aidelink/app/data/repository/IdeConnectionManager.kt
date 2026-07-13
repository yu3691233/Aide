package cc.aidelink.app.data.repository

import android.util.Log
import cc.aidelink.app.data.api.ServerConnection
import cc.aidelink.app.domain.model.ServerConfig
import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.prepareRequest
import io.ktor.client.request.url
import io.ktor.client.statement.bodyAsChannel
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import io.ktor.utils.io.readUTF8Line
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import javax.inject.Inject
import javax.inject.Singleton

/**
 * IDE 服务器连接状态
 */
enum class ConnectionStatus {
    DISCONNECTED,   // 离线
    CONNECTING,     // 连接中
    CONNECTED,      // 已连接
    RECONNECTING    // 重连中
}

/**
 * IDE 服务器连接生命周期管理器
 *
 * 职责：
 *  - 管理 IDE 服务器的连接/断开/重连
 *  - 健康检查（GET /sessions）
 *  - SSE 事件流监听（GET /event）
 *  - 指数退避自动重连
 *  - 暴露连接状态和 SSE 事件为响应式流
 */
@Singleton
class IdeConnectionManager @Inject constructor() {

    companion object {
        private const val TAG = "IdeConnectionMgr"
        private const val INITIAL_RECONNECT_DELAY_MS = 1_000L
        private const val MAX_RECONNECT_DELAY_MS = 30_000L
        private const val RECONNECT_BACKOFF_MULTIPLIER = 2L
        private const val HEALTH_CHECK_TIMEOUT_MS = 5_000L
    }

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        encodeDefaults = false
    }

    private val client = HttpClient(OkHttp) {
        install(ContentNegotiation) {
            json(json)
        }
        install(HttpTimeout) {
            requestTimeoutMillis = 120_000
            connectTimeoutMillis = HEALTH_CHECK_TIMEOUT_MS
            socketTimeoutMillis = 120_000
        }
        engine {
            config {
                retryOnConnectionFailure(false)
            }
        }
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    // 每个 serverId 对应的 SSE 监听 Job
    private val sseJobs = mutableMapOf<String, Job>()

    // 每个 serverId 对应的重连 Job
    private val reconnectJobs = mutableMapOf<String, Job>()

    // 每个 serverId 对应的连接状态
    private val _connectionStates = MutableStateFlow<Map<String, ConnectionStatus>>(emptyMap())
    val connectionStates: StateFlow<Map<String, ConnectionStatus>> = _connectionStates.asStateFlow()

    // SSE 事件流：Pair<serverId, rawEventData>
    private val _sseEvents = MutableSharedFlow<Pair<String, String>>(extraBufferCapacity = 64)
    val sseEvents: SharedFlow<Pair<String, String>> = _sseEvents.asSharedFlow()

    // ── 公开 API ──────────────────────────────────────────

    /**
     * 健康检查：GET ${server.url}/global/health
     * 使用 ServerConnection 构建正确的 Basic auth 头
     * @return true 表示服务器可达，false 表示不可达
     */
    suspend fun healthCheck(server: ServerConfig): Boolean {
        return try {
            val conn = ServerConnection.from(server.url, server.username, server.password)
            val response = client.get("${conn.baseUrl}/global/health") {
                conn.authHeader?.let { header(HttpHeaders.Authorization, it) }
            }
            response.status.isSuccess()
        } catch (e: Exception) {
            Log.d(TAG, "Health check failed for ${server.url}: ${e.message}")
            false
        }
    }

    /**
     * 连接到指定服务器
     *
     * 流程：CONNECTING → 健康检查 → CONNECTED（启动 SSE）/ DISCONNECTED
     */
    fun connect(serverId: String, server: ServerConfig) {
        // 先取消已有的连接
        disconnect(serverId)

        updateStatus(serverId, ConnectionStatus.CONNECTING)

        scope.launch {
            val healthy = healthCheck(server)
            if (healthy) {
                updateStatus(serverId, ConnectionStatus.CONNECTED)
                startSseStream(serverId, server)
            } else {
                updateStatus(serverId, ConnectionStatus.DISCONNECTED)
                Log.w(TAG, "Health check failed, not starting SSE for $serverId")
            }
        }
    }

    /**
     * 断开指定服务器的连接
     *
     * 取消 SSE 监听和重连任务，状态置为 DISCONNECTED
     */
    fun disconnect(serverId: String) {
        reconnectJobs.remove(serverId)?.cancel()
        sseJobs.remove(serverId)?.cancel()
        updateStatus(serverId, ConnectionStatus.DISCONNECTED)
    }

    /**
     * 释放所有资源，取消所有 Job
     */
    fun close() {
        reconnectJobs.values.forEach { it.cancel() }
        reconnectJobs.clear()
        sseJobs.values.forEach { it.cancel() }
        sseJobs.clear()
        _connectionStates.update { emptyMap() }
        client.close()
    }

    // ── SSE 事件流 ────────────────────────────────────────

    /**
     * 启动 SSE 事件流监听
     *
     * 连接 GET ${server.url}/global/event，逐行解析 "data:" 前缀的事件。
     * 连接断开时触发自动重连。
     */
    private fun startSseStream(serverId: String, server: ServerConfig) {
        sseJobs[serverId]?.cancel()
        sseJobs[serverId] = scope.launch {
            try {
                val conn = ServerConnection.from(server.url, server.username, server.password)
                client.prepareRequest {
                    url("${conn.baseUrl}/global/event")
                    method = HttpMethod.Get
                    conn.authHeader?.let { header(HttpHeaders.Authorization, it) }
                }.execute { response ->
                    val channel = response.bodyAsChannel()
                    while (isActive && !channel.isClosedForRead) {
                        val line = channel.readUTF8Line() ?: break
                        if (line.startsWith("data:")) {
                            val data = line.substringAfter("data:").trim()
                            if (data.isNotBlank() && data != "[DONE]") {
                                _sseEvents.emit(serverId to data)
                            }
                        }
                    }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "SSE stream error for $serverId: ${e.message}")
            } finally {
                // SSE 流结束，如果之前是 CONNECTED 状态则触发重连
                if (_connectionStates.value[serverId] == ConnectionStatus.CONNECTED) {
                    scheduleReconnect(serverId, server)
                }
            }
        }
    }

    // ── 自动重连（指数退避） ──────────────────────────────

    /**
     * 调度自动重连
     *
     * 初始延迟 1 秒，每次翻倍，最大 30 秒。
     * 仅在之前处于 CONNECTED 状态时才重连（手动 disconnect 不会触发）。
     */
    private fun scheduleReconnect(serverId: String, server: ServerConfig) {
        reconnectJobs[serverId]?.cancel()
        updateStatus(serverId, ConnectionStatus.RECONNECTING)

        reconnectJobs[serverId] = scope.launch {
            var delayMs = INITIAL_RECONNECT_DELAY_MS
            while (isActive) {
                Log.d(TAG, "Reconnecting to $serverId in ${delayMs}ms")
                delay(delayMs)

                updateStatus(serverId, ConnectionStatus.CONNECTING)
                val healthy = healthCheck(server)
                if (healthy) {
                    updateStatus(serverId, ConnectionStatus.CONNECTED)
                    startSseStream(serverId, server)
                    return@launch // 重连成功，退出重连循环
                }

                // 重连失败，继续退避
                updateStatus(serverId, ConnectionStatus.RECONNECTING)
                delayMs = (delayMs * RECONNECT_BACKOFF_MULTIPLIER).coerceAtMost(MAX_RECONNECT_DELAY_MS)
            }
        }
    }

    // ── 内部工具 ──────────────────────────────────────────

    private fun updateStatus(serverId: String, status: ConnectionStatus) {
        _connectionStates.update { current ->
            current + (serverId to status)
        }
    }
}

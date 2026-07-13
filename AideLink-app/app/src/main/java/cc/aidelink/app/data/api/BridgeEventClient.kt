package cc.aidelink.app.data.api

import android.util.Log
import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.timeout
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.prepareGet
import io.ktor.client.statement.bodyAsChannel
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpHeaders
import io.ktor.http.isSuccess
import io.ktor.utils.io.readUTF8Line
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 桥接服务器 SSE 客户端
 *
 * 连接 PC 端 phone_chat_bridge.py 的 /events/stream 端点，
 * 消费 EventBus 事件（ide.notification, ide.task_done, task.done 等）。
 *
 * 与 SseClient（连接 OpenCode 的 /global/event）不同，
 * 这个客户端连接的是 AideLink 桥接服务器。
 */
@Singleton
class BridgeEventClient @Inject constructor(
    private val bridgeApi: BridgeApi,
) {
    companion object {
        private const val TAG = "BridgeEventClient"
        private const val RECONNECT_BASE_MS = 1000L
        private const val RECONNECT_MAX_MS = 30_000L
        private const val HEARTBEAT_TIMEOUT_MS = 45_000L
    }

    data class BridgeEvent(
        val id: Long,
        val type: String,
        val timestamp: String,
        val data: Map<String, Any?>,
    )

    private val _events = MutableSharedFlow<BridgeEvent>(
        replay = 0,
        extraBufferCapacity = 64,
    )
    val events: SharedFlow<BridgeEvent> = _events.asSharedFlow()

    private var scope: kotlinx.coroutines.CoroutineScope? = null
    private var connectJob: Job? = null
    private var connected = false
    private var lastEventId: Long = 0

    fun isConnected(): Boolean = connected

    /**
     * 启动 SSE 连接（带自动重连）
     * @param baseUrl 桥接服务器地址
     */
    fun start(baseUrl: String) {
        stop()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        this.scope = scope
        connectJob = scope.launch {
            var retryDelay = RECONNECT_BASE_MS
            while (true) {
                try {
                    val reachableUrl = probeReachableUrl(baseUrl)
                    Log.d(TAG, "Connecting to ${reachableUrl}/events/stream (original: $baseUrl)")

                    // 断网恢复后，先补发错过的事件
                    if (lastEventId > 0) {
                        catchUpMissedEvents(reachableUrl)
                    }

                    connectSse(reachableUrl)
                    retryDelay = RECONNECT_BASE_MS
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    Log.w(TAG, "SSE disconnected: ${e.message}, retry in ${retryDelay}ms")
                }
                connected = false
                delay(retryDelay)
                retryDelay = (retryDelay * 2).coerceAtMost(RECONNECT_MAX_MS)
            }
        }
    }

    /**
     * 断网恢复后，从服务器补发错过的事件
     */
    private suspend fun catchUpMissedEvents(baseUrl: String) {
        try {
            val client = bridgeApi.client
            val resp = client.get("$baseUrl/events/recent?since_id=$lastEventId&limit=50")
            if (resp.status.isSuccess()) {
                val body = resp.bodyAsText()
                val events = kotlinx.serialization.json.Json { ignoreUnknownKeys = true }
                    .decodeFromString<List<Map<String, kotlinx.serialization.json.JsonElement>>>(body)
                for (event in events) {
                    val id = event["id"]?.toString()?.toLongOrNull() ?: continue
                    val type = event["type"]?.toString()?.trim('"') ?: continue
                    val timestamp = event["timestamp"]?.toString()?.trim('"') ?: ""
                    @Suppress("UNCHECKED_CAST")
                    val data = event["data"] as? Map<String, Any?> ?: emptyMap()
                    if (id > lastEventId) {
                        _events.tryEmit(BridgeEvent(id, type, timestamp, data))
                        lastEventId = id
                        Log.d(TAG, "Catch-up event: id=$id type=$type")
                    }
                }
                Log.d(TAG, "Catch-up complete, lastEventId=$lastEventId")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Catch-up failed: ${e.message}")
        }
    }

    /**
     * 探测可达的服务器 URL。
     * 如果 baseUrl 连不上，尝试查询 /server/ips 获取所有 IP，逐个探测。
     */
    private suspend fun probeReachableUrl(baseUrl: String): String {
        // 先尝试原始 baseUrl
        if (isReachable(baseUrl)) {
            return baseUrl
        }
        // 原始连不上，查询服务器所有 IP
        return try {
            val ipsUrl = "$baseUrl/server/ips"
            Log.d(TAG, "Original URL unreachable, querying $ipsUrl")
            val response = bridgeApi.client.get(ipsUrl)
            if (response.status.isSuccess()) {
                val body = response.bodyAsText()
                val json = Json.parseToJsonElement(body).jsonObject
                val ips = json["ips"]?.toString()?.trim('[', ']', '"', ' ')
                    ?.split(",")?.map { it.trim().trim('"') } ?: emptyList()
                Log.d(TAG, "Server IPs: $ips")
                // 逐个尝试，返回第一个能连通的
                for (ip in ips) {
                    val testUrl = "http://$ip:5000"
                    if (isReachable(testUrl)) {
                        Log.i(TAG, "Found reachable URL: $testUrl")
                        return testUrl
                    }
                }
            }
            baseUrl  // 都连不上，返回原始
        } catch (e: Exception) {
            Log.w(TAG, "Failed to query server IPs: ${e.message}")
            baseUrl
        }
    }

    private suspend fun isReachable(url: String): Boolean {
        return try {
            val r = bridgeApi.client.get("$url/ping")
            r.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    fun stop() {
        connectJob?.cancel()
        connectJob = null
        scope?.cancel()
        scope = null
        connected = false
        try {
            sseClient?.close()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to close SSE client: ${e.message}")
        }
        sseClient = null
    }

    private var sseClient: HttpClient? = null

    private fun getSseClient(): HttpClient {
        val existing = sseClient
        if (existing != null) return existing
        val client = HttpClient(OkHttp) {
            install(HttpTimeout) {
                requestTimeoutMillis = HttpTimeout.INFINITE_TIMEOUT_MS
                connectTimeoutMillis = 15_000
                socketTimeoutMillis = HttpTimeout.INFINITE_TIMEOUT_MS
            }
            install(io.ktor.client.plugins.logging.Logging) {
                level = io.ktor.client.plugins.logging.LogLevel.HEADERS
                logger = object : io.ktor.client.plugins.logging.Logger {
                    override fun log(message: String) {
                        Log.d("BridgeEventClient.Http", message)
                    }
                }
            }
            engine {
                config {
                    retryOnConnectionFailure(true)
                    // 禁用系统代理，避免代理拦截局域网请求
                    proxy(java.net.Proxy.NO_PROXY)
                }
            }
        }
        sseClient = client
        return client
    }

    private suspend fun connectSse(baseUrl: String) {
        val url = "$baseUrl/events/stream?types=ide.notification&types=ide.task_done&types=task.done&types=task.failed&types=task.pending_test&types=app.update_available&types=app.command&max_queue=100&idle_timeout=20"
        val client = getSseClient()

        val statement = client.prepareGet(url) {
            header(HttpHeaders.Accept, "text/event-stream")
            header(HttpHeaders.CacheControl, "no-cache")
        }

        statement.execute { response ->
            if (!response.status.isSuccess()) {
                throw RuntimeException("SSE HTTP ${response.status.value}")
            }
            connected = true
            Log.i(TAG, "SSE connected")

            val channel = response.bodyAsChannel()
            var lastData = System.currentTimeMillis()
            val buffer = StringBuilder()

            while (!channel.isClosedForRead) {
                val line = try {
                    channel.readUTF8Line()
                } catch (e: Exception) {
                    null
                }

                if (line == null) {
                    // 连接关闭
                    break
                }

                if (line.startsWith(":")) {
                    // 心跳注释行
                    lastData = System.currentTimeMillis()
                    continue
                }

                if (line.isEmpty()) {
                    // 空行 = 事件分隔符，处理缓冲的事件
                    if (buffer.isNotEmpty()) {
                        val event = parseEvent(buffer.toString())
                        if (event != null) {
                            lastData = System.currentTimeMillis()
                            if (event.id > lastEventId) {
                                lastEventId = event.id
                            }
                            _events.tryEmit(event)
                        }
                        buffer.clear()
                    }
                    continue
                }

                buffer.append(line).append("\n")

                // 心跳超时检查
                if (System.currentTimeMillis() - lastData > HEARTBEAT_TIMEOUT_MS) {
                    Log.w(TAG, "Heartbeat timeout, reconnecting")
                    break
                }
            }
        }
    }

    private fun parseEvent(raw: String): BridgeEvent? {
        var eventType = "message"
        val dataLines = mutableListOf<String>()
        var eventId = 0L
        var timestamp = ""

        for (line in raw.trim().split("\n")) {
            when {
                line.startsWith("event:") -> eventType = line.removePrefix("event:").trim()
                line.startsWith("data:") -> dataLines.add(line.removePrefix("data:").trim())
                line.startsWith("id:") -> eventId = line.removePrefix("id:").trim().toLongOrNull() ?: 0L
                line.startsWith("timestamp:") -> timestamp = line.removePrefix("timestamp:").trim()
            }
        }

        if (dataLines.isEmpty()) return null

        val dataStr = dataLines.joinToString("\n")
        val dataMap = parseDataJson(dataStr)

        return BridgeEvent(
            id = eventId,
            type = eventType,
            timestamp = timestamp,
            data = dataMap,
        )
    }

    private fun parseDataJson(jsonStr: String): Map<String, Any?> {
        return try {
            val element = kotlinx.serialization.json.Json.parseToJsonElement(jsonStr)
            val obj = element.jsonObject

            // 后端 SSE data 行是整个 event JSON：{"id":..., "type":..., "data":{...}}
            // 需要提取嵌套的 "data" 字段作为事件数据
            val dataField = obj["data"]
            val sourceObj = if (dataField is kotlinx.serialization.json.JsonObject) {
                dataField
            } else {
                obj
            }

            sourceObj.entries.associate { (key, value) ->
                key to when {
                    value is kotlinx.serialization.json.JsonPrimitive -> {
                        value.content
                    }
                    value is kotlinx.serialization.json.JsonObject -> value.toString()
                    value is kotlinx.serialization.json.JsonArray -> value.toString()
                    else -> null
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to parse event data JSON: ${e.message}")
            mapOf("raw" to jsonStr)
        }
    }
}

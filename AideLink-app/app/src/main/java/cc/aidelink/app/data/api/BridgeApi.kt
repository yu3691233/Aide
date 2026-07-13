package cc.aidelink.app.data.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.request.delete
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsChannel
import io.ktor.client.statement.bodyAsText
import io.ktor.client.statement.readBytes
import io.ktor.utils.io.readUTF8Line
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.flowOn
import kotlinx.serialization.encodeToString
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import cc.aidelink.app.domain.model.bridge.*

/**
 * AideLink 桥接 API - 调用本机 Flask phone_chat_bridge.py
 *
 * 端点（来自 PC 桥接服务）：
 *   GET  /ping                       → 健康检查
 *   GET  /history?limit=N            → 历史消息
 *   POST /send                       → 发送消息
 *   GET  /sessions                   → IDE 会话列表
 *   GET  /clipboard                  → 剪贴板历史
 *   POST /clipboard/append           → 追加剪贴板
 *   POST /clipboard/clear            → 清空剪贴板
 *   POST /upload                     → 上传图片（multipart）
 *   GET  /screenshot/full            → 全屏截图
 *   GET  /screenshot/crop            → 框选裁剪截图
 *   POST /evolution/submit           → 提交任务给 Aide
 *   GET  /evolution/task/<id>        → 查询任务状态
 *   POST /route                      → 路由决策查询
 *   GET  /scheduler/stats            → 调度器统计
 */
class BridgeApi(
    var baseUrl: String,
    private val authToken: String? = null,
) {
    var deviceIp: String? = null
    var deviceSerial: String? = null
    private fun normalizeWindowsPath(path: String): String = path.trim().replace('/', '\\')
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        encodeDefaults = true
    }

    val client: HttpClient = HttpClient(OkHttp) {
        install(ContentNegotiation) {
            json(json)
        }
        install(HttpTimeout) {
            requestTimeoutMillis = 45_000
            connectTimeoutMillis = 5_000
            socketTimeoutMillis = 45_000
        }
        defaultRequest {
            contentType(ContentType.Application.Json)
            authToken?.let { header(HttpHeaders.Authorization, "Bearer $it") }
            deviceIp?.let { header("X-Device-IP", it) }
            deviceSerial?.let { header("X-Device-Serial", it) }
        }
        expectSuccess = false
    }

    // 子 API 实例（延迟初始化）
    private val messageApi by lazy { BridgeMessageApi(client, baseUrl) }
    private val screenshotApi by lazy { BridgeScreenshotApi(client, baseUrl) }
    private val taskApi by lazy { BridgeTaskApi(client, baseUrl) }
    private val settingsApi by lazy { BridgeSettingsApi(client, baseUrl) }
    private val projectApi by lazy { BridgeProjectApi(client, baseUrl) }
    private val uiLocatorApi by lazy { BridgeUiLocatorApi(client, baseUrl) }
    private val screenApi by lazy { BridgeScreenApi(client, baseUrl) }
    private val ideApi by lazy { BridgeIdeApi(client, baseUrl) }
    private val mimoApi by lazy { BridgeMimoApi(client, baseUrl) }
    private val ocWebApi by lazy { BridgeOcWebApi(client, baseUrl) }
    private val appApi by lazy { BridgeAppApi(client, baseUrl) }

    fun updateBaseUrl(newUrl: String) {
        this.baseUrl = newUrl
    }

    // ─── 健康检查 ─────────────────────────────────────────────

    suspend fun ping(): Boolean = runCatching {
        val r = client.get("$baseUrl/ping")
        r.status.isSuccess()
    }.getOrDefault(false)

    suspend fun ping(url: String): Boolean = runCatching {
        val r = client.get("${url.trimEnd('/')}/ping")
        r.status.isSuccess()
    }.getOrDefault(false)

    // ─── 消息 ─────────────────────────────────────────────────

    suspend fun fetchHistory(limit: Int = 50): List<ChatMessage> {
        return try {
            val resp = client.get("$baseUrl/history") {
                parameter("limit", limit)
            }
            if (!resp.status.isSuccess()) return emptyList()
            runCatching {
                json.decodeFromString(
                    kotlinx.serialization.builtins.ListSerializer(ChatMessage.serializer()),
                    resp.bodyAsText()
                )
            }.getOrDefault(emptyList())
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun send(
        text: String,
        target: String = "auto",
        imagePath: String? = null,

        taskId: String? = null,
    ): SendResponse = try {
        val resp = client.post("$baseUrl/send") {
            setBody(SendRequest(text = text, target = target, image = imagePath, task_id = taskId))
        }
        val raw = resp.bodyAsText()
        runCatching {
            json.decodeFromString(SendResponse.serializer(), raw)
        }.getOrElse { SendResponse(ok = resp.status.isSuccess(), raw = raw) }
    } catch (e: Exception) {
        SendResponse(ok = false, raw = e.message ?: "Network error")
    }

    /**
     * 流式发送消息，返回 SSE 事件流。
     * 每个事件是 map：{"type": "delta"|"thinking"|"done"|"error", "content": "..."}
     * 使用 HttpURLConnection 确保真流式读取，避免 OkHttp/Ktor 缓冲整个响应。
     */
    fun sendStream(
        text: String,
        target: String = "auto",
        imagePath: String? = null,
    ): kotlinx.coroutines.flow.Flow<Map<String, Any?>> = kotlinx.coroutines.flow.flow {
        var conn: java.net.HttpURLConnection? = null
        try {
            val url = java.net.URL("$baseUrl/send/stream")
            conn = (url.openConnection() as java.net.HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 10_000
                readTimeout = 120_000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                authToken?.let { setRequestProperty("Authorization", "Bearer $it") }
                deviceIp?.let { setRequestProperty("X-Device-IP", it) }
                deviceSerial?.let { setRequestProperty("X-Device-Serial", it) }
            }
            // 发送请求体
            val bodyJson = json.encodeToString(SendRequest.serializer(), SendRequest(text = text, target = target, image = imagePath))
            conn.outputStream.use { it.write(bodyJson.toByteArray(Charsets.UTF_8)) }

            val responseCode = conn.responseCode
            if (responseCode !in 200..299) {
                emit(mapOf("type" to "error", "error" to "HTTP $responseCode"))
                return@flow
            }

            // 逐行流式读取 SSE
            val reader = java.io.BufferedReader(java.io.InputStreamReader(conn.inputStream, Charsets.UTF_8))
            var buffer = StringBuilder()
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isEmpty()) {
                    // 空行 = SSE block 分隔符
                    val block = buffer.toString().trim()
                    buffer = StringBuilder()
                    if (block.startsWith("data: ")) {
                        val jsonStr = block.removePrefix("data: ").trim()
                        if (jsonStr.isNotEmpty() && jsonStr != "[DONE]") {
                            runCatching {
                                val obj = json.parseToJsonElement(jsonStr).jsonObject
                                val map = mutableMapOf<String, Any?>()
                                obj.forEach { (k, v) ->
                                    map[k] = when {
                                        v is kotlinx.serialization.json.JsonPrimitive -> v.contentOrNull
                                        else -> null
                                    }
                                }
                                emit(map)
                            }
                        }
                    }
                } else {
                    if (buffer.isNotEmpty()) buffer.append('\n')
                    buffer.append(line)
                }
            }
            // 处理最后一个未以空行结尾的 block
            val block = buffer.toString().trim()
            if (block.startsWith("data: ")) {
                val jsonStr = block.removePrefix("data: ").trim()
                if (jsonStr.isNotEmpty() && jsonStr != "[DONE]") {
                    runCatching {
                        val obj = json.parseToJsonElement(jsonStr).jsonObject
                        val map = mutableMapOf<String, Any?>()
                        obj.forEach { (k, v) ->
                            map[k] = when {
                                v is kotlinx.serialization.json.JsonPrimitive -> v.contentOrNull
                                else -> null
                            }
                        }
                        emit(map)
                    }
                }
            }
        } catch (e: Exception) {
            emit(mapOf("type" to "error", "error" to (e.message ?: "网络错误")))
        } finally {
            conn?.disconnect()
        }
    }.flowOn(Dispatchers.IO)

    // ─── 会话 ─────────────────────────────────────────────────

    suspend fun fetchSessions(): List<IdeSession> {
        return try {
            val resp = client.get("$baseUrl/sessions")
            if (!resp.status.isSuccess()) return emptyList()
            runCatching {
                json.decodeFromString(
                    kotlinx.serialization.builtins.ListSerializer(IdeSession.serializer()),
                    resp.bodyAsText()
                )
            }.getOrDefault(emptyList())
        } catch (e: Exception) {
            emptyList()
        }
    }

    // ─── 剪贴板 ───────────────────────────────────────────────

    suspend fun fetchClipboard(): List<ClipboardItem> {
        return try {
            val resp = client.get("$baseUrl/clipboard")
            if (!resp.status.isSuccess()) return emptyList()
            runCatching {
                json.decodeFromString(
                    kotlinx.serialization.builtins.ListSerializer(ClipboardItem.serializer()),
                    resp.bodyAsText()
                )
            }.getOrDefault(emptyList())
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun appendClipboard(text: String): Boolean = try {
        val resp = client.post("$baseUrl/clipboard/append") {
            setBody(ClipboardAppendRequest(text = text))
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun clearClipboard(): Boolean = try {
        val resp = client.post("$baseUrl/clipboard/clear")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    // ─── IDE 租约管理 ─────────────────────────────────────────────

    /**
     * 释放IDE租约（解锁）
     * @param ide IDE名称（如 "opencode", "mimocode"）
     * @return 是否成功
     */
    suspend fun ideRelease(ide: String): Boolean = runCatching {
        val resp = client.post("$baseUrl/ide/$ide/release") {
            setBody("{}")
        }
        resp.status.isSuccess()
    }.getOrDefault(false)

    // ─── 上传 ─────────────────────────────────────────────────

    suspend fun uploadImage(filePath: String, filename: String, toClipboard: Boolean = false): UploadResponse = try {
        val resp = client.post("$baseUrl/upload") {
            setBody(
                MultiPartFormDataContent(
                    formData {
                        append("file", java.io.File(filePath).readBytes(), io.ktor.http.Headers.build {
                            append(HttpHeaders.ContentType, ContentType.Image.Any.toString())
                            append(HttpHeaders.ContentDisposition, "filename=\"$filename\"")
                        })
                        if (toClipboard) {
                            append("to_clipboard", "true")
                        }
                    }
                )
            )
        }
        val raw = resp.bodyAsText()
        runCatching {
            json.decodeFromString(UploadResponse.serializer(), raw)
        }.getOrElse { UploadResponse(ok = resp.status.isSuccess(), raw = raw) }
    } catch (e: Exception) {
        UploadResponse(ok = false, raw = e.message ?: "Network error")
    }

    // ─── 截图 ─────────────────────────────────────────────────

    suspend fun screenshotFull(target: String? = null, monitor: String? = null, fullMonitor: Boolean = false): ByteArray? {
        return try {
            val resp: HttpResponse = client.get("$baseUrl/screenshot/full") {
                target?.let { parameter("target", it) }
                monitor?.let { parameter("monitor", it) }
                if (fullMonitor) {
                    parameter("full_monitor", "true")
                }
            }
            if (!resp.status.isSuccess()) null else resp.readBytes()
        } catch (e: Exception) {
            null
        }
    }

    suspend fun screenshotFullWithStatus(target: String? = null, monitor: String? = null, fullMonitor: Boolean = false): Pair<ByteArray?, Boolean> {
        return try {
            val resp: HttpResponse = client.get("$baseUrl/screenshot/full") {
                target?.let { parameter("target", it) }
                monitor?.let { parameter("monitor", it) }
                if (fullMonitor) {
                    parameter("full_monitor", "true")
                }
            }
            val bytes = if (!resp.status.isSuccess()) null else resp.readBytes()
            val windowFound = resp.headers["X-Window-Found"] == "true"
            Pair(bytes, windowFound)
        } catch (e: Exception) {
            Pair(null, false)
        }
    }

    suspend fun screenshotCrop(
        x: Int,
        y: Int,
        width: Int,
        height: Int,
        target: String? = null,
    ): ByteArray? {
        return try {
            val resp = client.get("$baseUrl/screenshot/crop") {
                parameter("x", x); parameter("y", y)
                parameter("w", width); parameter("h", height)
                target?.let { parameter("target", it) }
            }
            if (!resp.status.isSuccess()) null else resp.readBytes()
        } catch (e: Exception) {
            null
        }
    }

    suspend fun screenshotCropByConfig(target: String, monitor: String? = null): ByteArray? {
        return try {
            val resp = client.get("$baseUrl/screenshot/crop") {
                parameter("target", target)
                monitor?.let { parameter("monitor", it) }
            }
            if (!resp.status.isSuccess()) null else resp.readBytes()
        } catch (e: Exception) {
            null
        }
    }
    suspend fun focusTargetInput(target: String): Boolean = try {
        val resp = client.post("$baseUrl/window/focus-input") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("target" to target))
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun focusTargetWindow(target: String): Boolean = try {
        val resp = client.post("$baseUrl/window/focus") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("target" to target))
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun maximizeTargetWindow(target: String): Boolean = try {
        val resp = client.post("$baseUrl/window/maximize") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("target" to target))
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun fetchTargetWindowInfo(target: String): WindowInfo? {
        return try {
            val resp = client.get("$baseUrl/window/info") {
                parameter("target", target)
            }
            if (!resp.status.isSuccess()) return null
            runCatching {
                json.decodeFromString(WindowInfoResponse.serializer(), resp.bodyAsText()).window
            }.getOrNull()
        } catch (e: Exception) {
            null
        }
    }

    suspend fun fetchCropConfigs(): Map<String, CropConfig> {
        return try {
            val resp = client.get("$baseUrl/screenshot/crop") {
                parameter("action", "config")
            }
            if (!resp.status.isSuccess()) return emptyMap()
            runCatching {
                json.decodeFromString<Map<String, CropConfig>>(resp.bodyAsText())
            }.getOrDefault(emptyMap())
        } catch (e: Exception) {
            emptyMap()
        }
    }

    suspend fun fetchMonitors(): List<MonitorInfo> {
        return try {
            val resp = client.get("$baseUrl/screenshot/crop") {
                parameter("action", "monitors")
            }
            if (!resp.status.isSuccess()) return emptyList()
            runCatching {
                json.decodeFromString(MonitorsResponse.serializer(), resp.bodyAsText()).monitors
            }.getOrDefault(emptyList())
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun fetchActiveCropConfig(target: String, monitor: String? = null): CropConfig? {
        return try {
            val resp = client.get("$baseUrl/screenshot/crop") {
                parameter("action", "active_config")
                parameter("target", target)
                monitor?.let { parameter("monitor", it) }
            }
            if (!resp.status.isSuccess()) return null
            val body = resp.bodyAsText()
            runCatching {
                json.decodeFromString<ActiveCropConfigResponse>(body).config
            }.getOrNull()
        } catch (e: Exception) {
            null
        }
    }

    suspend fun saveCropConfig(
        target: String,
        left: Int,
        right: Int,
        top: Int,
        bottom: Int,
        monitor: String? = null,
        dialogPosition: String? = null,
        calibWidth: Int? = null,
        calibHeight: Int? = null,
    ): Boolean = try {
        val resp = client.post("$baseUrl/screenshot/crop") {
            contentType(ContentType.Application.Json)
            setBody(CropSaveRequest(target, left, right, top, bottom, monitor, dialogPosition, calibWidth, calibHeight))
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    // ─── Aide（进化引擎）─────────────────────────────────────

    suspend fun submitAideLinkTask(
        message: String,
        taskType: String = "code",
        async: Boolean = false,
    ): AideLinkTaskResponse = try {
        val resp = client.post("$baseUrl/evolution/submit") {
            setBody(
                AideLinkSubmitRequest(
                    message = message,
                    task_type = taskType,
                    async = async,
                )
            )
        }
        val raw = resp.bodyAsText()
        runCatching {
            json.decodeFromString(AideLinkTaskResponse.serializer(), raw)
        }.getOrElse { AideLinkTaskResponse(ok = resp.status.isSuccess(), raw = raw) }
    } catch (e: Exception) {
        AideLinkTaskResponse(ok = false, raw = e.message ?: "Network error")
    }

    suspend fun queryAideLinkTask(taskId: String): String = try {
        val resp = client.get("$baseUrl/evolution/task/$taskId")
        resp.bodyAsText()
    } catch (e: Exception) {
        ""
    }

    // ─── 调度器统计 ───────────────────────────────────────────

    suspend fun schedulerStats(): String = try {
        val resp = client.get("$baseUrl/scheduler/stats")
        resp.bodyAsText()
    } catch (e: Exception) {
        ""
    }

    // ─── 获取可用模型列表 ─────────────────────────────────────

    suspend fun fetchActiveModels(): List<ActiveModel> {
        return try {
            val resp = client.get("$baseUrl/api/active-models")
            if (!resp.status.isSuccess()) return emptyList()
            runCatching {
                json.decodeFromString(ActiveModelsResponse.serializer(), resp.bodyAsText()).models
            }.getOrDefault(emptyList())
        } catch (e: Exception) {
            emptyList()
        }
    }

    // ─── 桌面 IDE 管理 ─────────────────────────────────────

    suspend fun fetchDesktopIdes(): List<DesktopIde> {
        return try {
            val resp = client.get("$baseUrl/api/desktop-ides")
            if (!resp.status.isSuccess()) return emptyList()
            runCatching {
                json.decodeFromString(DesktopIdesResponse.serializer(), resp.bodyAsText()).ides
            }.getOrDefault(emptyList())
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun scanIdes(): List<DesktopIde> {
        return try {
            val resp = client.post("$baseUrl/api/scan-ides")
            if (!resp.status.isSuccess()) return emptyList()
            runCatching {
                json.decodeFromString(DesktopIdesResponse.serializer(), resp.bodyAsText()).ides
            }.getOrDefault(emptyList())
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun browsePath(title: String = "选择 IDE 可执行文件", startDir: String? = null): String? {
        return try {
            val body = buildJsonObject {
                put("title", title)
                if (!startDir.isNullOrBlank()) put("start_dir", startDir)
            }
            val resp = client.post("$baseUrl/api/browse-path") {
                contentType(ContentType.Application.Json)
                setBody(body.toString())
            }
            if (!resp.status.isSuccess()) return null
            val text = resp.bodyAsText()
            val obj = runCatching { Json.parseToJsonElement(text).jsonObject }.getOrNull() ?: return null
            if (obj["ok"]?.toString()?.trim('"') == "true") {
                obj["path"]?.toString()?.trim('"')
            } else null
        } catch (e: Exception) {
            null
        }
    }

    suspend fun saveManualIde(ide: DesktopIde): Boolean = try {
        val body = buildJsonObject {
            put("key", ide.key)
            put("name", ide.name)
            put("path", ide.path)
        }
        val resp = client.post("$baseUrl/api/manual-ides") {
            contentType(ContentType.Application.Json)
            setBody(body.toString())
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun removeManualIde(key: String): Boolean = try {
        val body = buildJsonObject {
            put("key", key)
        }
        val resp = client.delete("$baseUrl/api/manual-ides") {
            contentType(ContentType.Application.Json)
            setBody(body.toString())
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    // ─── Aide MiMoCode 启停 ──────────────────────────────────

    suspend fun fetchMimoStatus(): MimoStatusResponse? {
        return try {
            val resp = client.get("$baseUrl/xiaomengling/mimo/status")
            if (!resp.status.isSuccess()) return null
            runCatching {
                json.decodeFromString(MimoStatusResponse.serializer(), resp.bodyAsText())
            }.getOrNull()
        } catch (e: Exception) {
            null
        }
    }

    suspend fun startMimo(): Boolean = try {
        val resp = client.post("$baseUrl/xiaomengling/mimo/start")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun stopMimo(): Boolean = try {
        val resp = client.post("$baseUrl/xiaomengling/mimo/stop")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    // ─── Aide 模型列表 ──────────────────────────────────────

    suspend fun fetchMimoModels(): MimoModelsEnvelope {
        return try {
            val resp = client.get("$baseUrl/xiaomengling/models")
            if (!resp.status.isSuccess()) return MimoModelsEnvelope()
            runCatching {
                json.decodeFromString<MimoModelsEnvelope>(resp.bodyAsText())
            }.getOrDefault(MimoModelsEnvelope())
        } catch (e: Exception) {
            MimoModelsEnvelope()
        }
    }

    suspend fun setMimoModel(modelId: String, providerId: String = ""): Boolean = try {
        val resp = client.post("$baseUrl/xiaomengling/models/set") {
            contentType(ContentType.Application.Json)
            setBody("""{"model_id":"$modelId","provider_id":"$providerId"}""")
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun fetchMimoWebUrl(): MimoWebUrlResponse {
        return try {
            val resp = client.get("$baseUrl/xiaomengling/mimo/weburl")
            if (!resp.status.isSuccess()) return MimoWebUrlResponse()
            runCatching {
                json.decodeFromString<MimoWebUrlResponse>(resp.bodyAsText())
            }.getOrDefault(MimoWebUrlResponse())
        } catch (e: Exception) {
            MimoWebUrlResponse()
        }
    }

    suspend fun createNewSession(): NewSessionResponse {
        return try {
            val resp = client.post("$baseUrl/xiaomengling/session/new")
            if (!resp.status.isSuccess()) return NewSessionResponse()
            runCatching {
                json.decodeFromString<NewSessionResponse>(resp.bodyAsText())
            }.getOrDefault(NewSessionResponse())
        } catch (e: Exception) {
            NewSessionResponse()
        }
    }

    // ─── 手机设置双向同步 ─────────────────────────────────────

    suspend fun fetchSettings(): SettingsPayload? {
        return try {
            val resp = client.get("$baseUrl/settings")
            if (!resp.status.isSuccess()) return null
            runCatching {
                json.decodeFromString(SettingsEnvelope.serializer(), resp.bodyAsText()).settings
            }.getOrNull()
        } catch (e: Exception) {
            null
        }
    }

    /** 拉取桥接服务通过可选隧道暴露的公网访问地址，供 App 直连 */
    suspend fun fetchFrpPublicUrl(): String? {
        return try {
            val resp = client.get("$baseUrl/api/frp/status")
            if (!resp.status.isSuccess()) return null
            val obj = json.parseToJsonElement(resp.bodyAsText()).jsonObject
            obj["public_url"]?.jsonPrimitive?.contentOrNull?.takeIf { it.isNotBlank() }
        } catch (e: Exception) {
            null
        }
    }

    suspend fun patchSetting(key: String, value: kotlinx.serialization.json.JsonElement): Boolean = try {
        val payload = kotlinx.serialization.json.JsonObject(mapOf(key to value))
        val resp = client.post("$baseUrl/settings") {
            contentType(ContentType.Application.Json)
            setBody(payload)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun patchSetting(body: kotlinx.serialization.json.JsonObject): Boolean = try {
        val resp = client.post("$baseUrl/settings") {
            contentType(ContentType.Application.Json)
            setBody(body)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    // ─── OC Web 服务管理 ─────────────────────────────────────────

    suspend fun getOcWebStatus(): OcWebStatus = try {
        val resp = client.get("$baseUrl/api/oc-web/status")
        if (!resp.status.isSuccess()) OcWebStatus()
        else runCatching { json.decodeFromString<OcWebStatus>(resp.bodyAsText()) }.getOrDefault(OcWebStatus())
    } catch (e: Exception) {
        OcWebStatus()
    }

    suspend fun startOcWeb(): OcWebActionResult = try {
        val resp = client.post("$baseUrl/api/oc-web/start")
        runCatching { json.decodeFromString<OcWebActionResult>(resp.bodyAsText()) }
            .getOrDefault(OcWebActionResult(ok = false, error = "解析失败"))
    } catch (e: Exception) {
        OcWebActionResult(ok = false, error = e.message)
    }

    suspend fun stopOcWeb(): OcWebActionResult = try {
        val resp = client.post("$baseUrl/api/oc-web/stop")
        runCatching { json.decodeFromString<OcWebActionResult>(resp.bodyAsText()) }
            .getOrDefault(OcWebActionResult(ok = false, error = "解析失败"))
    } catch (e: Exception) {
        OcWebActionResult(ok = false, error = e.message)
    }

    suspend fun getOcWebLatestReply(): OcWebLatestReply = try {
        val resp = client.get("$baseUrl/api/oc-web/latest-reply")
        if (!resp.status.isSuccess()) OcWebLatestReply()
        else runCatching { json.decodeFromString<OcWebLatestReply>(resp.bodyAsText()) }.getOrDefault(OcWebLatestReply())
    } catch (e: Exception) {
        OcWebLatestReply()
    }

    // ─── 项目管理 ───────────────────────────────────────────

    @kotlinx.serialization.Serializable
    data class AndroidApkInfo(
        val path: String = "",
        val name: String = "",
        val module: String = "",
        val variant: String = "",
        val application_id: String = "",
        val modified_at: Long = 0,
        val size: Long = 0,
    )

    @kotlinx.serialization.Serializable
    data class AndroidProjectInfo(
        val is_android: Boolean = false,
        val android_roots: List<String> = emptyList(),
        val apks: List<AndroidApkInfo> = emptyList(),
        val primary_apk: String = "",
    )

    @kotlinx.serialization.Serializable
    data class ProjectInfo(
        val path: String = "",
        val name: String = "",
        val last_used: String = "",
        val android: AndroidProjectInfo = AndroidProjectInfo(),
    )

    @kotlinx.serialization.Serializable
    data class ProjectsResponse(val projects: List<ProjectInfo> = emptyList(), val current_project: String = "")

    suspend fun getProjects(): ProjectsResponse = try {
        val resp = client.get("$baseUrl/api/projects")
        if (!resp.status.isSuccess()) ProjectsResponse()
        else runCatching { json.decodeFromString<ProjectsResponse>(resp.bodyAsText()) }.getOrDefault(ProjectsResponse())
    } catch (e: Exception) { ProjectsResponse() }

    suspend fun selectProject(path: String): Boolean = try {
        val resp = client.post("$baseUrl/api/projects/select") {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject { put("path", normalizeWindowsPath(path)) }.toString())
        }
        resp.status.isSuccess()
    } catch (e: Exception) { false }

    suspend fun deleteProject(idx: Int): Boolean = try {
        val resp = client.delete("$baseUrl/api/projects/$idx")
        resp.status.isSuccess()
    } catch (e: Exception) { false }

    suspend fun scanAndroidProject(path: String): Boolean = try {
        val resp = client.post("$baseUrl/api/projects/android/scan") {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject { put("path", path) }.toString())
        }
        resp.status.isSuccess()
    } catch (e: Exception) { false }

    suspend fun browseProjectFolder(startDir: String = ""): String? = try {
        val resp = client.post("$baseUrl/api/browse-folder") {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject { if (startDir.isNotBlank()) put("start_dir", startDir) }.toString())
        }
        if (!resp.status.isSuccess()) null
        else Json.parseToJsonElement(resp.bodyAsText()).jsonObject["path"]?.jsonPrimitive?.contentOrNull
    } catch (e: Exception) { null }

    // ─── 屏幕控制 ───────────────────────────────────────────

    suspend fun wakeScreen(): WakeResult = try {
        val resp = client.post("$baseUrl/screen/wake")
        if (!resp.status.isSuccess()) {
            WakeResult(ok = false, reason = "HTTP ${resp.status.value}")
        } else {
            runCatching {
                Json.decodeFromString<WakeResult>(resp.bodyAsText())
            }.getOrDefault(WakeResult(ok = true))
        }
    } catch (e: Exception) {
        WakeResult(ok = false, reason = e.message)
    }

    suspend fun ensureScreenUnlocked(): WakeResult = try {
        val resp = client.post("$baseUrl/screen/ensure-unlocked")
        if (!resp.status.isSuccess()) {
            WakeResult(ok = false, reason = "HTTP ${resp.status.value}")
        } else {
            runCatching {
                Json.decodeFromString<WakeResult>(resp.bodyAsText())
            }.getOrDefault(WakeResult(ok = true))
        }
    } catch (e: Exception) {
        WakeResult(ok = false, reason = e.message)
    }

    // ─── IDE 远程启动/停止 ─────────────────────────────────────

    suspend fun startIde(ide: String): Boolean = try {
        val resp = client.post("$baseUrl/ide/$ide/start")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun stopIde(ide: String): Boolean = try {
        val resp = client.post("$baseUrl/ide/$ide/stop")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun getDesktopIdes(): List<DesktopIde> = try {
        val resp = client.get("$baseUrl/api/desktop-ides")
        if (!resp.status.isSuccess()) emptyList()
        else runCatching {
            val body = resp.bodyAsText()
            Json.decodeFromString<DesktopIdesResponse>(body).ides
        }.getOrNull() ?: emptyList()
    } catch (e: Exception) {
        emptyList()
    }

    suspend fun getIdeProcesses(): List<DesktopIde> = try {
        val resp = client.get("$baseUrl/ide/processes")
        if (!resp.status.isSuccess()) emptyList()
        else runCatching {
            val body = resp.bodyAsText()
            Json.decodeFromString<IdeProcessesResponse>(body).ides
        }.getOrNull() ?: emptyList()
    } catch (e: Exception) {
        emptyList()
    }

    suspend fun getScreenStatus(): ScreenStatus = try {
        val resp = client.get("$baseUrl/screen/status")
        if (!resp.status.isSuccess()) ScreenStatus()
        else runCatching {
            Json.decodeFromString<ScreenStatus>(resp.bodyAsText())
        }.getOrDefault(ScreenStatus())
    } catch (e: Exception) {
        ScreenStatus()
    }

    suspend fun setScreenSettings(autoSkipLock: Boolean): Boolean = try {
        val resp = client.post("$baseUrl/screen/settings") {
            contentType(ContentType.Application.Json)
            setBody("""{"auto_skip_lock": $autoSkipLock}""")
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    // ─── 项目地图 ─────────────────────────────────────────────

    suspend fun fetchProjectMap(onlyVisible: Boolean = false): ProjectMapResponse {
        return try {
            val resp = client.get("$baseUrl/project-map") {
                parameter("only_visible", onlyVisible)
            }
            if (!resp.status.isSuccess()) return ProjectMapResponse()
            runCatching {
                json.decodeFromString<ProjectMapResponse>(resp.bodyAsText())
            }.getOrDefault(ProjectMapResponse())
        } catch (e: Exception) {
            ProjectMapResponse()
        }
    }

    suspend fun scanProjectMap(onlyVisible: Boolean = false): ProjectMapResponse {
        return try {
            val resp = client.post("$baseUrl/project-map/scan") {
                parameter("only_visible", onlyVisible)
            }
            if (!resp.status.isSuccess()) return ProjectMapResponse()
            runCatching {
                json.decodeFromString<ProjectMapResponse>(resp.bodyAsText())
            }.getOrDefault(ProjectMapResponse())
        } catch (e: Exception) {
            ProjectMapResponse()
        }
    }

    suspend fun injectClipboard(target: String): Boolean = try {
        val resp = client.post("$baseUrl/inject-clipboard") {
            setBody(buildJsonObject { put("target", target) })
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun captureUiLocator(): UiLocatorCaptureResponse {
        return try {
            val resp = client.post("$baseUrl/ui-locator/capture")
            val raw = resp.bodyAsText()
            runCatching {
                json.decodeFromString<UiLocatorCaptureResponse>(raw)
            }.getOrDefault(UiLocatorCaptureResponse(error = "HTTP ${resp.status.value}: $raw"))
        } catch (e: Exception) {
            UiLocatorCaptureResponse(error = e.message ?: "Network error")
        }
    }

    suspend fun locateUiElement(x: Int, y: Int, width: Int, height: Int): UiLocatorLocateResponse {
        return try {
            val resp = client.post("$baseUrl/ui-locator/locate") {
                setBody(UiLocatorLocateRequest(x, y, width, height))
            }
            if (!resp.status.isSuccess()) return UiLocatorLocateResponse(error = "HTTP ${resp.status.value}")
            runCatching {
                json.decodeFromString<UiLocatorLocateResponse>(resp.bodyAsText())
            }.getOrDefault(UiLocatorLocateResponse(error = "Decode failed"))
        } catch (e: Exception) {
            UiLocatorLocateResponse(error = e.message ?: "Network error")
        }
    }

    suspend fun lockProjectFeature(
        nodeId: String,
        nodeName: String,
        file: String,
        symbol: String,
        version: String,
        description: String,
    ): ProjectLockResponse {
        return try {
            val resp = client.post("$baseUrl/project-map/lock") {
                setBody(ProjectLockRequest(nodeId, nodeName, file, symbol, version, description))
            }
            if (!resp.status.isSuccess()) return ProjectLockResponse(error = "HTTP ${resp.status.value}")
            runCatching {
                json.decodeFromString<ProjectLockResponse>(resp.bodyAsText())
            }.getOrDefault(ProjectLockResponse(error = "Decode failed"))
        } catch (e: Exception) {
            ProjectLockResponse(error = e.message ?: "Network error")
        }
    }

    suspend fun patchSetting(key: String, value: Any): Boolean = when (value) {
        is Boolean -> patchSetting(key, kotlinx.serialization.json.JsonPrimitive(value))
        is Int -> patchSetting(key, kotlinx.serialization.json.JsonPrimitive(value))
        is Long -> patchSetting(key, kotlinx.serialization.json.JsonPrimitive(value))
        is String -> patchSetting(key, kotlinx.serialization.json.JsonPrimitive(value))
        else -> false
    }

    suspend fun reportAdbStatus(ip: String, port: Int, enabled: Boolean): Boolean = try {
        val body = buildJsonObject {
            put("ip", ip)
            put("port", port)
            put("enabled", enabled)
        }
        val resp = client.post("$baseUrl/api/adb/report") {
            contentType(ContentType.Application.Json)
            setBody(body.toString())
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    // ─── App 更新 ─────────────────────────────────────────────

    suspend fun fetchAppVersion(): AppVersionResponse {
        return try {
            val resp = client.get("$baseUrl/app/version")
            if (!resp.status.isSuccess()) {
                return AppVersionResponse(ok = false, error = "HTTP ${resp.status.value}")
            }
            runCatching {
                json.decodeFromString<AppVersionResponse>(resp.bodyAsText())
            }.getOrDefault(AppVersionResponse(ok = false, error = "JSON 解析失败"))
        } catch (e: Exception) {
            AppVersionResponse(ok = false, error = e.message ?: "网络错误")
        }
    }

    suspend fun adbSelfInstall(port: Int = 0): AdbInstallResponse {
        return try {
            val body = buildJsonObject {
                deviceIp?.let { put("ip", it) }
                if (port > 0) put("port", port)
            }
            val resp = client.post("$baseUrl/api/adb/self-install") {
                contentType(io.ktor.http.ContentType.Application.Json)
                setBody(body.toString())
            }
            if (!resp.status.isSuccess()) {
                return AdbInstallResponse(ok = false, error = "HTTP ${resp.status.value}")
            }
            runCatching {
                json.decodeFromString<AdbInstallResponse>(resp.bodyAsText())
            }.getOrDefault(AdbInstallResponse(ok = false, error = "JSON 解析失败"))
        } catch (e: Exception) {
            AdbInstallResponse(ok = false, error = e.message ?: "网络错误")
        }
    }

    suspend fun adbProjectInstall(projectPath: String, apkPath: String, port: Int = 0): AdbInstallResponse {
        return try {
            val body = buildJsonObject {
                deviceIp?.let { put("ip", it) }
                if (port > 0) put("port", port)
                put("project_path", projectPath)
                if (apkPath.isNotBlank()) put("apk_path", apkPath)
            }
            val resp = client.post("$baseUrl/api/adb/project-install") {
                contentType(io.ktor.http.ContentType.Application.Json)
                setBody(body.toString())
            }
            runCatching {
                json.decodeFromString<AdbInstallResponse>(resp.bodyAsText())
            }.getOrDefault(AdbInstallResponse(ok = false, error = "响应解析失败"))
        } catch (e: Exception) {
            AdbInstallResponse(ok = false, error = e.message ?: "网络错误")
        }
    }

    suspend fun restartServer(): Boolean {
        return try {
            val resp = client.post("$baseUrl/api/manager/restart")
            resp.status.isSuccess()
        } catch (_: Exception) {
            false
        }
    }

    // ─── 任务管理 ─────────────────────────────────────────────

    suspend fun fetchTasks(targetIde: String? = null, status: String? = null, limit: Int? = null, project: String? = null): List<AideTask> {
        return try {
            val resp = client.get("$baseUrl/api/tasks") {
                targetIde?.let { parameter("target_ide", it) }
                status?.let { parameter("status", it) }
                limit?.let { parameter("limit", it) }
                project?.let { parameter("project", it) }
            }
            if (!resp.status.isSuccess()) return emptyList()
            val text = resp.bodyAsText()
            runCatching {
                val obj = json.parseToJsonElement(text) as? kotlinx.serialization.json.JsonObject
                val tasks = obj?.get("tasks") as? kotlinx.serialization.json.JsonArray
                tasks?.map { json.decodeFromString<AideTask>(it.toString()) } ?: emptyList()
            }.getOrDefault(emptyList())
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun createTask(text: String, title: String? = null, targetIde: String? = null): Boolean {
        return try {
            val body = buildJsonObject {
                put("text", text)
                title?.let { put("title", it) }
                targetIde?.let { put("target_ide", it) }
                put("auto_dispatch", false)
                put("app_version", cc.aidelink.app.BuildConfig.VERSION_NAME)
            }
            val resp = client.post("$baseUrl/api/tasks/create") {
                contentType(ContentType.Application.Json)
                setBody(body.toString())
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun editTask(taskId: String, message: String): Boolean {

        return try {

            val body = buildJsonObject {
                put("task_id", taskId)
                put("message", message)
            }
            val resp = client.post("$baseUrl/api/tasks/edit") {

                contentType(ContentType.Application.Json)

                setBody(body.toString())

            }

            resp.status.isSuccess()

        } catch (e: Exception) {

            false

        }

    }



    suspend fun sendTaskFeedback(taskId: String, feedback: String): Boolean {

        return try {

            val body = buildJsonObject {
                put("task_id", taskId)
                put("feedback", feedback)
            }
            val resp = client.post("$baseUrl/api/tasks/feedback") {

                contentType(ContentType.Application.Json)

                setBody(body.toString())

            }

            resp.status.isSuccess()

        } catch (e: Exception) {

            false

        }

    }



    suspend fun enableUsbTcpip(): Boolean {
        return try {
            val resp = client.post("$baseUrl/api/adb/usb_tcpip") {
                contentType(ContentType.Application.Json)
                setBody("{}")
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun reportWirelessResult(
        ip: String,
        port: Int,
        ok: Boolean,
        error: String? = null,
        method: String? = null,
        requestId: String? = null,
        targetIp: String? = null,
    ): Boolean {
        return try {
            val body = mutableMapOf<String, Any>("ip" to ip, "port" to port, "ok" to ok, "error" to (error ?: ""))
            if (method != null) body["method"] = method
            if (!requestId.isNullOrBlank()) body["request_id"] = requestId
            if (!targetIp.isNullOrBlank()) body["target_ip"] = targetIp
            val resp = client.post("$baseUrl/api/adb/wireless-result") {
                contentType(ContentType.Application.Json)
                setBody(body)
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun completeTask(taskId: String): Boolean {
        return try {
            val resp = client.post("$baseUrl/api/tasks/$taskId/complete") {
                contentType(ContentType.Application.Json)
                setBody("{}")
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun confirmTask(taskId: String): Boolean {
        return try {
            val resp = client.post("$baseUrl/api/tasks/$taskId/confirm") {
                contentType(ContentType.Application.Json)
                setBody("{}")
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun failTask(taskId: String, error: String = "手动标记失败"): Boolean {
        return try {
            val body = buildJsonObject {
                put("error", error)
            }
            val resp = client.post("$baseUrl/api/tasks/$taskId/fail") {
                contentType(ContentType.Application.Json)
                setBody(body.toString())
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun deleteTask(taskId: String): Boolean {
        return try {
            val resp = client.delete("$baseUrl/api/tasks/$taskId")
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun assignTask(taskId: String, targetIde: String): Boolean {
        return try {
            val body = buildJsonObject {
                put("target_ide", targetIde)
                put("auto_dispatch", true)
            }
            val resp = client.post("$baseUrl/api/tasks/$taskId/assign") {
                contentType(ContentType.Application.Json)
                setBody(body.toString())
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun dispatchTasks(taskIds: List<String>, targetIde: String): Boolean {
        return try {
            val jsonBody = buildString {
                append("{")
                append("\"target_ide\":\"$targetIde\",")
                append("\"task_ids\":[")
                append(taskIds.joinToString(",") { "\"$it\"" })
                append("]")
                append("}")
            }
            val resp = client.post("$baseUrl/api/tasks/dispatch") {
                contentType(ContentType.Application.Json)
                setBody(jsonBody)
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun predictPrompts(
        file: String,
        name: String,
        desc: String,
        category: String,
        userReq: String,
        lineStart: String? = null,
        lineEnd: String? = null,
    ): PromptPredictResponse {
        return try {
            val body = buildJsonObject {
                put("file", file)
                put("name", name)
                put("desc", desc)
                put("category", category)
                put("user_req", userReq)
                lineStart?.let { put("line_start", it) }
                lineEnd?.let { put("line_end", it) }
            }
            val resp = client.post("$baseUrl/api/prompt/predict") {
                contentType(ContentType.Application.Json)
                setBody(body.toString())
            }
            if (!resp.status.isSuccess()) {
                PromptPredictResponse(success = false, message = "HTTP ${resp.status.value}")
            } else {
                json.decodeFromString<PromptPredictResponse>(resp.bodyAsText())
            }
        } catch (e: Exception) {
            PromptPredictResponse(success = false, message = e.message)
        }
    }

    suspend fun composePrompt(
        platform: String,
        componentName: String,
        userText: String,
        taskType: String = "auto",
        location: String = "",
        image: String? = null,
    ): PromptComposeResponse {
        return try {
            val body = buildJsonObject {
                put("task_type", taskType)
                put("user_text", userText)
                put("component", buildJsonObject {
                    put("platform", platform)
                    put("name", componentName)
                    put("location", location)
                })
                image?.let { put("image", it) }
            }
            val resp = client.post("$baseUrl/api/prompt/compose") {
                contentType(ContentType.Application.Json)
                setBody(body.toString())
            }
            if (!resp.status.isSuccess()) {
                PromptComposeResponse(message = "HTTP ${resp.status.value}")
            } else {
                json.decodeFromString<PromptComposeResponse>(resp.bodyAsText())
            }
        } catch (e: Exception) {
            PromptComposeResponse(message = e.message)
        }
    }
}



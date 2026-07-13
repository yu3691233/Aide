package cc.aidelink.app.data.api

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import cc.aidelink.app.domain.model.bridge.*

/**
 * 桥接 API - 应用相关
 */
class BridgeAppApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun ping(): Boolean = runCatching {
        val r = client.get("$baseUrl/ping")
        r.status.isSuccess()
    }.getOrDefault(false)

    suspend fun ping(url: String): Boolean = runCatching {
        val r = client.get("${url.trimEnd('/')}/ping")
        r.status.isSuccess()
    }.getOrDefault(false)

    suspend fun fetchAppVersion(): AppVersionResponse {
        return try {
            val resp = client.get("$baseUrl/app/version")
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else AppVersionResponse(ok = false, error = resp.bodyAsText())
        } catch (e: Exception) {
            AppVersionResponse(ok = false, error = e.message)
        }
    }

    suspend fun fetchActiveModels(): List<ActiveModel> {
        return try {
            val resp = client.get("$baseUrl/api/active-models")
            if (resp.status.isSuccess()) {
                val r: ActiveModelsResponse = kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
                r.models
            } else emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun submitAideLinkTask(
        message: String,
        taskType: String = "code",
        async: Boolean = false
    ): AideLinkTaskResponse {
        return try {
            val resp = client.post("$baseUrl/evolution/submit") {
                setBody(AideLinkSubmitRequest(message, taskType, async))
                contentType(io.ktor.http.ContentType.Application.Json)
            }
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else AideLinkTaskResponse(ok = false, raw = resp.bodyAsText())
        } catch (e: Exception) {
            AideLinkTaskResponse(ok = false, raw = e.message ?: "Unknown error")
        }
    }

    suspend fun queryAideLinkTask(taskId: String): String = try {
        val resp = client.get("$baseUrl/evolution/task/$taskId")
        if (resp.status.isSuccess()) resp.bodyAsText() else "Error: ${resp.status}"
    } catch (e: Exception) {
        "Error: ${e.message}"
    }

    suspend fun schedulerStats(): String = try {
        val resp = client.get("$baseUrl/scheduler/stats")
        if (resp.status.isSuccess()) resp.bodyAsText() else "Error"
    } catch (e: Exception) {
        "Error: ${e.message}"
    }

    suspend fun browsePath(title: String = "选择 IDE 可执行文件", startDir: String? = null): String? {
        return try {
            val resp = client.get("$baseUrl/browse-path") {
                parameter("title", title)
                startDir?.let { parameter("start_dir", it) }
            }
            if (resp.status.isSuccess()) {
                val r: BrowsePathResponse = kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
                r.path
            } else null
        } catch (e: Exception) {
            null
        }
    }
}

@kotlinx.serialization.Serializable
data class BrowsePathResponse(
    val ok: Boolean = false,
    val path: String? = null,
)

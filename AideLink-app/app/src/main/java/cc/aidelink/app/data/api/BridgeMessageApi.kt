package cc.aidelink.app.data.api

import io.ktor.client.HttpClient
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import cc.aidelink.app.domain.model.bridge.*

/**
 * 桥接 API - 消息和剪贴板相关
 */
class BridgeMessageApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun fetchHistory(limit: Int = 50): List<ChatMessage> {
        return try {
            val resp = client.get("$baseUrl/history") {
                url { parameters.append("limit", limit.toString()) }
            }
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun send(text: String, target: String = "auto", image: String? = null, taskId: String? = null): SendResponse {
        return try {
            val resp = client.post("$baseUrl/send") {
                setBody(SendRequest(text = text, target = target, image = image, task_id = taskId))
                contentType(io.ktor.http.ContentType.Application.Json)
            }
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else SendResponse(ok = false, raw = resp.bodyAsText())
        } catch (e: Exception) {
            SendResponse(ok = false, raw = e.message ?: "Unknown error")
        }
    }

    suspend fun fetchSessions(): List<IdeSession> {
        return try {
            val resp = client.get("$baseUrl/sessions")
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun fetchClipboard(): List<ClipboardItem> {
        return try {
            val resp = client.get("$baseUrl/clipboard")
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun appendClipboard(text: String): Boolean = try {
        val resp = client.post("$baseUrl/clipboard/append") {
            setBody(ClipboardAppendRequest(text))
            contentType(io.ktor.http.ContentType.Application.Json)
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
}

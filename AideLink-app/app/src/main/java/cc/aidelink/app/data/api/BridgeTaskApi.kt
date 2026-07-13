package cc.aidelink.app.data.api

import io.ktor.client.HttpClient
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.JsonPrimitive
import cc.aidelink.app.domain.model.bridge.*

/**
 * 桥接 API - 任务管理相关
 */
class BridgeTaskApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun fetchTasks(targetIde: String? = null, status: String? = null, limit: Int? = null, project: String? = null): List<AideTask> {
        return try {
            val resp = client.get("$baseUrl/api/tasks") {
                targetIde?.let { parameter("target_ide", it) }
                status?.let { parameter("status", it) }
                limit?.let { parameter("limit", it.toString()) }
                project?.let { parameter("project", it) }
            }
            if (resp.status.isSuccess()) {
                val text = resp.bodyAsText()
                val obj = kotlinx.serialization.json.Json.parseToJsonElement(text) as? kotlinx.serialization.json.JsonObject
                val tasks = obj?.get("tasks") as? kotlinx.serialization.json.JsonArray
                tasks?.map { kotlinx.serialization.json.Json.decodeFromString<AideTask>(it.toString()) } ?: emptyList()
            } else emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun createTask(text: String, title: String? = null, targetIde: String? = null): Boolean {
        return try {
            val body = buildJsonObject {
                put("text", JsonPrimitive(text))
                title?.let { put("title", JsonPrimitive(it)) }
                targetIde?.let { put("target_ide", JsonPrimitive(it)) }
                put("auto_dispatch", JsonPrimitive(false))
            }
            val resp = client.post("$baseUrl/api/tasks/create") {
                setBody(body.toString())
                contentType(ContentType.Application.Json)
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun editTask(taskId: String, message: String): Boolean = try {
        val body = buildJsonObject {
            put("task_id", JsonPrimitive(taskId))
            put("message", JsonPrimitive(message))
        }
        val resp = client.post("$baseUrl/api/tasks/edit") {
            setBody(body.toString())
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun sendTaskFeedback(taskId: String, feedback: String): Boolean = try {
        val body = buildJsonObject {
            put("task_id", JsonPrimitive(taskId))
            put("feedback", JsonPrimitive(feedback))
        }
        val resp = client.post("$baseUrl/api/tasks/feedback") {
            setBody(body.toString())
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun completeTask(taskId: String): Boolean = try {
        val resp = client.post("$baseUrl/api/tasks/$taskId/complete")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun confirmTask(taskId: String): Boolean = try {
        val resp = client.post("$baseUrl/api/tasks/$taskId/confirm")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun failTask(taskId: String, error: String = "手动标记失败"): Boolean = try {
        val resp = client.post("$baseUrl/api/tasks/$taskId/fail") {
            setBody(buildString { append("{\"error\":\"$error\"}") })
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun deleteTask(taskId: String): Boolean = try {
        val resp = client.delete("$baseUrl/api/tasks/$taskId")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun assignTask(taskId: String, targetIde: String): Boolean = try {
        val resp = client.post("$baseUrl/api/tasks/$taskId/assign") {
            setBody(buildString { append("{\"target_ide\":\"$targetIde\"}") })
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun predictPrompts(
        taskId: String? = null,
        taskText: String? = null,
        action: String? = null,
        description: String? = null
    ): PromptPredictResponse {
        return try {
            val body = buildString {
                append("{")
                taskId?.let { append("\"task_id\":\"$it\",") }
                taskText?.let { append("\"task_text\":\"${it.replace("\"", "\\\"")}\",") }
                action?.let { append("\"action\":\"$it\",") }
                description?.let { append("\"description\":\"${it.replace("\"", "\\\"")}\",") }
                if (endsWith(",")) deleteCharAt(length - 1)
                append("}")
            }
            val resp = client.post("$baseUrl/api/prompt/predict") {
                setBody(body)
                contentType(ContentType.Application.Json)
            }
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else PromptPredictResponse(success = false, message = resp.bodyAsText())
        } catch (e: Exception) {
            PromptPredictResponse(success = false, message = e.message)
        }
    }
}

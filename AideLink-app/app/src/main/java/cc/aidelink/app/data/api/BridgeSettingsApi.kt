package cc.aidelink.app.data.api

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import cc.aidelink.app.domain.model.bridge.*

/**
 * 桥接 API - 设置相关
 */
class BridgeSettingsApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun fetchSettings(): SettingsPayload? {
        return try {
            val resp = client.get("$baseUrl/settings")
            if (resp.status.isSuccess()) {
                val r: SettingsEnvelope = kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
                r.settings
            } else null
        } catch (e: Exception) {
            null
        }
    }

    suspend fun patchSetting(key: String, value: JsonElement): Boolean = try {
        val body = kotlinx.serialization.json.buildJsonObject {
            put(key, value)
        }.toString()
        val resp = client.post("$baseUrl/settings") {
            setBody(body)
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun patchSetting(body: JsonObject): Boolean = try {
        val resp = client.post("$baseUrl/settings") {
            setBody(body.toString())
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun patchSetting(key: String, value: Any): Boolean = when (value) {
        is Boolean -> patchSetting(key, kotlinx.serialization.json.JsonPrimitive(value))
        is Number -> patchSetting(key, kotlinx.serialization.json.JsonPrimitive(value))
        is String -> patchSetting(key, kotlinx.serialization.json.JsonPrimitive(value))
        else -> false
    }
}

package cc.aidelink.app.data.api

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import cc.aidelink.app.domain.model.bridge.*

/**
 * 桥接 API - MiMoCode 相关
 */
class BridgeMimoApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun fetchMimoStatus(): MimoStatusResponse? {
        return try {
            val resp = client.get("$baseUrl/xiaomengling/mimo/status")
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else null
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

    suspend fun fetchMimoModels(): MimoModelsEnvelope {
        return try {
            val resp = client.get("$baseUrl/xiaomengling/mimo/models")
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else MimoModelsEnvelope(ok = false)
        } catch (e: Exception) {
            MimoModelsEnvelope(ok = false)
        }
    }

    suspend fun setMimoModel(modelId: String, providerId: String = ""): Boolean = try {
        val resp = client.post("$baseUrl/xiaomengling/mimo/model") {
            setBody(buildString { append("{\"model\":\"$modelId\",\"provider\":\"$providerId\"}") })
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun fetchMimoWebUrl(): MimoWebUrlResponse {
        return try {
            val resp = client.get("$baseUrl/xiaomengling/mimo/web-url")
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else MimoWebUrlResponse(ok = false)
        } catch (e: Exception) {
            MimoWebUrlResponse(ok = false)
        }
    }

    suspend fun createNewSession(): NewSessionResponse {
        return try {
            val resp = client.post("$baseUrl/xiaomengling/mimo/new-session")
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else NewSessionResponse(ok = false)
        } catch (e: Exception) {
            NewSessionResponse(ok = false)
        }
    }
}

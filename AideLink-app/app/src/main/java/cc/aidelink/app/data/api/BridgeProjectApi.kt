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
 * 桥接 API - 项目地图相关
 */
class BridgeProjectApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun fetchProjectMap(onlyVisible: Boolean = false): ProjectMapResponse {
        return try {
            val resp = client.get("$baseUrl/project-map") {
                if (onlyVisible) parameter("only_visible", "true")
            }
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else ProjectMapResponse(ok = false)
        } catch (e: Exception) {
            ProjectMapResponse(ok = false)
        }
    }

    suspend fun scanProjectMap(onlyVisible: Boolean = false): ProjectMapResponse {
        return try {
            val resp = client.post("$baseUrl/project-map/scan") {
                if (onlyVisible) {
                    setBody(buildString { append("{\"only_visible\":true}") })
                    contentType(ContentType.Application.Json)
                }
            }
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else ProjectMapResponse(ok = false)
        } catch (e: Exception) {
            ProjectMapResponse(ok = false)
        }
    }

    suspend fun lockProjectFeature(
        nodeId: String,
        nodeName: String,
        file: String,
        symbol: String,
        version: String,
        description: String
    ): ProjectLockResponse {
        return try {
            val resp = client.post("$baseUrl/project-map/lock") {
                setBody(ProjectLockRequest(nodeId, nodeName, file, symbol, version, description))
                contentType(ContentType.Application.Json)
            }
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else ProjectLockResponse(ok = false, error = resp.bodyAsText())
        } catch (e: Exception) {
            ProjectLockResponse(ok = false, error = e.message)
        }
    }
}

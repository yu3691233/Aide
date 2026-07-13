package cc.aidelink.app.data.api

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.statement.bodyAsText
import io.ktor.http.isSuccess
import cc.aidelink.app.domain.model.bridge.*

/**
 * 桥接 API - OC Web 相关
 */
class BridgeOcWebApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun getOcWebStatus(): OcWebStatus = try {
        val resp = client.get("$baseUrl/oc-web/status")
        if (resp.status.isSuccess()) {
            kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
        } else OcWebStatus(ok = false)
    } catch (e: Exception) {
        OcWebStatus(ok = false)
    }

    suspend fun startOcWeb(): OcWebActionResult = try {
        val resp = client.post("$baseUrl/oc-web/start")
        if (resp.status.isSuccess()) {
            kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
        } else OcWebActionResult(ok = false, error = resp.bodyAsText())
    } catch (e: Exception) {
        OcWebActionResult(ok = false, error = e.message)
    }

    suspend fun stopOcWeb(): OcWebActionResult = try {
        val resp = client.post("$baseUrl/oc-web/stop")
        if (resp.status.isSuccess()) {
            kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
        } else OcWebActionResult(ok = false, error = resp.bodyAsText())
    } catch (e: Exception) {
        OcWebActionResult(ok = false, error = e.message)
    }

    suspend fun getOcWebLatestReply(): OcWebLatestReply = try {
        val resp = client.get("$baseUrl/oc-web/latest-reply")
        if (resp.status.isSuccess()) {
            kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
        } else OcWebLatestReply(ok = false, error = resp.bodyAsText())
    } catch (e: Exception) {
        OcWebLatestReply(ok = false, error = e.message)
    }
}

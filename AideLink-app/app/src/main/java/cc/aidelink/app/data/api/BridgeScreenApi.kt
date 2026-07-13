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
 * 桥接 API - 屏幕控制相关
 */
class BridgeScreenApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun wakeScreen(): WakeResult = try {
        val resp = client.post("$baseUrl/screen/wake")
        if (resp.status.isSuccess()) {
            kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
        } else WakeResult(ok = false, reason = resp.bodyAsText())
    } catch (e: Exception) {
        WakeResult(ok = false, reason = e.message)
    }

    suspend fun ensureScreenUnlocked(): WakeResult = try {
        val resp = client.post("$baseUrl/screen/ensure-unlocked")
        if (resp.status.isSuccess()) {
            kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
        } else WakeResult(ok = false, reason = resp.bodyAsText())
    } catch (e: Exception) {
        WakeResult(ok = false, reason = e.message)
    }

    suspend fun getScreenStatus(): ScreenStatus = try {
        val resp = client.get("$baseUrl/screen/status")
        if (resp.status.isSuccess()) {
            kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
        } else ScreenStatus(ok = false)
    } catch (e: Exception) {
        ScreenStatus(ok = false)
    }

    suspend fun setScreenSettings(autoSkipLock: Boolean): Boolean = try {
        val resp = client.post("$baseUrl/screen/settings") {
            setBody(buildString { append("{\"autoSkipLock\":$autoSkipLock}") })
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }
}

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
 * 桥接 API - UI 定位器相关
 */
class BridgeUiLocatorApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun captureUiLocator(): UiLocatorCaptureResponse {
        return try {
            val resp = client.post("$baseUrl/ui-locator/capture")
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else UiLocatorCaptureResponse(ok = false, error = resp.bodyAsText())
        } catch (e: Exception) {
            UiLocatorCaptureResponse(ok = false, error = e.message)
        }
    }

    suspend fun locateUiElement(x: Int, y: Int, width: Int, height: Int): UiLocatorLocateResponse {
        return try {
            val resp = client.post("$baseUrl/ui-locator/locate") {
                setBody(UiLocatorLocateRequest(x, y, width, height))
                contentType(ContentType.Application.Json)
            }
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else UiLocatorLocateResponse(ok = false, error = resp.bodyAsText())
        } catch (e: Exception) {
            UiLocatorLocateResponse(ok = false, error = e.message)
        }
    }

    suspend fun injectClipboard(target: String): Boolean = try {
        val resp = client.post("$baseUrl/inject-clipboard") {
            setBody(buildString { append("{\"target\":\"$target\"}") })
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }
}

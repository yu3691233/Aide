package cc.aidelink.app.data.api

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.client.statement.readBytes
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import cc.aidelink.app.domain.model.bridge.*

/**
 * 桥接 API - 截图和裁剪相关
 */
class BridgeScreenshotApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun screenshotFull(target: String? = null, monitor: String? = null, fullMonitor: Boolean = false): ByteArray? {
        return try {
            val resp = client.get("$baseUrl/screenshot/full") {
                target?.let { parameter("target", it) }
                monitor?.let { parameter("monitor", it) }
                if (fullMonitor) parameter("full_monitor", "true")
            }
            if (resp.status.isSuccess()) resp.readBytes() else null
        } catch (e: Exception) {
            null
        }
    }

    suspend fun screenshotFullWithStatus(target: String? = null, monitor: String? = null, fullMonitor: Boolean = false): Pair<ByteArray?, Boolean> {
        return try {
            val resp = client.get("$baseUrl/screenshot/full") {
                target?.let { parameter("target", it) }
                monitor?.let { parameter("monitor", it) }
                if (fullMonitor) parameter("full_monitor", "true")
            }
            if (resp.status.isSuccess()) {
                Pair(resp.readBytes(), resp.headers["X-Window-Found"] == "true")
            } else {
                Pair(null, false)
            }
        } catch (e: Exception) {
            Pair(null, false)
        }
    }

    suspend fun screenshotCrop(
        target: String,
        left: Int, right: Int, top: Int, bottom: Int,
        monitor: String? = null
    ): ByteArray? {
        return try {
            val resp = client.get("$baseUrl/screenshot/crop") {
                parameter("target", target)
                parameter("left", left)
                parameter("right", right)
                parameter("top", top)
                parameter("bottom", bottom)
                monitor?.let { parameter("monitor", it) }
            }
            if (resp.status.isSuccess()) resp.readBytes() else null
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
            if (resp.status.isSuccess()) resp.readBytes() else null
        } catch (e: Exception) {
            null
        }
    }

    suspend fun fetchCropConfigs(): Map<String, CropConfig> {
        return try {
            val resp = client.get("$baseUrl/screenshot/crops")
            if (resp.status.isSuccess()) {
                kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
            } else emptyMap()
        } catch (e: Exception) {
            emptyMap()
        }
    }

    suspend fun fetchMonitors(): List<MonitorInfo> {
        return try {
            val resp = client.get("$baseUrl/screenshot/monitors")
            if (resp.status.isSuccess()) {
                val r: MonitorsResponse = kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
                r.monitors
            } else emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun fetchActiveCropConfig(target: String, monitor: String? = null): CropConfig? {
        return try {
            val resp = client.get("$baseUrl/screenshot/crop-config") {
                parameter("target", target)
                monitor?.let { parameter("monitor", it) }
            }
            if (resp.status.isSuccess()) {
                val r: ActiveCropConfigResponse = kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
                r.config
            } else null
        } catch (e: Exception) {
            null
        }
    }

    suspend fun saveCropConfig(
        target: String, left: Int, right: Int, top: Int, bottom: Int,
        monitor: String? = null, dialogPosition: String? = null,
        calibWidth: Int? = null, calibHeight: Int? = null
    ): Boolean {
        return try {
            val resp = client.post("$baseUrl/screenshot/crop-config") {
                setBody(CropSaveRequest(target, left, right, top, bottom, monitor, dialogPosition, calibWidth, calibHeight))
                contentType(ContentType.Application.Json)
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun fetchTargetWindowInfo(target: String): WindowInfo? {
        return try {
            val resp = client.get("$baseUrl/screenshot/window-info") {
                parameter("target", target)
            }
            if (resp.status.isSuccess()) {
                val r: WindowInfoResponse = kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
                r.window
            } else null
        } catch (e: Exception) {
            null
        }
    }

    suspend fun focusTargetInput(target: String): Boolean = try {
        val resp = client.post("$baseUrl/screenshot/focus-input") {
            setBody(buildString { append("{\"target\":\"$target\"}") })
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun focusTargetWindow(target: String): Boolean = try {
        val resp = client.post("$baseUrl/screenshot/focus-window") {
            setBody(buildString { append("{\"target\":\"$target\"}") })
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }
}

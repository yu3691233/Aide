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
import cc.aidelink.app.domain.model.bridge.*

/**
 * 桥接 API - IDE 管理相关
 */
class BridgeIdeApi(private val client: HttpClient, private val baseUrl: String) {

    suspend fun fetchDesktopIdes(): List<DesktopIde> {
        return try {
            val resp = client.get("$baseUrl/desktop-ides")
            if (resp.status.isSuccess()) {
                val r: DesktopIdesResponse = kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
                r.ides
            } else emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun scanIdes(): List<DesktopIde> {
        return try {
            val resp = client.post("$baseUrl/scan-ides")
            if (resp.status.isSuccess()) {
                val r: DesktopIdesResponse = kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
                r.ides
            } else emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun saveManualIde(ide: DesktopIde): Boolean = try {
        val resp = client.post("$baseUrl/desktop-ides") {
            setBody(ide)
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun removeManualIde(key: String): Boolean = try {
        val resp = client.delete("$baseUrl/desktop-ides/$key")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun installMcp(key: String): Boolean = try {
        val resp = client.post("$baseUrl/api/ide/install-mcp") {
            setBody(mapOf("key" to key))
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun autoBindWindow(key: String): Boolean = try {
        val resp = client.post("$baseUrl/api/ide-window-bindings/auto") {
            setBody(mapOf("key" to key))
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) { false }

    suspend fun moveAndMaximizeForCalibration(key: String, monitor: String): Boolean = try {
        val resp = client.post("$baseUrl/api/calibrate-maximize") {
            setBody(kotlinx.serialization.json.buildJsonObject {
                put("key", kotlinx.serialization.json.JsonPrimitive(key))
                put("monitor_name", kotlinx.serialization.json.JsonPrimitive(monitor))
                put("prepare_only", kotlinx.serialization.json.JsonPrimitive(true))
            })
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) { false }

    suspend fun startIde(ide: String): Boolean = try {
        val resp = client.post("$baseUrl/ide/$ide/start")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun stopIde(ide: String): Boolean = try {
        val resp = client.post("$baseUrl/ide/$ide/stop")
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun getIdeProcesses(): List<DesktopIde> {
        return try {
            val resp = client.get("$baseUrl/ide/processes")
            if (resp.status.isSuccess()) {
                val r: IdeProcessesResponse = kotlinx.serialization.json.Json.decodeFromString(resp.bodyAsText())
                r.ides
            } else emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun ideRelease(ide: String): Boolean = runCatching {
        val resp = client.post("$baseUrl/ide/$ide/release")
        resp.status.isSuccess()
    }.getOrDefault(false)

    suspend fun reportAdbStatus(ip: String, port: Int, enabled: Boolean): Boolean = try {
        val resp = client.post("$baseUrl/adb/status") {
            setBody(buildString { append("{\"ip\":\"$ip\",\"port\":$port,\"enabled\":$enabled}") })
            contentType(ContentType.Application.Json)
        }
        resp.status.isSuccess()
    } catch (e: Exception) {
        false
    }

    suspend fun enableUsbTcpip(): Boolean {
        return try {
            val resp = client.post("$baseUrl/adb/enable-wireless")
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }

    suspend fun reportWirelessResult(ip: String, port: Int, ok: Boolean, error: String? = null, method: String? = null): Boolean {
        return try {
            val body = buildString {
                append("{")
                append("\"ip\":\"$ip\",")
                append("\"port\":$port,")
                append("\"ok\":$ok")
                error?.let { append(",\"error\":\"${it.replace("\"", "\\\"")}\"") }
                method?.let { append(",\"method\":\"$it\"") }
                append("}")
            }
            val resp = client.post("$baseUrl/adb/wireless-result") {
                setBody(body)
                contentType(ContentType.Application.Json)
            }
            resp.status.isSuccess()
        } catch (e: Exception) {
            false
        }
    }
}

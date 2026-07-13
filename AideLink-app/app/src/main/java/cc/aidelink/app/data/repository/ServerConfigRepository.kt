package cc.aidelink.app.data.repository

import android.util.Log
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import cc.aidelink.app.data.api.OpenCodeApi
import cc.aidelink.app.data.api.ServerConnection
import cc.aidelink.app.domain.model.ServerConfig
import cc.aidelink.app.domain.model.ServerHealth
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.flow.map
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import javax.inject.Inject
import javax.inject.Singleton

private const val TAG = "ServerConfigRepository"

/**
 * 统一服务器配置仓库
 * 合并 ServerRepository 和 IdeServerRepository 的功能
 * 
 * 存储键: "ide_servers_json"（兼容 IdeServerRepository）
 * 附加键: "ide_selected_server_id"（选中的服务器 ID）
 */
@Singleton
class ServerConfigRepository @Inject constructor(
    private val dataStore: DataStore<Preferences>,
    private val api: OpenCodeApi
) {
    companion object {
        private val SERVERS_KEY = stringPreferencesKey("ide_servers_json")
        private val SELECTED_SERVER_KEY = stringPreferencesKey("ide_selected_server_id")
    }

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** 所有已保存的服务器配置 */
    val servers: Flow<List<ServerConfig>> = dataStore.data.map { prefs ->
        parseServers(prefs[SERVERS_KEY])
    }

    /** 当前选中的服务器 ID */
    val selectedServerId: Flow<String?> = dataStore.data.map { it[SELECTED_SERVER_KEY] }

    /** 获取所有服务器（一次性） */
    suspend fun getServers(): List<ServerConfig> = servers.first()

    /** 根据 ID 获取服务器 */
    suspend fun getServer(serverId: String): ServerConfig? {
        return servers.firstOrNull()?.find { it.id == serverId }
    }

    /** 添加服务器 */
    suspend fun addServer(server: ServerConfig) {
        dataStore.edit { prefs ->
            val current = parseServers(prefs[SERVERS_KEY]).toMutableList()
            current.add(server)
            prefs[SERVERS_KEY] = serializeServers(current)
        }
    }

    /** 更新服务器 */
    suspend fun updateServer(server: ServerConfig) {
        dataStore.edit { prefs ->
            val current = parseServers(prefs[SERVERS_KEY]).toMutableList()
            val idx = current.indexOfFirst { it.id == server.id }
            if (idx >= 0) {
                current[idx] = server
                prefs[SERVERS_KEY] = serializeServers(current)
            }
        }
    }

    /** 删除服务器 */
    suspend fun removeServer(serverId: String) {
        dataStore.edit { prefs ->
            val current = parseServers(prefs[SERVERS_KEY]).toMutableList()
            current.removeAll { it.id == serverId }
            prefs[SERVERS_KEY] = serializeServers(current)
            // 如果删除的是当前选中的服务器，清除选中状态
            if (prefs[SELECTED_SERVER_KEY] == serverId) {
                prefs.remove(SELECTED_SERVER_KEY)
            }
        }
    }

    /** 设置选中的服务器 */
    suspend fun setSelectedServerId(id: String?) {
        dataStore.edit { prefs ->
            if (id != null) {
                prefs[SELECTED_SERVER_KEY] = id
            } else {
                prefs.remove(SELECTED_SERVER_KEY)
            }
        }
    }

    /** 获取选中的服务器 ID */
    suspend fun getSelectedServerId(): String? = selectedServerId.first()

    /** 检查服务器健康状态 */
    suspend fun checkHealth(server: ServerConfig): Result<ServerHealth> {
        return try {
            val conn = ServerConnection.from(server.url, server.username, server.password)
            val health = api.getHealth(conn)
            val updatedServer = server.copy(
                isHealthy = health.healthy,
                lastConnected = System.currentTimeMillis()
            )
            updateServer(updatedServer)
            Result.success(health)
        } catch (e: Exception) {
            Log.e(TAG, "Health check failed for ${server.url}", e)
            val updatedServer = server.copy(isHealthy = false)
            updateServer(updatedServer)
            Result.failure(e)
        }
    }

    /** 检查服务器健康（返回布尔值） */
    suspend fun checkServerHealth(server: ServerConfig): Boolean {
        return checkHealth(server).isSuccess
    }

    /** 设置自动连接 */
    suspend fun setAutoConnect(serverId: String, autoConnect: Boolean) {
        val server = getServer(serverId) ?: return
        updateServer(server.copy(autoConnect = autoConnect))
    }

    /** 更新最后连接时间 */
    suspend fun updateLastConnected(serverId: String) {
        val currentServers = servers.first()
        val updatedServers = currentServers.map {
            if (it.id == serverId) {
                it.copy(lastConnected = System.currentTimeMillis())
            } else it
        }
        saveServers(updatedServers)
    }

    private fun parseServers(raw: String?): List<ServerConfig> {
        if (raw.isNullOrBlank()) return emptyList()
        return try {
            json.decodeFromString<List<ServerConfig>>(raw)
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun serializeServers(servers: List<ServerConfig>): String {
        return json.encodeToString(servers)
    }

    private suspend fun saveServers(servers: List<ServerConfig>) {
        dataStore.edit { prefs ->
            prefs[SERVERS_KEY] = serializeServers(servers)
        }
    }
}

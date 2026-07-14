package cc.aidelink.app.data.repository

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import cc.aidelink.app.domain.model.BridgeServerConfig
import cc.aidelink.app.domain.model.BridgeServerType
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 桥接服务器配置仓库
 * 管理多个服务器配置（局域网、FRP等）
 */
@Singleton
class BridgeServerRepository @Inject constructor(
    private val dataStore: DataStore<Preferences>,
    @ApplicationContext private val context: Context
) {
    companion object {
        private val BRIDGE_SERVERS_KEY = stringPreferencesKey("bridge_servers")
        private val ACTIVE_SERVER_ID_KEY = stringPreferencesKey("active_bridge_server_id")

        /** 回环地址只代表手机自身，不能作为连接 PC 桥接服务的服务器。 */
        fun isPhoneLoopbackUrl(url: String): Boolean {
            val host = runCatching {
                val value = url.trim()
                java.net.URI(if (value.contains("://")) value else "http://$value").host
            }.getOrNull()?.trim()?.trimEnd('.')?.lowercase()

            return host == "localhost" || host == "::1" || host?.startsWith("127.") == true
        }
    }

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /**
     * 获取所有已保存的服务器配置
     */
    val servers: Flow<List<BridgeServerConfig>> = dataStore.data.map { preferences ->
        val serversJson = preferences[BRIDGE_SERVERS_KEY] ?: "[]"
        try {
            json.decodeFromString<List<BridgeServerConfig>>(serversJson)
                .filterNot { isPhoneLoopbackUrl(it.url) }
        } catch (e: Exception) {
            emptyList()
        }
    }

    /**
     * 获取当前激活的服务器ID
     */
    val activeServerId: Flow<String?> = dataStore.data.map { preferences ->
        preferences[ACTIVE_SERVER_ID_KEY]
    }

    /**
     * 获取所有服务器（一次性）
     */
    suspend fun getAllServers(): List<BridgeServerConfig> = servers.first()

    /**
     * 添加新服务器
     */
    suspend fun addServer(
        name: String,
        url: String,
        type: BridgeServerType = BridgeServerType.LOCAL,
        autoConnect: Boolean = false
    ): BridgeServerConfig {
        require(!isPhoneLoopbackUrl(url)) { "不能将手机本机回环地址保存为 PC 服务器" }
        val server = BridgeServerConfig(
            id = java.util.UUID.randomUUID().toString(),
            name = name,
            url = url.trimEnd('/'),
            serverType = type,
            autoConnect = autoConnect,
            lastConnected = null
        )

        val currentServers = getAllServers()
        val updatedServers = currentServers + server
        saveServers(updatedServers)

        return server
    }

    /**
     * 更新服务器
     */
    suspend fun updateServer(server: BridgeServerConfig) {
        require(!isPhoneLoopbackUrl(server.url)) { "不能将手机本机回环地址保存为 PC 服务器" }
        val currentServers = getAllServers()
        val updatedServers = currentServers.map {
            if (it.id == server.id) server else it
        }
        saveServers(updatedServers)
    }

    /**
     * 删除服务器
     */
    suspend fun deleteServer(serverId: String) {
        val currentServers = getAllServers()
        val updatedServers = currentServers.filter { it.id != serverId }
        saveServers(updatedServers)

        // 如果删除的是当前激活的服务器，清除激活状态
        val activeId = activeServerId.first()
        if (activeId == serverId) {
            setActiveServerId(null)
        }
    }

    /**
     * 设置激活的服务器
     */
    suspend fun setActiveServerId(serverId: String?) {
        dataStore.edit { preferences ->
            if (serverId != null) {
                preferences[ACTIVE_SERVER_ID_KEY] = serverId
            } else {
                preferences.remove(ACTIVE_SERVER_ID_KEY)
            }
        }
    }

    /**
     * 获取激活的服务器配置
     */
    suspend fun getActiveServer(): BridgeServerConfig? {
        val activeId = activeServerId.first() ?: return null
        return getAllServers().find { it.id == activeId }
    }

    /**
     * 更新服务器最后连接时间
     */
    suspend fun updateLastConnected(serverId: String) {
        val currentServers = getAllServers()
        val updatedServers = currentServers.map {
            if (it.id == serverId) {
                it.copy(lastConnected = System.currentTimeMillis())
            } else it
        }
        saveServers(updatedServers)
    }

    private suspend fun saveServers(servers: List<BridgeServerConfig>) {
        dataStore.edit { preferences ->
            preferences[BRIDGE_SERVERS_KEY] = json.encodeToString(servers)
        }
    }
}

package cc.aidelink.app.data.repository

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.util.UUID

/**
 * 离线任务缓存：在无网络时保存任务，连接恢复后自动同步到服务器。
 * 存储在 SharedPreferences 中，按任务 ID 去重。
 */
object OfflineTaskCache {
    private const val PREFS_NAME = "offline_tasks"
    private const val KEY_TASKS = "tasks_json"
    private const val KEY_SERVER_TASKS = "server_tasks_json"
    private const val KEY_CHAT_HISTORY = "chat_history_json"

    private val json = Json { ignoreUnknownKeys = true; prettyPrint = false }

    @Serializable
    data class CachedTask(
        val id: String = UUID.randomUUID().toString().substring(0, 8),
        val title: String,
        val message: String,
        val targetIde: String = "",
        val createdAt: Long = System.currentTimeMillis(),
        var synced: Boolean = false,
        val status: String = "pending_upload",
    )

    private fun getPrefs(context: Context): SharedPreferences {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    private fun loadAll(context: Context): MutableList<CachedTask> {
        val raw = getPrefs(context).getString(KEY_TASKS, null) ?: return mutableListOf()
        return try {
            json.decodeFromString<List<CachedTask>>(raw).toMutableList()
        } catch (_: Exception) { mutableListOf() }
    }

    private fun saveAll(context: Context, tasks: List<CachedTask>) {
        getPrefs(context).edit().putString(KEY_TASKS, json.encodeToString(tasks)).apply()
    }

    /**
     * 保存从服务器成功拉取的任务列表到本地持久化缓存
     */
    fun saveServerTasks(context: Context, tasks: List<cc.aidelink.app.domain.model.bridge.AideTask>) {
        try {
            getPrefs(context).edit().putString(KEY_SERVER_TASKS, json.encodeToString(tasks)).apply()
        } catch (_: Exception) {}
    }

    /**
     * 保存聊天历史到本地缓存，启动时先显示缓存再从服务端更新
     */
    fun saveChatHistory(context: Context, messages: List<cc.aidelink.app.domain.model.bridge.ChatMessage>) {
        try {
            getPrefs(context).edit().putString(KEY_CHAT_HISTORY, json.encodeToString(messages)).apply()
        } catch (_: Exception) {}
    }

    /**
     * 读取本地缓存的聊天历史
     */
    fun getChatHistory(context: Context): List<cc.aidelink.app.domain.model.bridge.ChatMessage> {
        val raw = getPrefs(context).getString(KEY_CHAT_HISTORY, null) ?: return emptyList()
        return try {
            json.decodeFromString<List<cc.aidelink.app.domain.model.bridge.ChatMessage>>(raw)
        } catch (_: Exception) { emptyList() }
    }

    /**
     * 从本地持久化缓存读取拉取的历史任务列表
     */
    fun getServerTasks(context: Context): List<cc.aidelink.app.domain.model.bridge.AideTask> {
        val raw = getPrefs(context).getString(KEY_SERVER_TASKS, null) ?: return emptyList()
        return try {
            json.decodeFromString<List<cc.aidelink.app.domain.model.bridge.AideTask>>(raw)
        } catch (_: Exception) { emptyList() }
    }

    /**
     * 保存一个离线任务
     */
    fun save(context: Context, title: String, message: String, targetIde: String = "", status: String = "pending_upload"): CachedTask {
        val task = CachedTask(title = title, message = message, targetIde = targetIde, status = status)
        val tasks = loadAll(context)
        tasks.add(task)
        saveAll(context, tasks)
        return task
    }

    /**
     * 获取所有未同步的任务
     */
    fun getPending(context: Context): List<CachedTask> {
        return loadAll(context).filter { !it.synced }
    }

    /**
     * 获取所有任务（含已同步）
     */
    fun getAll(context: Context): List<CachedTask> {
        return loadAll(context)
    }

    /**
     * 标记任务已同步
     */
    fun markSynced(context: Context, taskId: String) {
        val tasks = loadAll(context)
        val idx = tasks.indexOfFirst { it.id == taskId }
        if (idx >= 0) {
            tasks[idx] = tasks[idx].copy(synced = true)
            saveAll(context, tasks)
        }
    }

    /**
     * 删除任务
     */
    fun remove(context: Context, taskId: String) {
        val tasks = loadAll(context)
        tasks.removeAll { it.id == taskId }
        saveAll(context, tasks)
    }

    /**
     * 清空已同步的任务
     */
    fun clearSynced(context: Context) {
        val tasks = loadAll(context)
        saveAll(context, tasks.filter { !it.synced })
    }

    /**
     * 同步所有待同步任务到服务器
     * 返回成功同步的数量
     */
    suspend fun syncToServer(context: Context, bridgeApi: cc.aidelink.app.data.api.BridgeApi): Int = withContext(Dispatchers.IO) {
        val pending = getPending(context)
        var synced = 0
        for (task in pending) {
            try {
                val ok = bridgeApi.createTask(
                    text = task.message,
                    title = task.title,
                    targetIde = task.targetIde.ifBlank { null },
                )
                if (ok) {
                    markSynced(context, task.id)
                    synced++
                }
            } catch (_: Exception) {}
        }
        synced
    }
}

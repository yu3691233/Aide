package cc.aidelink.app.data.repository

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import cc.aidelink.app.data.config.BridgeDefaults
import javax.inject.Inject
import javax.inject.Singleton

/**
 * App-wide settings stored in DataStore.
 */
@Singleton
class SettingsRepository @Inject constructor(
    private val dataStore: DataStore<Preferences>,
    @dagger.hilt.android.qualifiers.ApplicationContext private val context: Context
) {
    companion object {
        private val SERVER_URL_KEY = stringPreferencesKey("aidelink_server_url")
        private val WOL_MAC_KEY = stringPreferencesKey("aidelink_wol_mac")
        private val LANGUAGE_KEY = stringPreferencesKey("app_language")
        private val THEME_KEY = stringPreferencesKey("app_theme")
        private val DYNAMIC_COLOR_KEY = booleanPreferencesKey("dynamic_color")
        private val FONT_SIZE_KEY = stringPreferencesKey("chat_font_size")
        private val NOTIFICATIONS_KEY = booleanPreferencesKey("notifications_enabled")

        private val INITIAL_MESSAGE_COUNT_KEY = intPreferencesKey("initial_message_count")
        private val CODE_WORD_WRAP_KEY = booleanPreferencesKey("code_word_wrap")
        private val CONFIRM_BEFORE_SEND_KEY = booleanPreferencesKey("confirm_before_send")
        private val AMOLED_DARK_KEY = booleanPreferencesKey("amoled_dark")
        private val COMPACT_MESSAGES_KEY = booleanPreferencesKey("compact_messages")
        private val COLLAPSE_TOOLS_KEY = booleanPreferencesKey("collapse_tools")
        private val HAPTIC_FEEDBACK_KEY = booleanPreferencesKey("haptic_feedback")
        private val RECONNECT_MODE_KEY = stringPreferencesKey("reconnect_mode")
        private val KEEP_SCREEN_ON_KEY = booleanPreferencesKey("keep_screen_on")
        private val SILENT_NOTIFICATIONS_KEY = booleanPreferencesKey("silent_notifications")
        private val COMPRESS_IMAGE_ATTACHMENTS_KEY = booleanPreferencesKey("compress_image_attachments")
        private val IMAGE_ATTACHMENT_MAX_LONG_SIDE_KEY = intPreferencesKey("image_attachment_max_long_side")
        private val IMAGE_ATTACHMENT_WEBP_QUALITY_KEY = intPreferencesKey("image_attachment_webp_quality")
        private val SHOW_LOCAL_RUNTIME_KEY = booleanPreferencesKey("show_local_runtime")
        private val TERMINAL_FONT_SIZE_KEY = floatPreferencesKey("terminal_font_size")
        private val LOCAL_SETUP_COMPLETED_KEY = booleanPreferencesKey("local_setup_completed")
        private val LOCAL_PROXY_ENABLED_KEY = booleanPreferencesKey("local_proxy_enabled")
        private val LOCAL_PROXY_URL_KEY = stringPreferencesKey("local_proxy_url")
        private val LOCAL_PROXY_NO_PROXY_KEY = stringPreferencesKey("local_proxy_no_proxy")
        private val LOCAL_SERVER_ALLOW_LAN_KEY = booleanPreferencesKey("local_server_allow_lan")
        private val LOCAL_SERVER_USERNAME_KEY = stringPreferencesKey("local_server_username")
        private val LOCAL_SERVER_PASSWORD_KEY = stringPreferencesKey("local_server_password")
        private val LOCAL_SERVER_RUN_IN_BACKGROUND_KEY = booleanPreferencesKey("local_server_run_in_background")
        private val LOCAL_SERVER_AUTO_START_KEY = booleanPreferencesKey("local_server_auto_start")
        private val LOCAL_SERVER_STARTUP_TIMEOUT_SEC_KEY = intPreferencesKey("local_server_startup_timeout_sec")
        private val XIAOMENGLING_MODEL_KEY = stringPreferencesKey("aidelink_xiaomengling_model")
        private val DESKTOP_IDE_KEY = stringPreferencesKey("aidelink_desktop_ide")
        private val DESKTOP_IDE_PATH_KEY = stringPreferencesKey("aidelink_desktop_ide_path")
        private val DESKTOP_IDE_LIST_KEY = stringSetPreferencesKey("aidelink_desktop_ide_list")
        private val MONITOR_INTERVAL_KEY = longPreferencesKey("aidelink_monitor_interval_ms")
        private val MONITOR_HEIGHT_KEY = intPreferencesKey("aidelink_monitor_height_dp")
        private val MONITOR_NO_CHANGE_TIMEOUT_KEY = longPreferencesKey("aidelink_monitor_no_change_timeout_ms")
        private val QUICK_REPLIES_KEY = stringSetPreferencesKey("aidelink_quick_replies")
        private val GLOBAL_LOCATOR_ENABLED_KEY = booleanPreferencesKey("aidelink_global_locator_enabled")

        private const val MONITOR_ENABLED_PREFIX = "aidelink_monitor_enabled_"
        private fun monitorEnabledKey(target: String) =
            booleanPreferencesKey(MONITOR_ENABLED_PREFIX + target)

        /** SharedPreferences key for desktop IDE list (multi-select) */
        private const val DESKTOP_IDE_LIST_PREFS = "desktop_ide_list_prefs"
        private const val DESKTOP_IDE_SINGLE_PREFS = "desktop_ide_single_prefs"

        /** SharedPreferences name used for synchronous locale reads in attachBaseContext. */
        private const val LOCALE_PREFS = "locale_prefs"
        private const val LOCALE_PREFS_KEY = "app_language"

        private const val SERVER_MODEL_HIDDEN_PREFIX = "server_model_hidden_"

        /** Read stored language synchronously — safe to call before Hilt init. */
        fun getStoredLanguage(context: Context): String {
            return context.getSharedPreferences(LOCALE_PREFS, Context.MODE_PRIVATE)
                .getString(LOCALE_PREFS_KEY, "") ?: ""
        }
    }

    private fun serverModelHiddenKey(serverId: String) =
        stringSetPreferencesKey(SERVER_MODEL_HIDDEN_PREFIX + serverId)

    // ── Server URL ────────────────────────────────────────────
    private val DEFAULT_SERVER_URL = BridgeDefaults.DEFAULT_BRIDGE_URL
    private val DEFAULT_WOL_MAC = BridgeDefaults.DEFAULT_WOL_MAC

    // ── Chat Monitor ──────────────────────────────────────────
    suspend fun getMonitorIntervalMsRaw(): Long =
        dataStore.data.first()[MONITOR_INTERVAL_KEY] ?: 4_000L

    suspend fun setMonitorIntervalMs(intervalMs: Long) {
        dataStore.edit { it[MONITOR_INTERVAL_KEY] = intervalMs }
    }

    suspend fun getMonitorHeightDpRaw(target: String): Int =
        dataStore.data.first()[MONITOR_HEIGHT_KEY] ?: 200

    suspend fun setMonitorHeightDp(target: String, heightDp: Int) {
        dataStore.edit { it[MONITOR_HEIGHT_KEY] = heightDp }
    }

    suspend fun getMonitorNoChangeTimeoutMsRaw(): Long =
        dataStore.data.first()[MONITOR_NO_CHANGE_TIMEOUT_KEY] ?: 600_000L

    suspend fun setMonitorNoChangeTimeoutMs(timeoutMs: Long) {
        dataStore.edit { it[MONITOR_NO_CHANGE_TIMEOUT_KEY] = timeoutMs }
    }

    // ── Quick Replies ─────────────────────────────────────────
    suspend fun getQuickReplies(): List<String> =
        (dataStore.data.first()[QUICK_REPLIES_KEY] ?: emptySet()).toList()

    suspend fun setQuickReplies(replies: List<String>) {
        dataStore.edit { it[QUICK_REPLIES_KEY] = replies.toSet() }
    }

    suspend fun addQuickReply(text: String) {
        dataStore.edit { prefs ->
            val current = prefs[QUICK_REPLIES_KEY] ?: emptySet()
            prefs[QUICK_REPLIES_KEY] = current + text
        }
    }

    suspend fun removeQuickReply(text: String) {
        dataStore.edit { prefs ->
            val current = prefs[QUICK_REPLIES_KEY] ?: emptySet()
            prefs[QUICK_REPLIES_KEY] = current - text
        }
    }

    suspend fun getMonitorEnabled(target: String): Boolean =
        dataStore.data.first()[monitorEnabledKey(target)] ?: false

    suspend fun setMonitorEnabled(target: String, enabled: Boolean) {
        dataStore.edit { it[monitorEnabledKey(target)] = enabled }
    }

    // ── Aide Model ──────────────────────────────────
    suspend fun getXiaomenglingModelRaw(): String =
        dataStore.data.first()[XIAOMENGLING_MODEL_KEY] ?: "free"

    fun getXiaomenglingModel(): String = runCatching {
        kotlinx.coroutines.runBlocking { getXiaomenglingModelRaw() }
    }.getOrDefault("free")

    suspend fun setXiaomenglingModel(model: String) {
        dataStore.edit { it[XIAOMENGLING_MODEL_KEY] = model }
    }

    // ── Desktop IDE ──────────────────────────────────────────
    private val DEFAULT_DESKTOP_IDE = BridgeDefaults.DEFAULT_DESKTOP_IDE

    suspend fun getDesktopIdeRaw(): String =
        dataStore.data.first()[DESKTOP_IDE_KEY] ?: DEFAULT_DESKTOP_IDE

    fun getDesktopIde(): String = runCatching {
        kotlinx.coroutines.runBlocking { getDesktopIdeRaw() }
    }.getOrDefault(DEFAULT_DESKTOP_IDE)

    suspend fun setDesktopIde(ide: String) {
        dataStore.edit { it[DESKTOP_IDE_KEY] = ide }
    }

    val globalLocatorEnabled: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[GLOBAL_LOCATOR_ENABLED_KEY] ?: false
    }

    suspend fun setGlobalLocatorEnabled(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[GLOBAL_LOCATOR_ENABLED_KEY] = enabled
        }
    }

    fun globalLocatorEnabledRaw(): Boolean = runCatching {
        kotlinx.coroutines.runBlocking {
            dataStore.data.map { it[GLOBAL_LOCATOR_ENABLED_KEY] ?: false }.first()
        }
    }.getOrDefault(false)

    suspend fun getDesktopIdePathRaw(): String =
        dataStore.data.first()[DESKTOP_IDE_PATH_KEY] ?: ""

    fun getDesktopIdePath(): String = runCatching {
        kotlinx.coroutines.runBlocking { getDesktopIdePathRaw() }
    }.getOrDefault("")

    suspend fun setDesktopIdePath(path: String) {
        dataStore.edit { it[DESKTOP_IDE_PATH_KEY] = path }
    }

    fun getDesktopIdeList(): List<String> {
        return try {
            val prefs = context.getSharedPreferences(DESKTOP_IDE_LIST_PREFS, Context.MODE_PRIVATE)
            val storedSet = prefs.getStringSet(DESKTOP_IDE_LIST_PREFS, null)
            // storedSet 为 null 表示未初始化或用户清空了所有 IDE（Android 空 set 返回 null），返回空列表
            storedSet?.toList() ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun saveDesktopIdeList(ideList: List<String>) {
        try {
            val prefs = context.getSharedPreferences(DESKTOP_IDE_LIST_PREFS, Context.MODE_PRIVATE)
            val editor = prefs.edit()
            // Android putStringSet 对空 set 有 bug（不会真正保存空 set），用 remove 确保清空
            if (ideList.isEmpty()) {
                editor.remove(DESKTOP_IDE_LIST_PREFS)
            } else {
                editor.putStringSet(DESKTOP_IDE_LIST_PREFS, ideList.toSet())
            }
            editor.apply()
        } catch (e: Exception) {
        }
    }

    suspend fun getServerUrlRaw(): String =
        dataStore.data.first()[SERVER_URL_KEY] ?: DEFAULT_SERVER_URL

    /** 服务器 URL 的 Flow，用于响应式监听变化 */
    val serverUrlFlow: kotlinx.coroutines.flow.Flow<String> = dataStore.data
        .map { it[SERVER_URL_KEY] ?: DEFAULT_SERVER_URL }

    fun getServerUrl(): String = runCatching {
        kotlinx.coroutines.runBlocking { getServerUrlRaw() }
    }.getOrDefault(DEFAULT_SERVER_URL)

    suspend fun setServerUrl(url: String) {
        dataStore.edit { it[SERVER_URL_KEY] = url }
    }

    // ── WoL MAC ────────────────────────────────────────────────
    suspend fun getWolMacRaw(): String =
        dataStore.data.first()[WOL_MAC_KEY] ?: DEFAULT_WOL_MAC

    fun getWolMac(): String = runCatching {
        kotlinx.coroutines.runBlocking { getWolMacRaw() }
    }.getOrDefault(DEFAULT_WOL_MAC)

    suspend fun setWolMac(mac: String) {
        dataStore.edit { it[WOL_MAC_KEY] = mac }
    }

    /**
     * Selected language code (e.g. "en", "ru", "de") or empty string for system default.
     */
    val appLanguage: Flow<String> = dataStore.data.map { preferences ->
        preferences[LANGUAGE_KEY] ?: ""
    }

    /**
     * Selected theme: "system", "light", or "dark".
     */
    val appTheme: Flow<String> = dataStore.data.map { preferences ->
        preferences[THEME_KEY] ?: "system"
    }

    /**
     * Set the app language. Pass empty string to use system default.
     * Also writes to SharedPreferences for synchronous read in attachBaseContext.
     */
    suspend fun setAppLanguage(languageCode: String) {
        context.getSharedPreferences(LOCALE_PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(LOCALE_PREFS_KEY, languageCode)
            .apply()
        dataStore.edit { preferences ->
            preferences[LANGUAGE_KEY] = languageCode
        }
    }

    /**
     * Set the app theme. Valid values: "system", "light", "dark".
     */
    suspend fun setAppTheme(theme: String) {
        dataStore.edit { preferences ->
            preferences[THEME_KEY] = theme
        }
    }

    /**
     * Whether dynamic colors (Material You) are enabled. Default: true.
     */
    val dynamicColor: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[DYNAMIC_COLOR_KEY] ?: true
    }

    suspend fun setDynamicColor(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[DYNAMIC_COLOR_KEY] = enabled
        }
    }

    /**
     * Chat font size: "small", "medium", "large". Default: "medium".
     */
    val chatFontSize: Flow<String> = dataStore.data.map { preferences ->
        preferences[FONT_SIZE_KEY] ?: "medium"
    }

    suspend fun setChatFontSize(size: String) {
        dataStore.edit { preferences ->
            preferences[FONT_SIZE_KEY] = size
        }
    }

    /**
     * Whether task completion notifications are enabled. Default: true.
     */
    val notificationsEnabled: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[NOTIFICATIONS_KEY] ?: true
    }

    suspend fun setNotificationsEnabled(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[NOTIFICATIONS_KEY] = enabled
        }
    }

    /**
     * Initial number of messages to load per session. Default: 50.
     */
    val initialMessageCount: Flow<Int> = dataStore.data.map { preferences ->
        preferences[INITIAL_MESSAGE_COUNT_KEY] ?: 50
    }

    suspend fun setInitialMessageCount(count: Int) {
        dataStore.edit { preferences ->
            preferences[INITIAL_MESSAGE_COUNT_KEY] = count
        }
    }

    /**
     * Whether code blocks use word wrap (true) or horizontal scroll (false). Default: false.
     */
    val codeWordWrap: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[CODE_WORD_WRAP_KEY] ?: false
    }

    suspend fun setCodeWordWrap(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[CODE_WORD_WRAP_KEY] = enabled
        }
    }

    /**
     * Whether to show confirmation dialog before sending a message. Default: false.
     */
    val confirmBeforeSend: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[CONFIRM_BEFORE_SEND_KEY] ?: false
    }

    suspend fun setConfirmBeforeSend(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[CONFIRM_BEFORE_SEND_KEY] = enabled
        }
    }

    /**
     * Whether AMOLED pure black dark theme is enabled. Default: false.
     */
    val amoledDark: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[AMOLED_DARK_KEY] ?: false
    }

    suspend fun setAmoledDark(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[AMOLED_DARK_KEY] = enabled
        }
    }

    /**
     * Whether compact message spacing is enabled. Default: false.
     */
    val compactMessages: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[COMPACT_MESSAGES_KEY] ?: false
    }

    suspend fun setCompactMessages(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[COMPACT_MESSAGES_KEY] = enabled
        }
    }

    /**
     * Whether tool cards are collapsed by default. Default: false.
     */
    val collapseTools: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[COLLAPSE_TOOLS_KEY] ?: false
    }

    suspend fun setCollapseTools(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[COLLAPSE_TOOLS_KEY] = enabled
        }
    }

    /**
     * Whether haptic feedback is enabled. Default: true.
     */
    val hapticFeedback: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[HAPTIC_FEEDBACK_KEY] ?: true
    }

    suspend fun setHapticFeedback(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[HAPTIC_FEEDBACK_KEY] = enabled
        }
    }

    /**
     * Reconnect mode: "aggressive" (1-5s), "normal" (1-30s), "conservative" (1-60s).
     * Default: "normal".
     */
    val reconnectMode: Flow<String> = dataStore.data.map { preferences ->
        preferences[RECONNECT_MODE_KEY] ?: "normal"
    }

    suspend fun setReconnectMode(mode: String) {
        dataStore.edit { preferences ->
            preferences[RECONNECT_MODE_KEY] = mode
        }
    }

    /**
     * Whether to keep screen on during streaming. Default: false.
     */
    val keepScreenOn: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[KEEP_SCREEN_ON_KEY] ?: false
    }

    suspend fun setKeepScreenOn(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[KEEP_SCREEN_ON_KEY] = enabled
        }
    }

    /**
     * Whether notifications are silent (no sound/vibration). Default: false.
     */
    val silentNotifications: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[SILENT_NOTIFICATIONS_KEY] ?: false
    }

    suspend fun setSilentNotifications(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[SILENT_NOTIFICATIONS_KEY] = enabled
        }
    }

    /** 同步读取通知开关（用于服务中快速判断） */
    fun notificationsEnabledRaw(): Boolean = runCatching {
        kotlinx.coroutines.runBlocking {
            dataStore.data.map { it[NOTIFICATIONS_KEY] ?: true }.first()
        }
    }.getOrDefault(true)

    /** 同步读取静音通知开关 */
    fun silentNotificationsRaw(): Boolean = runCatching {
        kotlinx.coroutines.runBlocking {
            dataStore.data.map { it[SILENT_NOTIFICATIONS_KEY] ?: false }.first()
        }
    }.getOrDefault(false)

    /** 同步读取触觉反馈开关 */
    fun hapticFeedbackRaw(): Boolean = runCatching {
        kotlinx.coroutines.runBlocking {
            dataStore.data.map { it[HAPTIC_FEEDBACK_KEY] ?: true }.first()
        }
    }.getOrDefault(true)

    /**
     * Whether image attachments are optimized (resize + WebP) before sending. Default: true.
     */
    val compressImageAttachments: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[COMPRESS_IMAGE_ATTACHMENTS_KEY] ?: true
    }

    suspend fun setCompressImageAttachments(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[COMPRESS_IMAGE_ATTACHMENTS_KEY] = enabled
        }
    }

    /**
     * Max long side (in px) used when resizing image attachments before sending.
     * Use 0 to keep original resolution. Default: 1440.
     */
    val imageAttachmentMaxLongSide: Flow<Int> = dataStore.data.map { preferences ->
        val value = preferences[IMAGE_ATTACHMENT_MAX_LONG_SIDE_KEY] ?: 1440
        if (value <= 0) 0 else value.coerceIn(720, 4096)
    }

    suspend fun setImageAttachmentMaxLongSide(px: Int) {
        dataStore.edit { preferences ->
            preferences[IMAGE_ATTACHMENT_MAX_LONG_SIDE_KEY] = if (px <= 0) 0 else px.coerceIn(720, 4096)
        }
    }

    /**
     * WebP quality used for image attachment optimization. Default: 60.
     */
    val imageAttachmentWebpQuality: Flow<Int> = dataStore.data.map { preferences ->
        (preferences[IMAGE_ATTACHMENT_WEBP_QUALITY_KEY] ?: 60).coerceIn(1, 100)
    }

    suspend fun setImageAttachmentWebpQuality(quality: Int) {
        dataStore.edit { preferences ->
            preferences[IMAGE_ATTACHMENT_WEBP_QUALITY_KEY] = quality.coerceIn(1, 100)
        }
    }

    /**
     * Whether to show local runtime controls on Home screen. Default: true.
     */
    val showLocalRuntime: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[SHOW_LOCAL_RUNTIME_KEY] ?: true
    }

    suspend fun setShowLocalRuntime(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[SHOW_LOCAL_RUNTIME_KEY] = enabled
        }
    }

    /**
     * Default terminal font size in sp. Default: 13.
     */
    val terminalFontSize: Flow<Float> = dataStore.data.map { preferences ->
        (preferences[TERMINAL_FONT_SIZE_KEY] ?: 13f).coerceIn(6f, 20f)
    }

    suspend fun setTerminalFontSize(size: Float) {
        dataStore.edit { preferences ->
            preferences[TERMINAL_FONT_SIZE_KEY] = size.coerceIn(6f, 20f)
        }
    }

    /**
     * Whether the local Termux setup has been completed at least once.
     */
    val localSetupCompleted: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[LOCAL_SETUP_COMPLETED_KEY] ?: false
    }

    suspend fun setLocalSetupCompleted(completed: Boolean) {
        dataStore.edit { preferences ->
            preferences[LOCAL_SETUP_COMPLETED_KEY] = completed
        }
    }

    /**
     * Whether local runtime should use an outbound proxy. Default: false.
     */
    val localProxyEnabled: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[LOCAL_PROXY_ENABLED_KEY] ?: false
    }

    suspend fun setLocalProxyEnabled(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[LOCAL_PROXY_ENABLED_KEY] = enabled
        }
    }

    /**
     * Proxy URL for local runtime outbound requests (e.g., http://host:port).
     * Empty string means disabled/not set.
     */
    val localProxyUrl: Flow<String> = dataStore.data.map { preferences ->
        preferences[LOCAL_PROXY_URL_KEY] ?: ""
    }

    suspend fun setLocalProxyUrl(url: String) {
        dataStore.edit { preferences ->
            preferences[LOCAL_PROXY_URL_KEY] = url.trim()
        }
    }

    /**
     * NO_PROXY/NO_PROXY exclusions used by local runtime.
     */
    val localProxyNoProxy: Flow<String> = dataStore.data.map { preferences ->
        preferences[LOCAL_PROXY_NO_PROXY_KEY] ?: LocalServerManager.DEFAULT_NO_PROXY_LIST
    }

    suspend fun setLocalProxyNoProxy(value: String) {
        dataStore.edit { preferences ->
            val normalized = value
                .split(',')
                .map { it.trim() }
                .filter { it.isNotBlank() }
                .joinToString(",")
            preferences[LOCAL_PROXY_NO_PROXY_KEY] = if (normalized.isBlank()) {
                LocalServerManager.DEFAULT_NO_PROXY_LIST
            } else {
                normalized
            }
        }
    }

    /**
     * Whether local runtime should bind to all interfaces (0.0.0.0). Default: false.
     */
    val localServerAllowLan: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[LOCAL_SERVER_ALLOW_LAN_KEY] ?: false
    }

    suspend fun setLocalServerAllowLan(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[LOCAL_SERVER_ALLOW_LAN_KEY] = enabled
        }
    }

    /**
     * Optional username used by local runtime server auth.
     * Empty means server default username is used.
     */
    val localServerUsername: Flow<String> = dataStore.data.map { preferences ->
        preferences[LOCAL_SERVER_USERNAME_KEY] ?: ""
    }

    suspend fun setLocalServerUsername(value: String) {
        dataStore.edit { preferences ->
            preferences[LOCAL_SERVER_USERNAME_KEY] = value.trim()
        }
    }

    /**
     * Password used by local runtime server (OPENCODE_SERVER_PASSWORD).
     * Empty means unsecured local server.
     */
    val localServerPassword: Flow<String> = dataStore.data.map { preferences ->
        preferences[LOCAL_SERVER_PASSWORD_KEY] ?: ""
    }

    suspend fun setLocalServerPassword(value: String) {
        dataStore.edit { preferences ->
            preferences[LOCAL_SERVER_PASSWORD_KEY] = value.trim()
        }
    }

    /**
     * Whether local runtime start command should run in background via Termux RunCommandService.
     */
    val localServerRunInBackground: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[LOCAL_SERVER_RUN_IN_BACKGROUND_KEY] ?: true
    }

    suspend fun setLocalServerRunInBackground(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[LOCAL_SERVER_RUN_IN_BACKGROUND_KEY] = enabled
        }
    }

    /**
     * Whether to auto-start local runtime on app launch when it is installed but not running.
     */
    val localServerAutoStart: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[LOCAL_SERVER_AUTO_START_KEY] ?: false
    }

    suspend fun setLocalServerAutoStart(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[LOCAL_SERVER_AUTO_START_KEY] = enabled
        }
    }

    /**
     * Startup timeout (seconds) for waiting local runtime readiness. Default: 30.
     */
    val localServerStartupTimeoutSec: Flow<Int> = dataStore.data.map { preferences ->
        (preferences[LOCAL_SERVER_STARTUP_TIMEOUT_SEC_KEY] ?: 30).coerceIn(10, 120)
    }

    suspend fun setLocalServerStartupTimeoutSec(value: Int) {
        dataStore.edit { preferences ->
            preferences[LOCAL_SERVER_STARTUP_TIMEOUT_SEC_KEY] = value.coerceIn(10, 120)
        }
    }

    /**
     * Hidden model keys for a server. Key format: "providerId:modelId".
     */
    fun hiddenModels(serverId: String): Flow<Set<String>> = dataStore.data.map { preferences ->
        preferences[serverModelHiddenKey(serverId)] ?: emptySet()
    }

    /**
     * Set model visibility for a server.
     * visible=true removes it from hidden set, visible=false adds it.
     */
    suspend fun setModelVisibility(serverId: String, providerId: String, modelId: String, visible: Boolean) {
        val key = "$providerId:$modelId"
        val prefsKey = serverModelHiddenKey(serverId)
        dataStore.edit { preferences ->
            val current = preferences[prefsKey] ?: emptySet()
            preferences[prefsKey] = if (visible) {
                current - key
            } else {
                current + key
            }
        }
    }

    // ── Server Sync ───────────────────────────────────────────

    private var _bridgeApi: cc.aidelink.app.data.api.BridgeApi? = null

    fun setBridgeApi(api: cc.aidelink.app.data.api.BridgeApi) {
        _bridgeApi = api
    }

    suspend fun syncFromServer() {
        val api = _bridgeApi ?: return
        val payload = api.fetchSettings() ?: return
        dataStore.edit { prefs ->
            payload.wol_mac?.let { prefs[WOL_MAC_KEY] = it }
            payload.app_language?.let { prefs[LANGUAGE_KEY] = it }
            payload.app_theme?.let { prefs[THEME_KEY] = it }
            payload.dynamic_color?.let { prefs[DYNAMIC_COLOR_KEY] = it }
            payload.notifications_enabled?.let { prefs[NOTIFICATIONS_KEY] = it }
            payload.haptic_feedback?.let { prefs[HAPTIC_FEEDBACK_KEY] = it }
            payload.monitor_interval_ms?.let { prefs[MONITOR_INTERVAL_KEY] = it }
            payload.monitor_height_dp?.let { prefs[MONITOR_HEIGHT_KEY] = it }
            payload.xiaomengling_model?.let { prefs[XIAOMENGLING_MODEL_KEY] = it }
            payload.desktop_ide?.let { prefs[DESKTOP_IDE_KEY] = it }
            payload.desktop_ide_path?.let { prefs[DESKTOP_IDE_PATH_KEY] = it }
        }
    }

    suspend fun pushToServer() {
        val api = _bridgeApi ?: return
        val prefs = dataStore.data.first()
        val fields = mapOf<String, kotlinx.serialization.json.JsonElement>(
            "server_url" to kotlinx.serialization.json.JsonPrimitive(prefs[SERVER_URL_KEY] ?: DEFAULT_SERVER_URL),
            "wol_mac" to kotlinx.serialization.json.JsonPrimitive(prefs[WOL_MAC_KEY] ?: DEFAULT_WOL_MAC),
            "app_language" to kotlinx.serialization.json.JsonPrimitive(prefs[LANGUAGE_KEY] ?: ""),
            "app_theme" to kotlinx.serialization.json.JsonPrimitive(prefs[THEME_KEY] ?: "system"),
            "dynamic_color" to kotlinx.serialization.json.JsonPrimitive(prefs[DYNAMIC_COLOR_KEY] ?: true),
            "notifications_enabled" to kotlinx.serialization.json.JsonPrimitive(prefs[NOTIFICATIONS_KEY] ?: true),
            "haptic_feedback" to kotlinx.serialization.json.JsonPrimitive(prefs[HAPTIC_FEEDBACK_KEY] ?: true),
            "monitor_interval_ms" to kotlinx.serialization.json.JsonPrimitive(prefs[MONITOR_INTERVAL_KEY] ?: 4000L),
            "monitor_height_dp" to kotlinx.serialization.json.JsonPrimitive(prefs[MONITOR_HEIGHT_KEY] ?: 200),
            "xiaomengling_model" to kotlinx.serialization.json.JsonPrimitive(prefs[XIAOMENGLING_MODEL_KEY] ?: "free"),
            "desktop_ide" to kotlinx.serialization.json.JsonPrimitive(prefs[DESKTOP_IDE_KEY] ?: "trae"),
            "desktop_ide_path" to kotlinx.serialization.json.JsonPrimitive(prefs[DESKTOP_IDE_PATH_KEY] ?: ""),
        )
        val body = kotlinx.serialization.json.JsonObject(fields)
        api.patchSetting(body)
    }

    suspend fun pushSettingToServer(key: String, value: kotlinx.serialization.json.JsonElement) {
        val api = _bridgeApi ?: return
        api.patchSetting(key, value)
    }
}

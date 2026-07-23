package cc.aidelink.app.ui.screens.chat



import android.graphics.Bitmap

import android.graphics.BitmapFactory

import androidx.compose.ui.graphics.ImageBitmap

import androidx.compose.ui.graphics.asAndroidBitmap

import androidx.compose.ui.graphics.asImageBitmap

import androidx.compose.ui.unit.Dp

import androidx.compose.ui.unit.dp

import androidx.lifecycle.ViewModel

import androidx.lifecycle.viewModelScope

import cc.aidelink.app.data.api.BridgeApi

import cc.aidelink.app.domain.model.bridge.ChatMessage

import cc.aidelink.app.domain.model.bridge.ClipboardItem

import cc.aidelink.app.domain.model.bridge.DesktopIde

import cc.aidelink.app.domain.model.bridge.ProjectNode

import cc.aidelink.app.domain.model.bridge.AideTask
import cc.aidelink.app.domain.model.bridge.InputPoint

import cc.aidelink.app.data.repository.ConnectionState

import cc.aidelink.app.data.repository.SettingsRepository

import dagger.hilt.android.lifecycle.HiltViewModel

import kotlinx.coroutines.Dispatchers

import kotlinx.coroutines.async

import kotlinx.coroutines.coroutineScope

import kotlinx.coroutines.Job

import kotlinx.coroutines.delay

import kotlinx.coroutines.withContext

import kotlinx.coroutines.flow.MutableStateFlow

import kotlinx.coroutines.flow.StateFlow

import kotlinx.coroutines.flow.asStateFlow

import kotlinx.coroutines.launch

import javax.inject.Inject

import java.util.UUID

private val PROJECT_SURFACES = setOf("android", "web", "windows")



enum class PromptAction(val label: String, val emoji: String) {

    BUG_FIX("修 Bug", "🐛"),

    OPTIMIZE("功能优化", "✨"),

    NEW_FEATURE("新增功能", "➕"),

    FEATURE_LOCK("功能锁定", "🔒"),

}

internal fun resolveStartupTargetKey(savedKey: String, processes: List<DesktopIde>?, selectedIdeKeys: Set<String> = emptySet()): String {
    // selectedIdeKeys 为空（用户关闭了所有 IDE 或未初始化），默认到 AIDELINK
    if (selectedIdeKeys.isEmpty()) return AideLinkChatViewModel.Target.AIDELINK.key
    // savedKey 不在用户选择的列表里，fallback 到 AIDELINK
    val validSaved = if (savedKey != AideLinkChatViewModel.Target.AIDELINK.key && savedKey in selectedIdeKeys) savedKey else AideLinkChatViewModel.Target.AIDELINK.key
    // 启动时只恢复用户上次选择的目标，不根据运行中的 IDE 轮流抢占目标，
    // 避免 Aide → ChatGPT → OpenCode 的连续跳转。
    return validSaved
}

internal fun shouldFallbackToOfflineTaskCache(bridgeOnline: Boolean, serverTaskCreated: Boolean): Boolean {
    return !bridgeOnline || !serverTaskCreated
}

internal fun normalizeTaskTarget(targetKey: String?): String {
    return targetKey?.takeUnless { it == AideLinkChatViewModel.Target.AIDELINK.key }.orEmpty()
}



@HiltViewModel

class AideLinkChatViewModel @Inject constructor(

    @dagger.hilt.android.qualifiers.ApplicationContext private val appContext: android.content.Context,

    val bridgeApi: BridgeApi,

    private val settingsRepository: SettingsRepository,

) : ViewModel() {
    data class Target(val key: String, val label: String, val icon: String = "", val colorHex: String = "#90A4AE") {

        companion object {

            val AIDELINK = Target("aide", "Aide", "💙", "#64B5F6")

            // 特殊 IDE 引用（用于 IDE 特定优化）

            val TRAE = Target("trae", "Trae", "", "#4FC3F7")

            val ANTIGRAVITY = Target("antigravity_ide", "Antigravity IDE", "", "#CE93D8")

            val OPENCODE = Target("opencode", "OpenCode", "", "#81C784")

            // OpenCode 桌面端、Web 和原生会话页共享同一服务端会话。
            // 桌面 OpenCode 使用 IDE 扫描返回的 opencode key；Web 使用独立 oc_web key。
            val OPENCODE_WEB = Target("oc_web", "OpenCode Web", "", "#26A69A")

            val MIMOCODE = Target("mimo", "MiMoCode", "", "#FFB74D")

            // 当前桌面入口实际显示为 ChatGPT；保留 codex key 仅用于兼容历史配置。
            val CODEX = Target("codex", "ChatGPT", "", "#58A6FF")



            private var _dynamic: List<Target> = emptyList()



            fun setDynamicTargets(targets: List<Target>) {

                _dynamic = targets

            }



            val entries: List<Target>

                get() {
                    val fixed = listOf(AIDELINK, TRAE, ANTIGRAVITY, OPENCODE, OPENCODE_WEB, MIMOCODE, CODEX)
                    // 扫描到的桌面 IDE 名称优先，避免 codex/ChatGPT 等固定兼容 key
                    // 在主界面和校准页显示过时的内置名称。
                    val dynamicByKey = _dynamic.associateBy { it.key }
                    return fixed.map { dynamicByKey[it.key] ?: it } +
                        _dynamic.filterNot { dyn -> fixed.any { it.key == dyn.key } }
                }



            // 桌面 OpenCode 与 OpenCode Web 保持独立，不做别名迁移。
            fun canonicalUserKey(key: String): String = key

            fun fromKey(key: String): Target {
                val canonicalKey = canonicalUserKey(key)
                return entries.find { it.key == canonicalKey } ?: Target(canonicalKey, canonicalKey)
            }

        }

    }



    enum class DialogCropSource {

        FULL, WINDOW

    }



    data class UiState(

        val messages: List<ChatMessage> = emptyList(),

        val input: String = "",

        val target: Target = Target.AIDELINK,

        val targetInitialized: Boolean = false,

        val sending: Boolean = false,

        val loading: Boolean = false,

        val errorMessage: String? = null,

        val toastMessage: String? = null,

        val monitorActive: Boolean = false,

        val monitorImage: ImageBitmap? = null,

        val monitorOriginalWidth: Int = 0,  // 监控全屏截图原始宽度

        val monitorOriginalHeight: Int = 0,  // 监控全屏截图原始高度

        val monitorIntervalMs: Long = 4000L,

        val monitorByTarget: Map<Target, Boolean> = emptyMap(),

        val cropLeft: Int = 0,

        val cropRight: Int = 0,

        val cropTop: Int = 0,

        val cropBottom: Int = 0,

        val calibWidth: Int = 0,

        val calibHeight: Int = 0,

        val dialogPosition: String = "center",

        val focusInputEnabled: Boolean = false,

        val inputPoint: InputPoint? = null,

        val monitorCropMode: Boolean = true,

        val showLiveMonitorDialog: Boolean = false,

        val monitorHeightDp: Int = 420,

        val dialogCropSource: DialogCropSource? = null,

        val dialogUncroppedImage: ImageBitmap? = null,

        val originalImageWidth: Int = 0,

        val originalImageHeight: Int = 0,

        val clipboardItems: List<ClipboardItem> = emptyList(),

        val clipboardLoading: Boolean = false,

        val uploading: Boolean = false,

        val uploadResult: String? = null,

        val mimoRunning: Boolean = false,

        val mimoLoading: Boolean = false,

        val bridgeOnline: Boolean = false,

        val bridgeConnecting: Boolean = true,

        val selectedIdeList: List<String> = emptyList(),

        val ideRunningMap: Map<String, Boolean> = emptyMap(),

        val quickReplies: List<String> = emptyList(),

        val desktopIdes: List<DesktopIde> = emptyList(),

        val desktopIdesLoading: Boolean = false,

        val showDesktopIdeDialog: Boolean = false,

        val ideHistorySessions: List<cc.aidelink.app.domain.model.bridge.IdeHistorySession> = emptyList(),

        val ideHistoryLoading: Boolean = false,

        val monitors: List<cc.aidelink.app.domain.model.bridge.MonitorInfo> = emptyList(),

        val selectedMonitor: String? = null,

        val manualMonitorOverride: Boolean = false,

        val windowFound: Boolean = true,

        // ─── 任务提示词构建器 ───

        val showTaskPromptDialog: Boolean = false,

        val taskPromptTaskId: String = "",

        val taskPromptTaskText: String = "",

        val taskPromptAction: PromptAction? = null,

        val taskPromptDescription: String = "",

        val taskPromptGenerated: String = "",

        // ─── 提示词模式（区分发送按钮图标）───

        val isPromptMode: Boolean = false,

        

        // ─── 项目状态 ───

        val currentProjectPath: String = "",

        val currentProjectName: String = "",

        val projects: List<BridgeApi.ProjectInfo> = emptyList(),

        val currentProjectCapabilities: List<String> = emptyList(),

        val selectedSurface: String? = null,

        // ─── 任务管理状态 ───

        val tasks: List<AideTask> = emptyList(),

        val tasksLoading: Boolean = false,

        // 批量操作

        val batchMode: Boolean = false,

        val selectedTaskIds: Set<String> = emptySet(),

        val activeTaskId: String? = null,

        val editingTaskId: String? = null,

        val inputDraftBeforeTaskEdit: String = "",

        // ─── 派发操作 ───

        val showDispatchDialog: Boolean = false,

        val dispatchTaskIds: Set<String> = emptySet(),

        // ─── 项目地图状态 ───

        val projectMapExpanded: Boolean = false,

        val projectMapLoading: Boolean = false,

        val projectMapOnlyVisible: Boolean = false,

        val projectMap: List<ProjectNode> = emptyList(),

        val selectedNode: ProjectNode? = null,

        val promptAction: PromptAction? = null,

        val promptDescription: String = "",

        val promptVersion: String = "v1.0",

        val generatedPrompt: String = "",

        val showWebButton: Boolean = false,

        val mimoWebUrl: String = "",

        val promptCandidates: List<cc.aidelink.app.domain.model.bridge.PromptCandidate> = emptyList(),

        val promptPredictLoading: Boolean = false,

        val monitorScreenVisible: Boolean = true,

        val monitorSleeping: Boolean = false,

        val monitorPollingPaused: Boolean = false,

        val monitorNoChangeTimeoutMs: Long = 600_000L,

        val ocWebRunning: Boolean = false,

        val ocWebLoading: Boolean = false,

        val ocWebPort: Int = 4096,

        val ocWebStatusMessage: String? = null,

        val ocWebLatestReply: String? = null,

        val ocWebSessionTitle: String? = null,

        // ─── Codex 额度 ───

        val codexQuota: cc.aidelink.app.domain.model.bridge.CodexQuota? = null,

        val codexQuotaLoading: Boolean = false,

    )





    private val _state = MutableStateFlow(UiState())

    private var _initialIdeAutoSwitchDone = false

    private var _initialRunningAutoSwitchDone = false

    val state: StateFlow<UiState> = _state.asStateFlow()



    private var monitorJob: Job? = null

    private var lastScreenshotHash: Long = 0L

    private var consecutiveNoChangeCount: Int = 0

    private var lastChangeTimeMs: Long = 0L

    companion object {

        private const val NO_CHANGE_THRESHOLD = 3

        private const val NO_CHANGE_TIMEOUT_MS = 10 * 60 * 1000L // 10 minutes

    }



    init {

        viewModelScope.launch(Dispatchers.IO) {

            val savedUrl = settingsRepository.getServerUrlRaw()

            if (savedUrl.isNotBlank() && savedUrl != bridgeApi.baseUrl) {

                bridgeApi.updateBaseUrl(savedUrl)

            }

            // 立即加载本地缓存的历史消息和离线任务，不等待网络
            val cachedMsgs = cc.aidelink.app.data.repository.OfflineTaskCache.getChatHistory(appContext)
            if (cachedMsgs.isNotEmpty()) {
                _state.value = _state.value.copy(messages = cachedMsgs, loading = false)
            }
            val cachedTasks = cc.aidelink.app.data.repository.OfflineTaskCache.getServerTasks(appContext)
            if (cachedTasks.isNotEmpty()) {
                _state.value = _state.value.copy(tasks = cachedTasks)
            }
            loadOfflineTasks()

            // 尽早启动 reload() 和 loadTasks()，它们各自在 IO 协程里运行，不阻塞 init
            reload()
            loadTasks()

            val rawLastIdeKey = runCatching { settingsRepository.getDesktopIdeRaw() }.getOrDefault(Target.AIDELINK.key)
            val lastIdeKey = Target.canonicalUserKey(rawLastIdeKey)
            val savedIdeKeys = settingsRepository.getDesktopIdeList().map(Target::canonicalUserKey).toSet()
            if (rawLastIdeKey != lastIdeKey) {
                runCatching { settingsRepository.setDesktopIde(lastIdeKey) }
            }
            val locallyRestoredKey = if (
                lastIdeKey == Target.AIDELINK.key ||
                lastIdeKey == Target.OPENCODE_WEB.key ||
                lastIdeKey in savedIdeKeys
            ) {
                lastIdeKey
            } else {
                Target.AIDELINK.key
            }
            // 本地目标恢复不应等待 IDE/进程网络请求，否则首屏会先显示错误目标或长时间空白。
            _state.value = _state.value.copy(
                target = Target.fromKey(locallyRestoredKey),
                targetInitialized = true,
            )
            // 网络请求加 3 秒超时，避免服务端不可达时阻塞 init
            val (startupIdes, startupProcesses) = coroutineScope {
                val idesRequest = async { runCatching { bridgeApi.getDesktopIdes() }.getOrNull() }
                val processesRequest = async { runCatching { bridgeApi.getIdeProcesses() }.getOrNull() }
                try {
                    kotlinx.coroutines.withTimeoutOrNull(3000L) {
                        idesRequest.await() to processesRequest.await()
                    } ?: (null to null)
                } catch (_: Exception) { null to null }
            }
            startupIdes?.let { ides ->
                Target.setDynamicTargets(ides.map { Target(it.key, it.name, it.icon, it.color) })
            }
            // 启动目标只恢复用户上次选择，不再根据当前运行中的 IDE 推断。
            val startupTargetKey = if (
                lastIdeKey == Target.AIDELINK.key ||
                lastIdeKey == Target.OPENCODE_WEB.key ||
                lastIdeKey in savedIdeKeys
            ) {
                lastIdeKey
            } else {
                Target.AIDELINK.key
            }
            val targetEnum = Target.fromKey(startupTargetKey)

            if (startupProcesses != null) {
                _initialRunningAutoSwitchDone = true
                _state.value = _state.value.copy(
                    ideRunningMap = startupProcesses.associate { it.key to it.running },
                )
                // 仅同步运行状态，不修改用户保存的目标 IDE。
            }



            val byTarget = Target.entries.associateWith { target ->

                runCatching { settingsRepository.getMonitorEnabled(target.key) }.getOrDefault(false)

            }

            _state.value = _state.value.copy(

                target = targetEnum,

                targetInitialized = true,

                monitorIntervalMs = settingsRepository.getMonitorIntervalMsRaw(),

                monitorHeightDp = settingsRepository.getMonitorHeightDpRaw(targetEnum.key),

                monitorNoChangeTimeoutMs = settingsRepository.getMonitorNoChangeTimeoutMsRaw(),

                monitorByTarget = byTarget,

                monitorActive = byTarget[targetEnum] == true,

            )

            // loadProject 和 crop config 网络请求加超时，避免阻塞 init
            kotlinx.coroutines.withTimeoutOrNull(3000L) { loadProject() }

            kotlinx.coroutines.withTimeoutOrNull(3000L) {
                runCatching {

                    val activeConfig = bridgeApi.fetchActiveCropConfig(targetEnum.key)

                    if (activeConfig != null) {

                        _state.value = _state.value.copy(

                            cropLeft = activeConfig.left,

                            cropRight = activeConfig.right,

                            cropTop = activeConfig.top,

                            cropBottom = activeConfig.bottom,

                            calibWidth = activeConfig.calib_width,

                            calibHeight = activeConfig.calib_height,

                            dialogPosition = activeConfig.dialog_position,

                            focusInputEnabled = activeConfig.focus_input_enabled,

                            inputPoint = activeConfig.input_region,

                        )

                    }

                }
            }

            if (_state.value.monitorActive) {

                startMonitorPolling()

            }

            reloadCropConfigs()



            kotlinx.coroutines.withContext(Dispatchers.Main) {

                // reload() 和 loadTasks() 已在缓存加载后尽早调用，此处不再重复

                // IDE 列表更新放到 IO 线程，避免阻塞 UI
                viewModelScope.launch(Dispatchers.IO) {
                    runCatching {
                        val ides = startupIdes ?: bridgeApi.getDesktopIdes()
                        _state.value = _state.value.copy(desktopIdes = ides)
                        Target.setDynamicTargets(ides.map { AideLinkChatViewModel.Target(it.key, it.name, it.icon, it.color) })
                        // 智能合并：过滤掉服务端不存在的无效 key（如 trae → trae_cn 迁移）
                        if (ides.isNotEmpty()) {
                            val serverKeys = ides.map { it.key }.toSet() + Target.OPENCODE_WEB.key
                            val savedKeys = settingsRepository.getDesktopIdeList().map(Target::canonicalUserKey).toSet()
                            // savedKeys 为空表示用户明确关闭了所有 IDE，尊重用户选择，不强制填充
                            if (savedKeys.isNotEmpty()) {
                                val filtered = savedKeys.intersect(serverKeys).toList()
                                if (filtered != savedKeys.toList()) {
                                    settingsRepository.saveDesktopIdeList(filtered)
                                }
                                _state.value = _state.value.copy(selectedIdeList = filtered)
                            }
                            // 当前 target 不在服务端有效列表里时重置，避免发送到无效 IDE（如 trae 已迁移为 trae_cn）
                            if (_state.value.target.key != "aide" && _state.value.target.key !in serverKeys) {
                                _state.value = _state.value.copy(target = AideLinkChatViewModel.Target.AIDELINK)
                            }
                        }
                    }
                }

                loadSelectedIdeList()

                loadIdeRunningStatus()

                loadQuickReplies()

                loadMimoWebUrl()

                val pendingIde = appContext.getSharedPreferences("aidelink_navigation", android.content.Context.MODE_PRIVATE)
                    .getString("pending_calibration_ide", null)
                if (!pendingIde.isNullOrBlank()) {
                    appContext.getSharedPreferences("aidelink_navigation", android.content.Context.MODE_PRIVATE)
                        .edit().remove("pending_calibration_ide").apply()
                    _state.value = _state.value.copy(target = Target.fromKey(pendingIde))
                    setShowLiveMonitorDialog(true)
                }

            }

        }



        // 观察全局连接状态

        viewModelScope.launch {

            var wasOnline = false

            ConnectionState.bridgeOnline.collect { online ->

                _state.value = _state.value.copy(bridgeOnline = online)

                // 连接恢复时刷新状态；离线任务由用户点击后同步并派发。

                if (online && !wasOnline) {

                    loadIdeRunningStatus()

                    loadDesktopIdes()

                    loadTasks()

                }

                wasOnline = online

            }

        }

        viewModelScope.launch {

            ConnectionState.connecting.collect { connecting ->

                _state.value = _state.value.copy(bridgeConnecting = connecting)

            }

        }

        viewModelScope.launch {

            settingsRepository.serverUrlFlow.collect { newUrl ->

                if (newUrl.isNotBlank() && newUrl != bridgeApi.baseUrl) {

                    bridgeApi.updateBaseUrl(newUrl)

                    reload()

                    loadTasks()

                    loadIdeRunningStatus()

                    loadDesktopIdes()

                }

            }

        }

    }



    fun reloadCropConfigs() {

        viewModelScope.launch(Dispatchers.IO) {

            runCatching { bridgeApi.fetchCropConfigs() }

                .onSuccess { configs ->

                    val cfg = configs[_state.value.target.key]

                    if (cfg != null) {

                        _state.value = _state.value.copy(

                            cropLeft = cfg.left,

                            cropRight = cfg.right,

                            cropTop = cfg.top,

                            cropBottom = cfg.bottom,

                        )

                    }

                }

        }

    }



    fun clearError() {
        _state.value = _state.value.copy(errorMessage = null)
    }

    fun clearToast(expectedMessage: String? = null) {
        if (expectedMessage == null || _state.value.toastMessage == expectedMessage) {
            _state.value = _state.value.copy(toastMessage = null)
        }
    }

    fun reload() {

        viewModelScope.launch(Dispatchers.IO) {

            // 先加载本地缓存的历史消息，立即显示
            val cached = cc.aidelink.app.data.repository.OfflineTaskCache.getChatHistory(appContext)
            if (cached.isNotEmpty()) {
                _state.value = _state.value.copy(messages = cached, loading = false)
            } else {
                _state.value = _state.value.copy(loading = true, errorMessage = null)
            }

            loadProject()

            loadTasks()

            runCatching { bridgeApi.fetchHistory(limit = 100) }

                .onSuccess { msgs ->
                    _state.value = _state.value.copy(messages = msgs, loading = false)
                    // 缓存到本地（空列表不覆盖，避免丢失之前的好缓存）
                    if (msgs.isNotEmpty()) {
                        cc.aidelink.app.data.repository.OfflineTaskCache.saveChatHistory(appContext, msgs)
                    }
                }

                .onFailure { e -> _state.value = _state.value.copy(loading = false, errorMessage = e.message) }

        }

    }



    fun setInput(text: String) {

        _state.value = _state.value.copy(input = text)

    }



    fun setTarget(target: Target, persist: Boolean = true) {

        // 校准弹窗打开期间锁定当前 IDE，避免主界面恢复上次目标时
        // 用另一个 IDE 的裁剪配置覆盖已经读取到的校准数据。
        if (_state.value.showLiveMonitorDialog && target.key != _state.value.target.key) return

        val wasActive = _state.value.monitorActive

        _state.value = _state.value.copy(target = target, selectedMonitor = null, manualMonitorOverride = false)

        reloadCropConfigs()

        viewModelScope.launch(Dispatchers.IO) {

            if (persist) {
                runCatching { settingsRepository.setDesktopIde(target.key) }
            }

            val height = settingsRepository.getMonitorHeightDpRaw(target.key)

            val enabled = runCatching { settingsRepository.getMonitorEnabled(target.key) }.getOrDefault(false)

            _state.value = _state.value.copy(

                monitorHeightDp = height,

                monitorActive = enabled,

                monitorByTarget = _state.value.monitorByTarget + (target to enabled),

            )

            // 先用 fetchActiveCropConfig 同步获取新 IDE 的裁剪值

            runCatching {

                val activeConfig = bridgeApi.fetchActiveCropConfig(target.key)

                if (activeConfig != null) {

                    _state.value = _state.value.copy(

                        cropLeft = activeConfig.left,

                        cropRight = activeConfig.right,

                        cropTop = activeConfig.top,

                        cropBottom = activeConfig.bottom,

                        calibWidth = activeConfig.calib_width,

                        calibHeight = activeConfig.calib_height,

                        dialogPosition = activeConfig.dialog_position,

                    )

                }

            }

            if (enabled && !wasActive) {

                startMonitorPolling()

            } else if (!enabled && wasActive) {

                stopMonitorPolling()

            }

            // 裁剪值更新后再刷新截图

            if (enabled) {

                refreshMonitorImage(cropped = true)

            }

        }

        // 切换到 Aide 时检查 MiMoCode 状态

        if (target == Target.AIDELINK) {

            checkMimoStatus()

        }

        // 切换到 OC Web 时加载服务状态

        if (target.key == Target.OPENCODE_WEB.key) {

            loadOcWebStatus()

        }

        // Codex 额度：仅在选中 Codex 时轮询；切到其他 IDE 时停止并清空，避免残留显示。
        if (target == Target.CODEX) {
            startCodexQuotaPolling()
        } else {
            stopCodexQuotaPolling()
            _state.value = _state.value.copy(codexQuota = null)
        }

        viewModelScope.launch(Dispatchers.IO) {

            loadProject()

            withContext(Dispatchers.Main) {

                loadTasks()

            }

        }

    }



    fun checkMimoStatus() {

        viewModelScope.launch(Dispatchers.IO) {

            runCatching { bridgeApi.fetchMimoStatus() }

                .onSuccess { resp ->

                    _state.value = _state.value.copy(mimoRunning = resp?.running == true)

                }

                .onFailure {

                    _state.value = _state.value.copy(mimoRunning = false)

                }

        }

    }



    fun toggleMimo() {

        val currentlyRunning = _state.value.mimoRunning

        _state.value = _state.value.copy(mimoLoading = true)

        viewModelScope.launch(Dispatchers.IO) {

            val success = if (currentlyRunning) {

                bridgeApi.stopMimo()

            } else {

                bridgeApi.startMimo()

            }

            if (success) {

                // 等待一下让进程启动/停止

                delay(if (currentlyRunning) 1000L else 3000L)

                checkMimoStatus()

            }

            _state.value = _state.value.copy(mimoLoading = false)

        }

    }



    fun loadOcWebStatus() {

        viewModelScope.launch(Dispatchers.IO) {

            _state.value = _state.value.copy(ocWebLoading = true)

            runCatching { bridgeApi.getOcWebStatus() }

                .onSuccess { s ->

                    _state.value = _state.value.copy(

                        ocWebRunning = s.running,

                        ocWebPort = s.port,

                        ocWebLoading = false,

                    )

                    if (s.running) loadOcWebLatestReply()

                }

                .onFailure {

                    _state.value = _state.value.copy(ocWebRunning = false, ocWebLoading = false)

                }

        }

    }



    // ─── Codex 额度 ────────────────────────────────────────────

    private var _codexQuotaPollingJob: kotlinx.coroutines.Job? = null

    /** 拉取一次 Codex 额度。force=true 时绕过服务端缓存。 */
    fun loadCodexQuota(force: Boolean = false) {

        viewModelScope.launch(Dispatchers.IO) {

            _state.value = _state.value.copy(codexQuotaLoading = true)

            runCatching { bridgeApi.fetchCodexQuota(force) }

                .onSuccess { resp ->

                    _state.value = _state.value.copy(

                        codexQuota = resp.quota,

                        codexQuotaLoading = false,

                    )

                }

                .onFailure {

                    _state.value = _state.value.copy(codexQuotaLoading = false)

                }

        }

    }

    /** 在 ChatScreen 期间按 5 分钟轮询 Codex 额度。仅在选中 Codex 时生效。 */
    fun startCodexQuotaPolling() {

        // 仅当当前选中的 IDE 是 Codex 时才轮询，其他 IDE 不发请求。
        if (_state.value.target != Target.CODEX) return

        _codexQuotaPollingJob?.cancel()

        _codexQuotaPollingJob = viewModelScope.launch(Dispatchers.IO) {

            loadCodexQuota(force = false)

            while (true) {

                kotlinx.coroutines.delay(5 * 60 * 1000L)

                loadCodexQuota(force = false)

            }

        }

    }

    fun stopCodexQuotaPolling() {

        _codexQuotaPollingJob?.cancel()

        _codexQuotaPollingJob = null

    }



    private var _ocWebReplyPollingJob: kotlinx.coroutines.Job? = null



    fun loadOcWebLatestReply() {

        _ocWebReplyPollingJob?.cancel()

        _ocWebReplyPollingJob = viewModelScope.launch(Dispatchers.IO) {

            repeat(30) {

                delay(2000L)

                if (_state.value.target.key != Target.OPENCODE_WEB.key) return@launch

                runCatching { bridgeApi.getOcWebLatestReply() }

                    .onSuccess { r ->

                        if (r.ok && r.reply != null && r.reply.text.isNotEmpty()) {

                            _state.value = _state.value.copy(

                                ocWebLatestReply = r.reply.text,

                                ocWebSessionTitle = r.reply.session_title,

                            )

                            return@launch

                        }

                    }

            }

        }

    }



    fun toggleOcWeb() {

        val running = _state.value.ocWebRunning

        _state.value = _state.value.copy(ocWebLoading = true, ocWebStatusMessage = null)

        viewModelScope.launch(Dispatchers.IO) {

            val result = if (running) bridgeApi.stopOcWeb() else bridgeApi.startOcWeb()

            if (result.ok) {

                delay(if (running) 1000L else 3000L)

                loadOcWebStatus()

                _state.value = _state.value.copy(ocWebStatusMessage = result.message)

            } else {

                _state.value = _state.value.copy(

                    ocWebLoading = false,

                    ocWebStatusMessage = result.error ?: "操作失败",

                )

            }

        }

    }



    fun send(isTaskListMode: Boolean = false) {

        val text = _state.value.input.trim()

        if (text.isEmpty() || _state.value.sending) return

        _state.value.editingTaskId?.let {
            saveTaskEdit()
            return
        }

        _state.value.activeTaskId?.let { taskId ->
            sendTaskThreadMessage(taskId, text)
            return
        }

        // 立即将用户消息加入本地列表，不等服务端 reload
        val nowStr = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())
        val userMsg = cc.aidelink.app.domain.model.bridge.ChatMessage(
            sender = "user",
            text = text,
            time = nowStr,
            target = _state.value.target.key,
        )
        _state.value = _state.value.copy(
            sending = true,
            input = "",
            isPromptMode = false,
            messages = _state.value.messages + userMsg,
        )



        if (isTaskListMode) {

            createTask(text = text, targetIde = _state.value.target.key)

            return

        }



        viewModelScope.launch(Dispatchers.IO) {

            // Aide 对话走流式路径
            if (_state.value.target == AideLinkChatViewModel.Target.AIDELINK) {
                var fullReply = ""
                var thinkingText = ""
                val agentTime = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())
                try {
                    bridgeApi.sendStream(text = text, target = _state.value.target.key).collect { chunk ->
                        val type = chunk["type"] as? String ?: return@collect
                        when (type) {
                            "delta" -> {
                                fullReply += chunk["content"] as? String ?: ""
                                val agentMsg = cc.aidelink.app.domain.model.bridge.ChatMessage(
                                    sender = "agent",
                                    text = fullReply,
                                    time = agentTime,
                                    target = "aide",
                                )
                                val msgs = _state.value.messages.toMutableList()
                                val lastAgentIdx = msgs.indexOfLast { it.sender == "agent" && it.target == "aide" && it.time == agentTime }
                                if (lastAgentIdx >= 0) msgs[lastAgentIdx] = agentMsg else msgs.add(agentMsg)
                                _state.value = _state.value.copy(messages = msgs)
                            }
                            "thinking" -> {
                                thinkingText += chunk["content"] as? String ?: ""
                                val thinkMsg = cc.aidelink.app.domain.model.bridge.ChatMessage(
                                    sender = "agent",
                                    text = thinkingText,
                                    time = agentTime,
                                    target = "aide_thinking",
                                )
                                val msgs = _state.value.messages.toMutableList()
                                val thinkIdx = msgs.indexOfLast { it.target == "aide_thinking" }
                                if (thinkIdx >= 0) msgs[thinkIdx] = thinkMsg else msgs.add(thinkMsg)
                                _state.value = _state.value.copy(messages = msgs)
                            }
                            "done" -> {
                                fullReply = chunk["content"] as? String ?: fullReply
                                val msgs = _state.value.messages.filter { it.target != "aide_thinking" }.toMutableList()
                                val lastAgentIdx = msgs.indexOfLast { it.sender == "agent" && it.target == "aide" }
                                if (lastAgentIdx >= 0) {
                                    msgs[lastAgentIdx] = msgs[lastAgentIdx].copy(text = fullReply)
                                }
                                _state.value = _state.value.copy(messages = msgs, sending = false)
                            }
                            "error" -> {
                                _state.value = _state.value.copy(
                                    sending = false,
                                    errorMessage = chunk["error"] as? String ?: "未知错误",
                                )
                            }
                        }
                    }
                    if (_state.value.sending) {
                        _state.value = _state.value.copy(sending = false)
                        // 流式完成后立即保存到本地缓存
                        cc.aidelink.app.data.repository.OfflineTaskCache.saveChatHistory(appContext, _state.value.messages)
                        if (_state.value.monitorActive) wakeMonitor()
                        reload()
                    }
                } catch (e: Exception) {
                    _state.value = _state.value.copy(sending = false, errorMessage = e.message)
                    // 出错时也保存当前消息到缓存
                    cc.aidelink.app.data.repository.OfflineTaskCache.saveChatHistory(appContext, _state.value.messages)
                }
                return@launch
            }

            // 其他 target 走原有轮询逻辑
            val pollJob = viewModelScope.launch(Dispatchers.IO) {
                while (_state.value.sending) {
                    delay(2000L)
                    if (!_state.value.sending) break
                    runCatching { bridgeApi.fetchHistory(limit = 100) }
                        .onSuccess { msgs ->
                            _state.value = _state.value.copy(messages = msgs)
                            if (msgs.isNotEmpty()) {
                                cc.aidelink.app.data.repository.OfflineTaskCache.saveChatHistory(appContext, msgs)
                            }
                        }
                }
            }

            val response = runCatching { bridgeApi.send(text = text, target = _state.value.target.key) }.getOrElse { e ->
                pollJob.cancel()
                _state.value = _state.value.copy(
                    sending = false,
                    errorMessage = e.message,
                )
                return@launch
            }

            pollJob.cancel()
            _state.value = _state.value.copy(sending = false)

            if (response.ok) {
                if (_state.value.monitorActive) wakeMonitor()
                reload()
            } else {
                _state.value = _state.value.copy(errorMessage = response.raw.ifBlank { "发送失败" })
            }

        }

    }



    fun sendDirect(text: String, isTaskListMode: Boolean = false) {

        if (text.isEmpty() || _state.value.sending) return

        _state.value.activeTaskId?.let { taskId ->
            sendTaskThreadMessage(taskId, text)
            return
        }

        // 立即将用户消息加入本地列表
        val nowStr = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())
        val userMsg = cc.aidelink.app.domain.model.bridge.ChatMessage(
            sender = "user",
            text = text,
            time = nowStr,
            target = _state.value.target.key,
        )
        _state.value = _state.value.copy(sending = true, isPromptMode = false, messages = _state.value.messages + userMsg)



        if (isTaskListMode) {

            createTask(text = text, targetIde = _state.value.target.key)

            return

        }



        viewModelScope.launch(Dispatchers.IO) {

            // Aide 对话走流式路径
            if (_state.value.target == AideLinkChatViewModel.Target.AIDELINK) {
                var fullReply = ""
                var thinkingText = ""
                val agentTime = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())
                try {
                    bridgeApi.sendStream(text = text, target = _state.value.target.key).collect { chunk ->
                        val type = chunk["type"] as? String ?: return@collect
                        when (type) {
                            "delta" -> {
                                fullReply += chunk["content"] as? String ?: ""
                                val agentMsg = cc.aidelink.app.domain.model.bridge.ChatMessage(
                                    sender = "agent",
                                    text = fullReply,
                                    time = agentTime,
                                    target = "aide",
                                )
                                val msgs = _state.value.messages.toMutableList()
                                val lastAgentIdx = msgs.indexOfLast { it.sender == "agent" && it.target == "aide" && it.time == agentTime }
                                if (lastAgentIdx >= 0) msgs[lastAgentIdx] = agentMsg else msgs.add(agentMsg)
                                _state.value = _state.value.copy(messages = msgs)
                            }
                            "thinking" -> {
                                thinkingText += chunk["content"] as? String ?: ""
                                val thinkMsg = cc.aidelink.app.domain.model.bridge.ChatMessage(
                                    sender = "agent",
                                    text = thinkingText,
                                    time = agentTime,
                                    target = "aide_thinking",
                                )
                                val msgs = _state.value.messages.toMutableList()
                                val thinkIdx = msgs.indexOfLast { it.target == "aide_thinking" }
                                if (thinkIdx >= 0) msgs[thinkIdx] = thinkMsg else msgs.add(thinkMsg)
                                _state.value = _state.value.copy(messages = msgs)
                            }
                            "done" -> {
                                fullReply = chunk["content"] as? String ?: fullReply
                                val msgs = _state.value.messages.filter { it.target != "aide_thinking" }.toMutableList()
                                val lastAgentIdx = msgs.indexOfLast { it.sender == "agent" && it.target == "aide" }
                                if (lastAgentIdx >= 0) {
                                    msgs[lastAgentIdx] = msgs[lastAgentIdx].copy(text = fullReply)
                                }
                                _state.value = _state.value.copy(messages = msgs, sending = false)
                            }
                            "error" -> {
                                _state.value = _state.value.copy(
                                    sending = false,
                                    errorMessage = chunk["error"] as? String ?: "未知错误",
                                )
                            }
                        }
                    }
                    if (_state.value.sending) {
                        _state.value = _state.value.copy(sending = false)
                        // 流式完成后立即保存到本地缓存
                        cc.aidelink.app.data.repository.OfflineTaskCache.saveChatHistory(appContext, _state.value.messages)
                        if (_state.value.monitorActive) wakeMonitor()
                        reload()
                    }
                } catch (e: Exception) {
                    _state.value = _state.value.copy(sending = false, errorMessage = e.message)
                    // 出错时也保存当前消息到缓存
                    cc.aidelink.app.data.repository.OfflineTaskCache.saveChatHistory(appContext, _state.value.messages)
                }
                return@launch
            }

            // 其他 target 走原有轮询逻辑
            val pollJob = viewModelScope.launch(Dispatchers.IO) {
                while (_state.value.sending) {
                    delay(2000L)
                    if (!_state.value.sending) break
                    runCatching { bridgeApi.fetchHistory(limit = 100) }
                        .onSuccess { msgs ->
                            _state.value = _state.value.copy(messages = msgs)
                            if (msgs.isNotEmpty()) {
                                cc.aidelink.app.data.repository.OfflineTaskCache.saveChatHistory(appContext, msgs)
                            }
                        }
                }
            }

            val response = runCatching { bridgeApi.send(text = text, target = _state.value.target.key) }.getOrElse { e ->
                pollJob.cancel()
                _state.value = _state.value.copy(
                    sending = false,
                    errorMessage = e.message,
                )
                return@launch
            }

            pollJob.cancel()
            _state.value = _state.value.copy(sending = false)

            if (response.ok) {
                if (_state.value.monitorActive) wakeMonitor()
                reload()
            } else {
                _state.value = _state.value.copy(errorMessage = response.raw.ifBlank { "发送失败" })
            }

        }

    }



    fun setMonitorScreenVisible(visible: Boolean) {

        _state.value = _state.value.copy(monitorScreenVisible = visible)

        if (visible) {
            if (_state.value.monitorActive) {
                wakeMonitor()
            }
        } else {
            stopMonitorPolling()
        }

    }



    fun setMonitorActive(active: Boolean) {

        val target = _state.value.target

        _state.value = _state.value.copy(

            monitorActive = active,

            monitorByTarget = _state.value.monitorByTarget + (target to active),

        )

        viewModelScope.launch(Dispatchers.IO) {

            runCatching { settingsRepository.setMonitorEnabled(target.key, active) }

        }

        if (active) {

            wakeMonitor()

        } else {

            _state.value = _state.value.copy(monitorSleeping = false)

            stopMonitorPolling()

        }

    }



    /** 切换指定 target 的监控开关（不一定是当前 target）。 */

    fun setMonitorEnabledForTarget(target: Target, enabled: Boolean) {

        _state.value = _state.value.copy(

            monitorByTarget = _state.value.monitorByTarget + (target to enabled),

        )

        viewModelScope.launch(Dispatchers.IO) {

            runCatching { settingsRepository.setMonitorEnabled(target.key, enabled) }

        }

        // 如果是当前 target，同时更新 active 状态并启停 polling

        if (target == _state.value.target) {

            _state.value = _state.value.copy(monitorActive = enabled)

            if (enabled) wakeMonitor() else stopMonitorPolling()

        }

    }



    private fun startMonitorPolling() {

        monitorJob?.cancel()

        monitorJob = viewModelScope.launch(Dispatchers.IO) {

            while (true) {

                val s = _state.value

                if (s.monitorScreenVisible && !s.showLiveMonitorDialog && !s.monitorSleeping && !s.monitorPollingPaused) {

                    refreshMonitorImage(cropped = s.monitorCropMode)

                }

                delay(s.monitorIntervalMs)

            }

        }

    }



    private fun stopMonitorPolling() {

        monitorJob?.cancel()

        monitorJob = null

    }



    fun pauseMonitorPolling() {

        _state.value = _state.value.copy(monitorPollingPaused = true)

    }



    fun resumeMonitorPolling() {

        _state.value = _state.value.copy(monitorPollingPaused = false)

    }



    fun wakeMonitor() {

        lastScreenshotHash = 0L

        consecutiveNoChangeCount = 0

        lastChangeTimeMs = System.currentTimeMillis()

        _state.value = _state.value.copy(monitorSleeping = false)

        if (_state.value.monitorActive) {

            startMonitorPolling()

        }

    }



    private fun trackScreenshotChange(bytes: ByteArray) {

        val hash = centerRegionHash(bytes)

        val now = System.currentTimeMillis()

        if (hash != 0L && hash == lastScreenshotHash) {

            consecutiveNoChangeCount++

            if (consecutiveNoChangeCount >= NO_CHANGE_THRESHOLD &&

                now - lastChangeTimeMs > _state.value.monitorNoChangeTimeoutMs

            ) {

                _state.value = _state.value.copy(monitorSleeping = true)

                stopMonitorPolling()

            }

        } else {

            consecutiveNoChangeCount = 0

            lastChangeTimeMs = now

            lastScreenshotHash = hash

        }

    }



    fun adjustMonitorInterval(deltaMs: Long) {

        val current = _state.value.monitorIntervalMs

        val newInterval = (current + deltaMs).coerceIn(500L, 600_000L)

        _state.value = _state.value.copy(monitorIntervalMs = newInterval)

        viewModelScope.launch(Dispatchers.IO) {

            settingsRepository.setMonitorIntervalMs(newInterval)

        }

    }



    fun setMonitorInterval(intervalMs: Long) {

        val newInterval = intervalMs.coerceIn(500L, 600_000L)

        _state.value = _state.value.copy(monitorIntervalMs = newInterval)

        viewModelScope.launch(Dispatchers.IO) {

            settingsRepository.setMonitorIntervalMs(newInterval)

        }

    }



    fun setMonitorHeightDp(heightDp: Int) {

        _state.value = _state.value.copy(monitorHeightDp = heightDp)

        val target = _state.value.target.key

        viewModelScope.launch(Dispatchers.IO) {

            settingsRepository.setMonitorHeightDp(target, heightDp)

        }

    }



    fun setMonitorNoChangeTimeoutMs(timeoutMs: Long) {

        val clamped = timeoutMs.coerceIn(60_000L, 3_600_000L)

        _state.value = _state.value.copy(monitorNoChangeTimeoutMs = clamped)

        viewModelScope.launch(Dispatchers.IO) {

            settingsRepository.setMonitorNoChangeTimeoutMs(clamped)

        }

    }



    fun setMonitorCropMode(cropped: Boolean, onReady: () -> Unit = {}) {

        viewModelScope.launch(Dispatchers.IO) {

            val target = _state.value.target.key

            if (target in setOf(Target.TRAE.key, Target.ANTIGRAVITY.key)) {

                bridgeApi.focusTargetInput(target)

                delay(250)

            }

            _state.value = _state.value.copy(monitorCropMode = cropped)

            refreshMonitorImage(cropped)

            onReady()

        }

    }



    fun triggerIntelligentScreenshot() {

        viewModelScope.launch(Dispatchers.IO) {

            val target = _state.value.target.key

            if (target in setOf(Target.TRAE.key, Target.ANTIGRAVITY.key)) {

                bridgeApi.focusTargetInput(target)

                delay(250)

            }

            refreshMonitorImage()

        }

    }



    fun focusTargetWindow() {

        viewModelScope.launch(Dispatchers.IO) {

            val target = _state.value.target.key

            if (target in setOf(Target.TRAE.key, Target.ANTIGRAVITY.key, Target.MIMOCODE.key, Target.OPENCODE.key, Target.CODEX.key)) {

                bridgeApi.focusTargetWindow(target)

                delay(250)

            }

            refreshMonitorImage()

        }

    }



    private suspend fun refreshMonitorImage(cropped: Boolean = _state.value.monitorCropMode) {

        runCatching {

            val currentTarget = _state.value.target.key
            val cropMonitor = resolveMonitorForCrop(currentTarget)

            if (cropped) {

                // 截已裁剪的窗口（服务端按 crop配置裁剪四边）

                bridgeApi.screenshotCropByConfig(currentTarget, cropMonitor)

            } else {

                // 截目标窗口本身（不裁剪）。这里不能传 monitor，否则后端会返回整块显示器，导致边距基准漂移。

                bridgeApi.screenshotFull(target = currentTarget)

            }

        }.onSuccess { bytes ->

            // 截图完成后再次检查标志，如果已进入全屏则不更新，避免画面跳动

            if (!_state.value.showLiveMonitorDialog && bytes != null) {

                trackScreenshotChange(bytes)

                runCatching {

                    val bitmap = decodeScaledBitmap(bytes)

                    if (bitmap != null && bitmap.width in 1..2048 && bitmap.height in 1..2048) {

                        _state.value = _state.value.copy(

                            monitorImage = bitmap.asImageBitmap()

                        )

                    }

                }

            }

        }

    }

    private suspend fun resolveMonitorForCrop(targetKey: String): String? {
        val snapshot = _state.value
        if (snapshot.manualMonitorOverride) return snapshot.selectedMonitor

        val windowInfo = runCatching { bridgeApi.fetchTargetWindowInfo(targetKey) }.getOrNull() ?: return null
        val monitorsList = if (snapshot.monitors.isNotEmpty()) {
            snapshot.monitors
        } else {
            runCatching { bridgeApi.fetchMonitors() }.getOrDefault(emptyList())
        }
        val centerX = (windowInfo.left + windowInfo.right) / 2
        val centerY = (windowInfo.top + windowInfo.bottom) / 2
        return monitorsList.firstOrNull { mon ->
            centerX >= mon.left && centerX < mon.right &&
                centerY >= mon.top && centerY < mon.bottom
        }?.name
    }



    private suspend fun refreshDialogUncroppedImage(source: DialogCropSource? = null) {

        runCatching {

            val currentTarget = _state.value.target.key
            val selectedMonitor = _state.value.selectedMonitor.takeIf { _state.value.manualMonitorOverride }

            if (source == DialogCropSource.WINDOW && currentTarget in setOf(Target.TRAE.key, Target.ANTIGRAVITY.key, Target.MIMOCODE.key, Target.OPENCODE.key, Target.CODEX.key)) {

                bridgeApi.screenshotFull(target = currentTarget, monitor = selectedMonitor)

            } else {

                bridgeApi.screenshotFull(target = null, monitor = selectedMonitor)

            }

        }.onSuccess { bytes ->

            if (bytes != null) {

                runCatching {

                    val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }

                    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)

                    val origW = opts.outWidth

                    val origH = opts.outHeight

                    val bitmap = decodeScaledBitmap(bytes)

                    if (bitmap != null) {

                        _state.value = _state.value.copy(

                            dialogUncroppedImage = bitmap.asImageBitmap(),

                            originalImageWidth = origW,

                            originalImageHeight = origH

                        )

                    }

                }

            }

        }

    }



    fun setDialogCropSource(source: DialogCropSource?) {

        _state.value = _state.value.copy(dialogCropSource = source)

        if (source != null) {

            viewModelScope.launch(Dispatchers.IO) {

                refreshDialogUncroppedImage(source)

            }

        } else {

            _state.value = _state.value.copy(dialogUncroppedImage = null)

        }

    }



    /** Consume a calibration request created from Settings when this screen resumes. */
    fun consumePendingCalibrationRequest() {
        val prefs = appContext.getSharedPreferences("aidelink_navigation", android.content.Context.MODE_PRIVATE)
        val pendingIde = prefs.getString("pending_calibration_ide", null)
        if (pendingIde.isNullOrBlank()) return
        prefs.edit().remove("pending_calibration_ide").apply()
        _state.value = _state.value.copy(target = Target.fromKey(pendingIde))
        setShowLiveMonitorDialog(true)
    }

    fun setShowLiveMonitorDialog(show: Boolean) {

        if (show) {

            // 先同步设置标志，让轮询立即暂停，避免与轮询刷新竞态导致画面跳动

            _state.value = _state.value.copy(

                showLiveMonitorDialog = true,

                monitors = emptyList(),

                selectedMonitor = null,

                manualMonitorOverride = false,

                windowFound = true

            )

            viewModelScope.launch(Dispatchers.IO) {

                try {

                    val targetKey = _state.value.target.key

                    // 进入边距调整前，先将窗口最大化，确保校准基线为最大化状态
                    runCatching { bridgeApi.maximizeTargetWindow(targetKey) }

                    // 同时拉取多显示器列表

                    val monitorsList = runCatching { bridgeApi.fetchMonitors() }.getOrDefault(emptyList())

                    val windowInfo = runCatching { bridgeApi.fetchTargetWindowInfo(targetKey) }.getOrNull()

                    val windowMonitor = monitorContainingWindow(windowInfo, monitorsList)

                    val activeMonitor = _state.value.selectedMonitor ?: windowMonitor

                    val activeConfig = bridgeApi.fetchActiveCropConfig(targetKey, activeMonitor)



                    // 获取显示器截图，如果找不到窗口所在的显示器，则可以传 monitor，或者以全屏作为兜底

                    val pair = bridgeApi.screenshotFullWithStatus(
                        target = targetKey,
                        monitor = activeMonitor,
                        fullMonitor = false
                    )

                    val bytes = pair.first

                    val winFound = pair.second

                    

                    if (bytes != null) {

                        val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }

                        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)

                        val origW = opts.outWidth

                        val origH = opts.outHeight

                        val bitmap = decodeScaledBitmap(bytes)

                        if (bitmap != null && bitmap.width in 1..2048 && bitmap.height in 1..2048) {

                            // 一次性更新所有状态

                            _state.value = _state.value.copy(

                                cropLeft = activeConfig?.left ?: 0,

                                cropRight = activeConfig?.right ?: 0,

                                cropTop = activeConfig?.top ?: 0,

                                cropBottom = activeConfig?.bottom ?: 0,

                                calibWidth = activeConfig?.calib_width ?: 0,

                                calibHeight = activeConfig?.calib_height ?: 0,

                                dialogPosition = activeConfig?.dialog_position ?: "center",

                                focusInputEnabled = activeConfig?.focus_input_enabled ?: false,

                                inputPoint = activeConfig?.input_region,

                                dialogUncroppedImage = bitmap.asImageBitmap(),

                                originalImageWidth = origW,

                                originalImageHeight = origH,

                                monitors = monitorsList,

                                selectedMonitor = activeMonitor,

                                windowFound = winFound

                            )

                        }

                    }

                } catch (e: OutOfMemoryError) {

                    _state.value = _state.value.copy(

                        showLiveMonitorDialog = false,

                        errorMessage = "截图过大，内存不足"

                    )

                } catch (e: Exception) {

                    _state.value = _state.value.copy(

                        showLiveMonitorDialog = false,

                        errorMessage = "打开监控失败: ${e.message}"

                    )

                }

            }

        } else {

            _state.value = _state.value.copy(

                showLiveMonitorDialog = false,

                dialogCropSource = null,

                dialogUncroppedImage = null,

                monitors = emptyList(),

                selectedMonitor = null,

                manualMonitorOverride = false

            )

        }

    }



    fun switchDialogMonitor(monitorName: String) {

        _state.value = _state.value.copy(selectedMonitor = monitorName, manualMonitorOverride = true)

        viewModelScope.launch(Dispatchers.IO) {

            val targetKey = _state.value.target.key

            // 显示器切换不仅换截图来源，也把 IDE 窗口移动并最大化到目标显示器。
            // 若绑定尚未落盘，先尝试将当前前台 IDE 绑定，避免移动接口因无 hwnd 直接返回。
            runCatching { bridgeApi.autoBindIdeWindow(targetKey) }
            val moved = runCatching { bridgeApi.moveAndMaximizeForCalibration(targetKey, monitorName) }.getOrDefault(false)
            if (!moved) {
                _state.value = _state.value.copy(toastMessage = "IDE 未切换到目标显示器，请先绑定窗口")
            }

            val bytes = bridgeApi.screenshotFull(target = targetKey, monitor = monitorName)

            if (bytes != null) {

                val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }

                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)

                val origW = opts.outWidth

                val origH = opts.outHeight

                val bitmap = decodeScaledBitmap(bytes)

                if (bitmap != null && bitmap.width in 1..2048 && bitmap.height in 1..2048) {

                    _state.value = _state.value.copy(

                        dialogUncroppedImage = bitmap.asImageBitmap(),

                        originalImageWidth = origW,

                        originalImageHeight = origH

                    )

                }

            }

            val cfg = bridgeApi.fetchActiveCropConfig(targetKey, monitorName)

            if (cfg != null) {

                _state.value = _state.value.copy(

                    cropLeft = cfg.left,

                    cropRight = cfg.right,

                    cropTop = cfg.top,

                    cropBottom = cfg.bottom,

                    calibWidth = cfg.calib_width,

                    calibHeight = cfg.calib_height,

                    dialogPosition = cfg.dialog_position,

                    focusInputEnabled = cfg.focus_input_enabled,

                    inputPoint = cfg.input_region,

                )

            }

        }

    }



    fun onResumeRefresh() {

        loadSelectedIdeList()

        loadIdeRunningStatus()

        loadTasks()

        viewModelScope.launch(Dispatchers.IO) {

            val snapshot = _state.value

            if (snapshot.monitorActive && !snapshot.showLiveMonitorDialog) {

                refreshMonitorImage(cropped = snapshot.monitorCropMode)

            } else if (snapshot.showLiveMonitorDialog && snapshot.dialogCropSource != null) {

                refreshDialogUncroppedImage(snapshot.dialogCropSource)

            }

        }

    }



    fun setCropValue(side: String, value: Int) {

        val safeValue = value.coerceIn(0, 3000)

        _state.value = when (side.lowercase()) {

            "left" -> _state.value.copy(cropLeft = safeValue)

            "right" -> _state.value.copy(cropRight = safeValue)

            "top" -> _state.value.copy(cropTop = safeValue)

            "bottom" -> _state.value.copy(cropBottom = safeValue)

            else -> _state.value

        }

    }



    fun setDialogPosition(pos: String) {

        if (pos !in setOf("left", "center", "right")) return

        _state.value = _state.value.copy(dialogPosition = pos)

        viewModelScope.launch(Dispatchers.IO) {

            val targetKey = _state.value.target.key

            val pair = bridgeApi.screenshotFullWithStatus(
                target = targetKey,
                monitor = _state.value.selectedMonitor.takeIf { _state.value.manualMonitorOverride },
                fullMonitor = false
            )

            val bytes = pair.first

            if (bytes != null) {

                val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }

                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)

                val origW = opts.outWidth

                val origH = opts.outHeight

                val bitmap = decodeScaledBitmap(bytes)

                if (bitmap != null) {

                    _state.value = _state.value.copy(

                        dialogUncroppedImage = bitmap.asImageBitmap(),

                        originalImageWidth = origW,

                        originalImageHeight = origH

                    )

                }

            }

        }

    }



    /**

     * 重置所有裁剪边距（清零左右上下的空白，让截图拉满

     */

    fun resetAllCrops() {

        _state.value = _state.value.copy(

            cropLeft = 0,

            cropRight = 0,

            cropTop = 0,

            cropBottom = 0

        )

        viewModelScope.launch(Dispatchers.IO) {

            applyCropAndRefresh(0, 0, 0, 0)

        }

    }



    fun clearCropsOnly() {

        _state.value = _state.value.copy(

            cropLeft = 0,

            cropRight = 0,

            cropTop = 0,

            cropBottom = 0

        )

    }



    fun expandToFitWidth() {

        _state.value = _state.value.copy(

            cropLeft = 0,

            cropRight = 0,

            cropTop = 0,

            cropBottom = 0

        )

        viewModelScope.launch(Dispatchers.IO) {

            saveCropConfig()

        }

    }



    /**

     * 根据图片宽高比（像素）和容器宽度（dp）调整面板高度（dp）

     */

    fun adjustHeightByImageRatioDp(imageWidthPx: Int, imageHeightPx: Int, containerWidthDp: Dp) {

        if (imageWidthPx <= 0 || imageHeightPx <= 0) return

        val ratio = imageHeightPx.toFloat() / imageWidthPx.toFloat()

        val newHeightDp = (containerWidthDp.value * ratio).toInt().coerceIn(150, 700)

        setMonitorHeightDp(newHeightDp)

    }



    fun saveCropConfig() {

        viewModelScope.launch(Dispatchers.IO) {

            runCatching {

                val s = _state.value
                // crops are in display-image space (from get_scaled_crop_config),
                // so calib must match that space so the server scales up correctly
                val calibX = s.originalImageWidth.takeIf { it > 0 } ?: s.calibWidth
                val calibY = s.originalImageHeight.takeIf { it > 0 } ?: s.calibHeight
                bridgeApi.saveCropConfig(

                    target = s.target.key,

                    left = s.cropLeft,

                    right = s.cropRight,

                    top = s.cropTop,

                    bottom = s.cropBottom,

                    monitor = s.selectedMonitor,

                    dialogPosition = s.dialogPosition,
                    calibWidth = calibX,
                    calibHeight = calibY,
                    focusInputEnabled = s.focusInputEnabled,
                    inputPoint = s.inputPoint,

                )

            }

        }

    }



    /**

     * 串行：先把裁剪配置保存到服务器，**等保存完成后再** 用新裁剪刷新截图

     * 避免 saveCropConfig 和 refreshMonitorImage 并发跑导致截图用旧 crops

     */

    fun applyCropAndRefresh(left: Int, right: Int, top: Int, bottom: Int) {

        viewModelScope.launch(Dispatchers.IO) {

            val safeL = left.coerceIn(0, 3000)

            val safeR = right.coerceIn(0, 3000)

            val safeT = top.coerceIn(0, 3000)

            val safeB = bottom.coerceIn(0, 3000)

            val target = _state.value.target.key
            val selectedAtEdit = _state.value.selectedMonitor
            if (!_state.value.manualMonitorOverride && selectedAtEdit != null) {
                val freshMonitors = runCatching { bridgeApi.fetchMonitors() }.getOrDefault(emptyList())
                val freshWindow = runCatching { bridgeApi.fetchTargetWindowInfo(target) }.getOrNull()
                val currentWindowMonitor = monitorContainingWindow(freshWindow, freshMonitors)
                if (currentWindowMonitor == null) {
                    _state.value = _state.value.copy(
                        toastMessage = "未能确认目标窗口所在显示器，已取消应用裁剪，请重试",
                    )
                    return@launch
                }
                if (currentWindowMonitor != selectedAtEdit) {
                    _state.value = _state.value.copy(
                        monitors = freshMonitors,
                        toastMessage = "目标窗口已从 $selectedAtEdit 移到 $currentWindowMonitor，未应用旧显示器裁剪",
                    )
                    switchDialogMonitor(currentWindowMonitor)
                    _state.value = _state.value.copy(manualMonitorOverride = false)
                    return@launch
                }
            }

            val mon = _state.value.selectedMonitor

            _state.value = _state.value.copy(

                cropLeft = safeL, cropRight = safeR, cropTop = safeT, cropBottom = safeB,

                monitorCropMode = true,

                dialogCropSource = null,

                dialogUncroppedImage = null

            )

            val pos = _state.value.dialogPosition
            val sCrop = _state.value

            val cw = sCrop.originalImageWidth.takeIf { it > 0 } ?: sCrop.calibWidth
            val ch = sCrop.originalImageHeight.takeIf { it > 0 } ?: sCrop.calibHeight

            runCatching {

                bridgeApi.saveCropConfig(target, safeL, safeR, safeT, safeB, mon,

                    dialogPosition = pos, calibWidth = cw, calibHeight = ch,
                    focusInputEnabled = sCrop.focusInputEnabled,
                    inputPoint = sCrop.inputPoint)

            }

            refreshMonitorImage(cropped = true)

            setShowLiveMonitorDialog(false)

        }

    }



    fun uploadImage(filePath: String) {

        viewModelScope.launch(Dispatchers.IO) {

            _state.value = _state.value.copy(uploading = true, uploadResult = null)

            runCatching {

                val filename = java.io.File(filePath).name

                bridgeApi.uploadImage(filePath, filename)

            }.onSuccess { resp ->
                if (resp.ok && !resp.path.isNullOrBlank()) {
                    val attachmentLine = "附件：${resp.path}"
                    val currentInput = _state.value.input.trimEnd()
                    _state.value = _state.value.copy(
                        uploading = false,
                        input = if (currentInput.isBlank()) attachmentLine else "$currentInput\n$attachmentLine",
                        uploadResult = "附件已上传",
                        toastMessage = "附件已上传，请补充说明后发送",
                    )
                } else {
                    _state.value = _state.value.copy(
                        uploading = false,
                        uploadResult = "上传失败",
                        errorMessage = resp.raw.ifBlank { "附件上传失败" },
                    )
                }

            }.onFailure { e ->

                _state.value = _state.value.copy(

                    uploading = false,

                    uploadResult = "上传失败: ${e.message}",

                )

            }

        }

    }



    fun loadClipboard() {

        viewModelScope.launch(Dispatchers.IO) {

            _state.value = _state.value.copy(clipboardLoading = true)

            runCatching { bridgeApi.fetchClipboard() }

                .onSuccess { items ->

                    _state.value = _state.value.copy(clipboardItems = items, clipboardLoading = false)

                }

                .onFailure { e ->

                    _state.value = _state.value.copy(clipboardLoading = false, errorMessage = e.message)

                }

        }

    }



    fun syncClipboardToPc(text: String) {

        viewModelScope.launch(Dispatchers.IO) {

            runCatching { bridgeApi.appendClipboard(text) }

                .onSuccess {

                    loadClipboard()

                }

                .onFailure { e ->

                    _state.value = _state.value.copy(errorMessage = e.message)

                }

        }

    }



    fun clearClipboard() {

        viewModelScope.launch(Dispatchers.IO) {

            runCatching { bridgeApi.clearClipboard() }

                .onSuccess {

                    loadClipboard()

                }

                .onFailure { e ->

                    _state.value = _state.value.copy(errorMessage = e.message)

                }

        }

    }



    fun wakeScreen() {

        viewModelScope.launch(Dispatchers.IO) {

            val result = bridgeApi.wakeScreen()

            if (!result.ok) {

                _state.value = _state.value.copy(

                    errorMessage = "唤醒屏幕失败: ${result.reason ?: "未知错误"}"

                )

                delay(3000)

                _state.value = _state.value.copy(errorMessage = null)

            } else {

                val msg = when {

                    result.skipped && result.reason == "already unlocked" -> "屏幕已经是亮的"

                    result.skipped -> "已跳过（${result.reason ?: ""}）"

                    else -> "已唤醒电脑屏幕"

                }

                _state.value = _state.value.copy(toastMessage = msg)

            }

        }

    }



    fun turnOffMonitor() {

        viewModelScope.launch(Dispatchers.IO) {

            val result = bridgeApi.turnOffMonitor()

            if (!result.ok) {

                _state.value = _state.value.copy(

                    errorMessage = "关闭显示器失败: ${result.reason ?: "未知错误"}"

                )

                delay(3000)

                _state.value = _state.value.copy(errorMessage = null)

            } else {

                _state.value = _state.value.copy(toastMessage = "已关闭电脑显示器，派发任务时会自动唤醒")

            }

        }

    }



    fun loadSelectedIdeList() {

        viewModelScope.launch {

            val saved = settingsRepository.getDesktopIdeList()
            val canonicalSaved = saved.map(Target::canonicalUserKey).distinct()

            val serverKeys = _state.value.desktopIdes.map { it.key }.toSet()

            // 过滤掉服务端不存在的 IDE key（如 trae 已迁移为 trae_cn），保留 oc_web（web 类型不在 desktopIdes 中）

            val filtered = if (serverKeys.isNotEmpty()) {

                canonicalSaved.filter { it in serverKeys || it == Target.OPENCODE_WEB.key }

            } else {

                canonicalSaved

            }

            _state.value = _state.value.copy(selectedIdeList = filtered)

            // 持久化过滤结果，避免下次再加载到无效 key

            if (filtered != saved && filtered.isNotEmpty()) {

                settingsRepository.saveDesktopIdeList(filtered)

            }

        }

    }

    fun loadIdeRunningStatus() {

        viewModelScope.launch(Dispatchers.IO) {

            runCatching { bridgeApi.getIdeProcesses() }

                .onSuccess { processes ->

                    val runningMap = processes.associate { it.key to it.running }

                    _state.value = _state.value.copy(ideRunningMap = runningMap)



                    // 刷新运行状态只更新状态，不抢占用户当前页面的目标 IDE。
                    // 否则从设置返回时会出现 Aide -> ChatGPT -> OpenCode 的连续跳转。
                    _initialRunningAutoSwitchDone = true

                }

        }

    }



    fun startIde(ide: String) {
        val displayName = if (ide == Target.CODEX.key) Target.CODEX.label else ide
        _state.value = _state.value.copy(toastMessage = "正在启动 $displayName…")
        viewModelScope.launch(Dispatchers.IO) {
            val started = runCatching { bridgeApi.startIde(ide) }.getOrDefault(false)
            if (!started) {
                _state.value = _state.value.copy(toastMessage = "$displayName 启动失败，请检查电脑端服务")
                return@launch
            }
            delay(1500)
            loadIdeRunningStatus()
        }
    }



    fun stopIde(ide: String) {
        val displayName = _state.value.desktopIdes.firstOrNull { it.key == ide }?.name ?: ide
        _state.value = _state.value.copy(toastMessage = "正在关闭 $displayName…")
        viewModelScope.launch(Dispatchers.IO) {
            val stopped = runCatching { bridgeApi.stopIde(ide) }.getOrDefault(false)
            _state.value = _state.value.copy(
                toastMessage = if (stopped) "已请求关闭 $displayName" else "$displayName 关闭失败"
            )
            if (stopped) {
                delay(1000)
                loadIdeRunningStatus()
            }
        }
    }

    fun switchIdeProject(ide: String, path: String) {
        val ideName = _state.value.desktopIdes.firstOrNull { it.key == ide }?.name ?: ide
        val projectName = _state.value.projects.firstOrNull { it.path == path }?.name
            ?.ifBlank { path.substringAfterLast('\\') }
            ?: path.substringAfterLast('\\')
        _state.value = _state.value.copy(toastMessage = "正在让 $ideName 打开 $projectName…")
        viewModelScope.launch(Dispatchers.IO) {
            val selected = runCatching { bridgeApi.selectProject(path) }.getOrDefault(false)
            val opened = selected && runCatching { bridgeApi.openIdeProject(ide, path) }.getOrDefault(false)
            if (selected) loadProject()
            _state.value = _state.value.copy(
                toastMessage = if (opened) "$ideName 已请求打开 $projectName"
                else "$ideName 切换项目失败，请检查适配配置"
            )
        }
    }

    fun updateIdeProfile(ide: String) {
        val ideName = _state.value.desktopIdes.firstOrNull { it.key == ide }?.name ?: ide
        _state.value = _state.value.copy(toastMessage = "正在更新 $ideName 适配配置…")
        viewModelScope.launch(Dispatchers.IO) {
            val ok = runCatching { bridgeApi.updateIdeProfile(ide) }.getOrDefault(false)
            if (ok) refreshDesktopIdes()
            _state.value = _state.value.copy(
                toastMessage = if (ok) "$ideName 适配配置已检查更新" else "$ideName 适配配置更新失败"
            )
        }
    }

    fun loadIdeHistory(ide: String) {
        _state.value = _state.value.copy(ideHistoryLoading = true, ideHistorySessions = emptyList())
        viewModelScope.launch(Dispatchers.IO) {
            val sessions = runCatching { bridgeApi.getIdeHistory(ide) }.getOrDefault(emptyList())
            _state.value = _state.value.copy(
                ideHistoryLoading = false,
                ideHistorySessions = sessions,
                toastMessage = if (sessions.isEmpty()) "没有找到可用的历史会话" else null,
            )
        }
    }

    fun openIdeHistory(ide: String, threadId: String) {
        viewModelScope.launch(Dispatchers.IO) {
            val opened = runCatching { bridgeApi.openIdeHistory(ide, threadId) }.getOrDefault(false)
            _state.value = _state.value.copy(
                toastMessage = if (opened) "已请求打开历史会话" else "历史会话打开失败"
            )
        }
    }



    fun setShowDesktopIdeDialog(show: Boolean) {

        _state.value = _state.value.copy(showDesktopIdeDialog = show)

    }

    fun openDesktopIdeDialog() {
        _state.value = _state.value.copy(
            showDesktopIdeDialog = true,
            desktopIdesLoading = true,
        )
        viewModelScope.launch(Dispatchers.IO) {
            var ides = runCatching { bridgeApi.getDesktopIdes() }.getOrDefault(emptyList())
            val targetKey = _state.value.target.key
            val needsDesktopIde = targetKey != Target.AIDELINK.key && targetKey != Target.OPENCODE_WEB.key
            if (needsDesktopIde && ides.none { it.key == targetKey }) {
                ides = runCatching { bridgeApi.scanIdes() }.getOrDefault(emptyList())
            }
            _state.value = _state.value.copy(
                desktopIdes = ides,
                desktopIdesLoading = false,
            )
            Target.setDynamicTargets(
                ides.map { ide -> Target(ide.key, ide.name, ide.icon, ide.color) }
            )
            loadIdeRunningStatus()
        }
    }



    private suspend fun refreshDesktopIdes() {
        runCatching { bridgeApi.getDesktopIdes() }
            .onSuccess { ides ->
                _state.value = _state.value.copy(desktopIdes = ides)
                // 同步更新动态 Target 列表
                val targets = ides.map { ide ->
                    Target(key = ide.key, label = ide.name, icon = ide.icon, colorHex = ide.color)
                }
                Target.setDynamicTargets(targets)
            }
    }

    fun loadDesktopIdes() {
        viewModelScope.launch(Dispatchers.IO) {
            refreshDesktopIdes()
        }
    }



    fun scanDesktopIdes() {
        _state.value = _state.value.copy(desktopIdesLoading = true)
        viewModelScope.launch(Dispatchers.IO) {
            val ides = runCatching { bridgeApi.scanIdes() }.getOrDefault(emptyList())
            _state.value = _state.value.copy(desktopIdes = ides, desktopIdesLoading = false)
            loadIdeRunningStatus()
        }
    }



    fun addDesktopIde(key: String, name: String, path: String, onDone: (Boolean) -> Unit = {}) {

        viewModelScope.launch(Dispatchers.IO) {

            val ok = runCatching { bridgeApi.saveManualIde(DesktopIde(key = key, name = name, path = path)) }

                .getOrDefault(false)

            if (ok) {

                refreshDesktopIdes()

                loadIdeRunningStatus()

            }

            withContext(Dispatchers.Main) { onDone(ok) }

        }

    }



    fun removeDesktopIde(key: String) {

        viewModelScope.launch(Dispatchers.IO) {

            runCatching { bridgeApi.removeManualIde(key) }

                .onSuccess {

                    refreshDesktopIdes()

                    loadIdeRunningStatus()

                }

        }

    }



    fun browseIdePath(onResult: (String?) -> Unit) {

        viewModelScope.launch(Dispatchers.IO) {

            val path = runCatching { bridgeApi.browsePath() }.getOrNull()

            withContext(Dispatchers.Main) { onResult(path) }

        }

    }



    fun loadQuickReplies() {

        viewModelScope.launch(Dispatchers.IO) {

            val replies = settingsRepository.getQuickReplies()

            if (replies.isEmpty()) {

                val defaults = listOf("继续", "安装到手机", "升级版本号并提交git")

                settingsRepository.setQuickReplies(defaults)

                _state.value = _state.value.copy(quickReplies = defaults)

            } else {

                _state.value = _state.value.copy(quickReplies = replies)

            }

        }

    }



    fun addQuickReply(text: String) {

        if (text.isBlank()) return

        viewModelScope.launch(Dispatchers.IO) {

            settingsRepository.addQuickReply(text.trim())

            loadQuickReplies()

        }

    }



    fun removeQuickReply(text: String) {

        viewModelScope.launch(Dispatchers.IO) {

            settingsRepository.removeQuickReply(text)

            loadQuickReplies()

        }

    }



    fun sendQuickReply(text: String) {

        sendDirect(text)

    }



    // ─── 任务管理 ───



    fun loadTasks() {

        viewModelScope.launch(Dispatchers.IO) {

            _state.value = _state.value.copy(tasksLoading = true)

            // 服务端 TaskRuntime 已按当前目标项目选择独立任务文件。
            // 客户端再传可能过期的 project 会把新项目任务全部二次过滤掉。
            runCatching { bridgeApi.fetchTasks(targetIde = null, status = null, project = null) }

                .onSuccess { list ->

                    // 保留当前项目下所有 IDE 的任务；“当前/全部”只在列表组件中筛选。
                    _state.value = _state.value.copy(tasks = list, tasksLoading = false)

                    // 保存任务列表到本地持久化缓存

                    cc.aidelink.app.data.repository.OfflineTaskCache.saveServerTasks(appContext, list)

                    // 离线任务保留在本地，等待用户点击后同步并派发。
                    loadOfflineTasks()

                }

                .onFailure {

                    // 服务器不可用，从本地缓存加载历史任务列表，并合并待同步的离线任务

                    val cachedTasks = cc.aidelink.app.data.repository.OfflineTaskCache.getServerTasks(appContext)

                    _state.value = _state.value.copy(tasks = cachedTasks)

                    loadOfflineTasks()

                    _state.value = _state.value.copy(tasksLoading = false)

                }

        }

    }

    suspend fun loadProject() {

        val projectResponse = runCatching { bridgeApi.getProjects() }.getOrNull()
        val settings = runCatching { bridgeApi.fetchSettings() }.getOrNull() ?: return

        val rawPath = settings.current_project ?: settings.project_dir ?: ""

        val projPath = rawPath.replace('/', '\\')

        val name = if (projPath.isNotBlank()) projPath.substringAfterLast('\\') else ""
        val projects = projectResponse?.projects ?: _state.value.projects
        val currentProject = projects.firstOrNull {
            it.path.replace('/', '\\').trimEnd('\\').equals(projPath.trimEnd('\\'), ignoreCase = true)
        }
        val capabilities = currentProject?.capabilities.orEmpty()
            .map { it.trim().lowercase() }
            .filter { it in PROJECT_SURFACES }
            .distinct()
        val previousSurface = _state.value.selectedSurface
        val selectedSurface = previousSurface?.takeIf { it in capabilities && capabilities.size > 1 }

        _state.value = _state.value.copy(
            currentProjectPath = projPath,
            currentProjectName = name,
            projects = projects,
            currentProjectCapabilities = capabilities,
            selectedSurface = selectedSurface,
        )
        loadOfflineTasks()

    }

    fun selectProject(path: String) {
        viewModelScope.launch(Dispatchers.IO) {
            if (bridgeApi.selectProject(path)) {
                loadProject()
                loadTasks()
            }
        }
    }

    fun selectSurface(surface: String) {
        val available = _state.value.currentProjectCapabilities
        if (available.size <= 1 || surface !in available) return
        _state.value = _state.value.copy(
            selectedSurface = if (_state.value.selectedSurface == surface) null else surface,
        )
    }



    // ─── 批量操作 ───



    fun enterBatchMode(firstTaskId: String) {

        _state.value = _state.value.copy(batchMode = true, selectedTaskIds = setOf(firstTaskId))

    }



    fun exitBatchMode() {

        _state.value = _state.value.copy(batchMode = false, selectedTaskIds = emptySet())

    }



    fun toggleTaskSelection(taskId: String) {

        val current = _state.value.selectedTaskIds

        _state.value = _state.value.copy(

            selectedTaskIds = if (taskId in current) current - taskId else current + taskId

        )

    }



    fun selectTasks(taskIds: Set<String>) {

        _state.value = _state.value.copy(selectedTaskIds = taskIds)

    }



    fun openTaskThread(taskId: String) {

        _state.value = _state.value.copy(
            activeTaskId = taskId,
            editingTaskId = null,
            input = "",
            isPromptMode = false,
            promptCandidates = emptyList(),
        )

    }



    fun closeTaskThread() {

        _state.value = _state.value.copy(activeTaskId = null)

    }



    fun startTaskEdit(taskId: String) {

        val task = _state.value.tasks.find { it.task_id == taskId } ?: return
        val draft = _state.value.input
        _state.value = _state.value.copy(
            editingTaskId = taskId,
            inputDraftBeforeTaskEdit = draft,
            input = task.text.ifBlank { task.title ?: "" },
            isPromptMode = false,
            promptCandidates = emptyList(),
        )

    }



    fun cancelTaskEdit() {

        _state.value = _state.value.copy(
            editingTaskId = null,
            input = _state.value.inputDraftBeforeTaskEdit,
            inputDraftBeforeTaskEdit = "",
            isPromptMode = false,
            promptCandidates = emptyList(),
        )

    }



    fun saveTaskEdit() {

        val taskId = _state.value.editingTaskId ?: return
        val message = _state.value.input.trim()
        if (message.isBlank() || _state.value.sending) return
        viewModelScope.launch(Dispatchers.IO) {
            _state.value = _state.value.copy(sending = true)
            val ok = bridgeApi.editTask(taskId, message)
            _state.value = _state.value.copy(sending = false)
            if (ok) {
                _state.value = _state.value.copy(
                    editingTaskId = null,
                    input = _state.value.inputDraftBeforeTaskEdit,
                    inputDraftBeforeTaskEdit = "",
                    isPromptMode = false,
                    promptCandidates = emptyList(),
                )
                loadTasks()
            } else {
                _state.value = _state.value.copy(errorMessage = "任务修改失败，可能当前状态不允许编辑")
            }
        }

    }



    fun sendTaskThreadMessage(taskId: String, text: String) {

        if (text.isBlank() || _state.value.sending) return

        viewModelScope.launch(Dispatchers.IO) {

            _state.value = _state.value.copy(sending = true, input = "", isPromptMode = false)

            try {

                val ok = bridgeApi.sendTaskFeedback(taskId, text)

                _state.value = _state.value.copy(sending = false)

                if (ok) {

                    loadTasks()

                    reload()

                    _state.value = _state.value.copy(toastMessage = "已补充到当前任务")

                } else {

                    _state.value = _state.value.copy(errorMessage = "任务补充失败，请检查任务状态或电脑端桥接服务")

                }

            } catch (e: Exception) {

                _state.value = _state.value.copy(sending = false, errorMessage = e.message ?: "任务补充失败")

            }

        }

    }



    fun optimizeTaskDraft() {

        val text = _state.value.input.trim()
        if (text.isBlank() || _state.value.promptPredictLoading) return
        _state.value = _state.value.copy(promptPredictLoading = true, promptCandidates = emptyList())
        viewModelScope.launch(Dispatchers.IO) {
            val task = _state.value.editingTaskId?.let { id -> _state.value.tasks.find { it.task_id == id } }
            val resp = bridgeApi.predictPrompts(
                file = "",
                name = task?.title ?: "任务",
                desc = text,
                category = PromptAction.OPTIMIZE.name,
                userReq = text
            )
            val candidate = resp.candidates.firstOrNull()?.prompt
            _state.value = _state.value.copy(
                promptPredictLoading = false,
                promptCandidates = if (resp.success) resp.candidates else emptyList(),
                input = candidate ?: _state.value.input,
                isPromptMode = candidate != null,
            )
        }

    }



    fun batchDelete() {

        val ids = _state.value.selectedTaskIds.toList()

        viewModelScope.launch(Dispatchers.IO) {

            ids.forEach { id -> runCatching { bridgeApi.deleteTask(id) } }

            exitBatchMode()

            loadTasks()

        }

    }



    fun batchComplete() {

        val ids = _state.value.selectedTaskIds.toList()

        viewModelScope.launch(Dispatchers.IO) {

            ids.forEach { id -> runCatching { bridgeApi.completeTask(id) } }

            exitBatchMode()

            loadTasks()

        }

    }



    fun createTask(text: String, title: String? = null, targetIde: String? = null) {

        viewModelScope.launch(Dispatchers.IO) {

            _state.value = _state.value.copy(sending = true)

            val isOnline = cc.aidelink.app.data.repository.ConnectionState.bridgeOnline.value

            val requestedTarget = targetIde ?: _state.value.target.key
            val target = normalizeTaskTarget(requestedTarget)

            try {

                // 健康检查状态可能比真实请求慢一拍。只要服务端创建没有成功，
                // 就必须回退到本地缓存，避免断网瞬间把用户输入直接丢掉。
                val createdOnServer = isOnline && runCatching {
                    bridgeApi.createTask(
                        text = text,
                        title = title,
                        targetIde = target.ifBlank { null },
                        surface = _state.value.selectedSurface,
                    )
                }.getOrDefault(false)

                if (!shouldFallbackToOfflineTaskCache(isOnline, createdOnServer)) {
                    _state.value = _state.value.copy(sending = false)
                    if (_state.value.monitorActive) wakeMonitor()
                    loadTasks()
                    return@launch
                }

                saveOfflineTask(text = text, title = title, isInspiration = false)

            } catch (e: Exception) {

                // 本地保存本身失败时才向用户报告创建失败；网络异常由离线缓存兜底。
                _state.value = _state.value.copy(sending = false, errorMessage = e.message ?: "任务保存失败")

            }

        }

    }

    fun installMcp(ide: String) {
        viewModelScope.launch(Dispatchers.IO) {
            val ok = runCatching { bridgeApi.installMcp(ide) }.getOrDefault(false)
            _state.value = _state.value.copy(toastMessage = if (ok) "MCP 安装成功：$ide" else "MCP 安装失败：$ide")
        }
    }

    fun bindIdeWindow(ide: String) {
        viewModelScope.launch(Dispatchers.IO) {
            val ok = runCatching { bridgeApi.autoBindIdeWindow(ide) }.getOrDefault(false)
            _state.value = _state.value.copy(toastMessage = if (ok) "窗口绑定成功：$ide" else "窗口绑定失败，请先激活 IDE 窗口")
        }
    }

    fun bindIdeWindowAndCalibrate(ide: String) {
        viewModelScope.launch(Dispatchers.IO) {
            val ok = runCatching { bridgeApi.autoBindIdeWindow(ide) }.getOrDefault(false)
            if (ok) {
                _state.value = _state.value.copy(toastMessage = "窗口绑定成功，正在进入校准：$ide")
                withContext(Dispatchers.Main) { openIdeCalibration(ide) }
            } else {
                _state.value = _state.value.copy(toastMessage = "窗口绑定失败，请先激活 IDE 窗口")
            }
        }
    }

    fun openIdeCalibration(ide: String) {
        val target = Target.fromKey(ide)
        _state.value = _state.value.copy(target = target)
        setShowLiveMonitorDialog(true)
    }

    fun setInputPoint(x: Float, y: Float) {
        _state.value = _state.value.copy(
            inputPoint = InputPoint(x.coerceIn(0f, 0.99f), y.coerceIn(0f, 0.99f)),
            focusInputEnabled = true,
        )
    }

    fun setFocusInputEnabled(enabled: Boolean) {
        _state.value = _state.value.copy(focusInputEnabled = enabled)
    }

    fun createOfflineTaskFromInput() {
        val text = _state.value.input.trim()
        if (text.isEmpty() || _state.value.sending) return

        _state.value = _state.value.copy(input = "", sending = true)
        viewModelScope.launch(Dispatchers.IO) {
            try {
                saveOfflineTask(text = text, title = null, isInspiration = true)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    sending = false,
                    errorMessage = e.message ?: "随记保存失败",
                )
            }
        }
    }

    private suspend fun saveOfflineTask(
        text: String,
        title: String?,
        isInspiration: Boolean,
    ) {
        val status = "draft"
        cc.aidelink.app.data.repository.OfflineTaskCache.save(
            appContext,
            title ?: text.take(40),
            text,
            _state.value.currentProjectPath,
            status,
            taskType = if (isInspiration) "inspiration" else "code",
            surface = _state.value.selectedSurface,
        )
        _state.value = _state.value.copy(
            sending = false,
            errorMessage = null,
            toastMessage = if (isInspiration) "已加入随记" else "已加入待派发",
        )
        loadOfflineTasks()
    }



    /**

     * 加载离线缓存的任务到任务列表

     */

    private fun loadOfflineTasks() {

        val projectPath = _state.value.currentProjectPath
        cc.aidelink.app.data.repository.OfflineTaskCache.claimLegacyProject(appContext, projectPath)
        val offlineTasks = cc.aidelink.app.data.repository.OfflineTaskCache.getPendingForProject(appContext, projectPath)

        val localIdeaIds = cc.aidelink.app.data.repository.OfflineTaskCache
            .getPending(appContext)
            .map { it.id }
            .toSet()
        val currentTasks = _state.value.tasks
            .filterNot { it.task_id in localIdeaIds }
            .toMutableList()

        for (ot in offlineTasks.reversed()) {

            if (currentTasks.none { it.task_id == ot.id }) {

                currentTasks.add(0, AideTask(

                    task_id = ot.id,

                    title = ot.title,

                    text = ot.message,

                    target_ide = null,
                    project = projectPath,

                    status = ot.status,
                    task_type = ot.taskType,

                    created_at = java.time.Instant.ofEpochMilli(ot.createdAt).toString(),

                ))

            }

        }

        _state.value = _state.value.copy(tasks = currentTasks)

    }



    /**

     * 连接恢复后同步离线任务

     */

    fun syncOfflineTasks() {

        viewModelScope.launch(Dispatchers.IO) {

            val synced = cc.aidelink.app.data.repository.OfflineTaskCache.syncToServer(
                appContext,
                _state.value.currentProjectPath,
                bridgeApi,
            )

            if (synced > 0) {

                loadTasks()

                cc.aidelink.app.data.repository.OfflineTaskCache.clearSynced(appContext)

            }

        }

    }



    fun completeTask(taskId: String) {

        viewModelScope.launch(Dispatchers.IO) {

            val ok = bridgeApi.completeTask(taskId)

            if (ok) {

                loadTasks()

            }

        }

    }



    fun confirmTask(taskId: String) {

        viewModelScope.launch(Dispatchers.IO) {

            val ok = bridgeApi.confirmTask(taskId)

            if (ok) {

                loadTasks()

            }

        }

    }

    fun feedbackTestResult(taskId: String) {

        viewModelScope.launch(Dispatchers.IO) {

            val task = _state.value.tasks.firstOrNull { it.task_id == taskId }

            val summary = task?.test_summary?.trim().orEmpty()

            val evidence = task?.test_evidence?.trim().orEmpty()

            val feedback = buildString {

                append("测试未通过")

                if (summary.isNotBlank()) append("：").append(summary)

                if (evidence.isNotBlank()) append("\n验证证据：").append(evidence)

            }

            val ok = bridgeApi.sendTaskFeedback(taskId, feedback)

            _state.value = _state.value.copy(

                toastMessage = if (ok) "测试结果已反馈给开发 IDE" else "反馈开发 IDE 失败",

            )

            if (ok) loadTasks()

        }

    }



    fun failTask(taskId: String, error: String = "手动标记失败") {

        viewModelScope.launch(Dispatchers.IO) {

            val ok = bridgeApi.failTask(taskId, error)

            if (ok) {

                loadTasks()

            }

        }

    }



    fun deleteTask(taskId: String) {

        viewModelScope.launch(Dispatchers.IO) {

            if (cc.aidelink.app.data.repository.OfflineTaskCache.containsPending(appContext, taskId)) {
                cc.aidelink.app.data.repository.OfflineTaskCache.remove(appContext, taskId)
                _state.value = _state.value.copy(
                    tasks = _state.value.tasks.filterNot { it.task_id == taskId },
                    toastMessage = "随记已删除",
                )
                return@launch
            }

            val ok = bridgeApi.deleteTask(taskId)

            if (ok) {

                loadTasks()

            } else {

                _state.value = _state.value.copy(toastMessage = "删除失败，任务可能已被移除")

            }

        }

    }



    fun assignTask(taskId: String, targetIde: String) {

        viewModelScope.launch(Dispatchers.IO) {

            val ok = bridgeApi.assignTask(taskId, targetIde)

            if (ok) {

                loadTasks()

            }

        }

    }



    fun showDispatchSelector(taskIds: Set<String>) {

        _state.value = _state.value.copy(showDispatchDialog = true, dispatchTaskIds = taskIds)

    }



    fun hideDispatchSelector() {

        _state.value = _state.value.copy(showDispatchDialog = false, dispatchTaskIds = emptySet())

    }



    fun executeDispatch(
        targetIde: String,
        taskIds: Set<String>? = null,
        onComplete: ((Boolean) -> Unit)? = null,
    ) {

        val ids = (taskIds ?: _state.value.dispatchTaskIds).toList()

        if (ids.isEmpty()) return

        hideDispatchSelector()

        viewModelScope.launch(Dispatchers.IO) {
            val (offlineIds, serverIds) = ids.partition {
                cc.aidelink.app.data.repository.OfflineTaskCache.containsPending(appContext, it)
            }
            val offlineResults = offlineIds.map { taskId ->
                cc.aidelink.app.data.repository.OfflineTaskCache.syncAndDispatch(
                    context = appContext,
                    taskId = taskId,
                    targetIde = targetIde,
                    bridgeApi = bridgeApi,
                )
            }
            val serverOk = serverIds.isEmpty() || bridgeApi.dispatchTasks(serverIds, targetIde)
            val ok = serverOk && offlineResults.all { it }

            if (ok) {

                exitBatchMode()

                loadTasks()

            } else {
                loadOfflineTasks()
                _state.value = _state.value.copy(
                    toastMessage = "派发未成功，内容仍保存在随记中",
                )

            }

            kotlinx.coroutines.withContext(Dispatchers.Main) {
                onComplete?.invoke(ok)
            }

        }

    }



    // ─── Aide 进化面板 ───



    fun loadMimoWebUrl() {

        viewModelScope.launch(Dispatchers.IO) {

            try {

                val resp = bridgeApi.fetchMimoWebUrl()

                if (resp.ok) {

                    _state.value = _state.value.copy(mimoWebUrl = resp.url)

                }

            } catch (_: Exception) {}

        }

    }



    fun createNewSession() {

        viewModelScope.launch(Dispatchers.IO) {

            val resp = bridgeApi.createNewSession()

            if (resp.ok) {

                _state.value = _state.value.copy(

                    messages = emptyList(),

                    mimoWebUrl = resp.url,

                )

            }

        }

    }



    fun toggleWebButton() {

        _state.value = _state.value.copy(showWebButton = !_state.value.showWebButton)

    }



    data class OpenCodeWebConfig(val url: String, val username: String, val password: String)



    suspend fun resolveOpenCodeWebConfig(): OpenCodeWebConfig? {

        return try {

            val settings = bridgeApi.fetchSettings() ?: return null

            val connection = settings.opencode_web_connection ?: "lan"

            val port = settings.opencode_web_port ?: 4096



            val url: String

            val username: String

            val password: String



            if (connection == "frp") {

                val directUrl = settings.opencode_web_urls?.get("frp")?.trim() ?: ""

                if (directUrl.isNotBlank()) {

                    url = directUrl.trimEnd('/') + "/"

                } else {

                    val baseUrl = bridgeApi.baseUrl.trimEnd('/')

                    url = "$baseUrl/oc-web/"

                }

                username = ""

                password = settings.opencode_web_password ?: ""

            } else {

                val host = bridgeApi.baseUrl.substringAfter("://").substringBefore(":")

                url = "http://$host:$port"

                username = settings.opencode_web_username ?: ""

                password = settings.opencode_web_password ?: ""

            }

            OpenCodeWebConfig(url, username, password)

        } catch (_: Exception) { null }

    }



    // ─── 项目地图 ───



    fun toggleProjectMap() {

        val expanded = !_state.value.projectMapExpanded

        _state.value = _state.value.copy(projectMapExpanded = expanded)

        if (expanded && _state.value.projectMap.isEmpty()) {

            loadProjectMap()

        }

    }



    fun toggleProjectMapOnlyVisible() {

        val nextVal = !_state.value.projectMapOnlyVisible

        _state.value = _state.value.copy(projectMapOnlyVisible = nextVal)

        loadProjectMap()

    }



    fun loadProjectMap() {

        viewModelScope.launch(Dispatchers.IO) {

            _state.value = _state.value.copy(projectMapLoading = true)

            val resp = bridgeApi.fetchProjectMap(_state.value.projectMapOnlyVisible)

            _state.value = _state.value.copy(

                projectMap = if (resp.ok) resp.categories else emptyList(),

                projectMapLoading = false,

            )

        }

    }



    fun scanProjectMap() {

        viewModelScope.launch(Dispatchers.IO) {

            _state.value = _state.value.copy(projectMapLoading = true)

            val resp = bridgeApi.scanProjectMap(_state.value.projectMapOnlyVisible)

            _state.value = _state.value.copy(

                projectMap = if (resp.ok) resp.categories else emptyList(),

                projectMapLoading = false,

            )

        }

    }



    fun selectNode(node: ProjectNode) {

        _state.value = _state.value.copy(

            selectedNode = node,

            promptAction = null,

            promptDescription = "",

            generatedPrompt = "",

        )

    }



    fun selectLocatorComponent(file: String, name: String) {

        val node = ProjectNode(

            id = file,

            name = name,

            file = file

        )

        selectNode(node)

    }



    fun clearSelection() {



        _state.value = _state.value.copy(

            selectedNode = null,

            promptAction = null,

            promptDescription = "",

            generatedPrompt = "",

        )

    }



    fun setPromptAction(action: PromptAction) {

        _state.value = _state.value.copy(promptAction = action)

    }



    fun setPromptDescription(desc: String) {

        _state.value = _state.value.copy(promptDescription = desc)

    }



    fun setPromptVersion(version: String) {

        _state.value = _state.value.copy(promptVersion = version)

    }



    fun generatePrompt() {

        val node = _state.value.selectedNode ?: return

        val action = _state.value.promptAction ?: return

        val desc = _state.value.promptDescription.trim()



        val typeCN = when (action) {

            PromptAction.BUG_FIX -> "修复bug"

            PromptAction.OPTIMIZE -> "功能优化"

            PromptAction.NEW_FEATURE -> "新增功能"

            PromptAction.FEATURE_LOCK -> "功能锁定"

        }



        val prompt = buildString {

            if (desc.isNotEmpty()) {

                append("【内容】$desc\n\n")

            } else {

                append("【内容】（请说明您希望实现的功能）\n\n")

            }

            append("【代码修改与优化任务】\n")

            append("目标文件: ${node.file ?: ""}\n")

            val lineRange = if (node.line_start != null && node.line_end != null) {

                " (L${node.line_start}-${node.line_end})"

            } else ""

            if (lineRange.isNotEmpty()) {

                append("目标范围: $lineRange\n")

            }

            append("组件/类/函数: ${node.name}\n")

            if (!node.description.isNullOrEmpty()) {

                append("组件描述: ${node.description}\n")

            }

            append("修改类型: $typeCN")

        }



        _state.value = _state.value.copy(generatedPrompt = prompt)

    }



    fun useGeneratedPrompt() {

        val prompt = _state.value.generatedPrompt

        if (prompt.isNotEmpty()) {

            _state.value = _state.value.copy(

                input = prompt,

                isPromptMode = true,

                generatedPrompt = "",

                selectedNode = null,

                promptAction = null,

                promptDescription = "",

                projectMapExpanded = false,

            )

        }

    }



    fun predictPrompts(userReq: String, isTaskMode: Boolean = false) {

        val action = if (isTaskMode) _state.value.taskPromptAction else _state.value.promptAction

        if (action == null) return

        _state.value = _state.value.copy(promptPredictLoading = true, promptCandidates = emptyList())

        viewModelScope.launch(Dispatchers.IO) {

            val file: String

            val name: String

            val desc: String



            if (isTaskMode) {

                val taskText = _state.value.taskPromptTaskText

                val fileMatch = Regex("目标文件:\\s*(.+)").find(taskText)

                val compMatch = Regex("组件/类/函数:\\s*(.+)").find(taskText)

                file = fileMatch?.groupValues?.get(1)?.trim() ?: ""

                name = compMatch?.groupValues?.get(1)?.trim() ?: ""

                desc = extractTaskContent(taskText)

            } else {

                val node = _state.value.selectedNode ?: return@launch

                file = node.file ?: ""

                name = node.name

                desc = node.description ?: ""

            }



            val resp = bridgeApi.predictPrompts(

                file = file,

                name = name,

                desc = desc,

                category = action.name,

                userReq = userReq

            )

            _state.value = _state.value.copy(

                promptPredictLoading = false,

                promptCandidates = if (resp.success) resp.candidates else emptyList()

            )

        }

    }





    fun lockProjectFeature() {

        val node = _state.value.selectedNode ?: return

        val version = _state.value.promptVersion.trim()

        val desc = _state.value.promptDescription.trim()



        _state.value = _state.value.copy(projectMapLoading = true)

        viewModelScope.launch(Dispatchers.IO) {

            try {

                val resp = bridgeApi.lockProjectFeature(

                    nodeId = node.id,

                    nodeName = node.name,

                    file = node.file ?: "",

                    symbol = node.symbolName,

                    version = version,

                    description = desc

                )

                if (resp.ok) {

                    _state.value = _state.value.copy(

                        projectMapLoading = false,

                        selectedNode = null,

                        promptAction = null,

                        promptDescription = "",

                        generatedPrompt = ""

                    )

                    val systemMsg = ChatMessage(

                        sender = "assistant",

                        text = "🔒 功能 [${node.name}] 已成功在版本 $version 锁定并完成备份，规则已注入 AGENTS.md 防御其他 IDE 修改损坏！\n\n版本作用详情已记入 docs/version_features.md。"

                    )

                    _state.value = _state.value.copy(

                        messages = _state.value.messages + systemMsg

                    )

                } else {

                    _state.value = _state.value.copy(

                        projectMapLoading = false,

                        errorMessage = resp.error ?: "功能锁定失败"

                    )

                }

            } catch (e: Exception) {

                _state.value = _state.value.copy(

                    projectMapLoading = false,

                    errorMessage = e.message ?: "网络异常"

                )

            }

        }

    }



    // ─── 任务提示词构建器 ───



    fun showTaskPromptBuilder(taskId: String) {

        val task = _state.value.tasks.find { it.task_id == taskId } ?: return

        _state.value = _state.value.copy(

            showTaskPromptDialog = true,

            taskPromptTaskId = taskId,

            taskPromptTaskText = task.text,

            taskPromptAction = null,

            taskPromptDescription = "",

            taskPromptGenerated = "",

        )

    }



    fun dismissTaskPromptBuilder() {

        _state.value = _state.value.copy(

            showTaskPromptDialog = false,

            taskPromptTaskId = "",

            taskPromptTaskText = "",

            taskPromptAction = null,

            taskPromptDescription = "",

            taskPromptGenerated = "",

        )

    }



    fun setTaskPromptAction(action: PromptAction) {

        _state.value = _state.value.copy(taskPromptAction = action)

    }



    fun setTaskPromptDescription(desc: String) {

        _state.value = _state.value.copy(taskPromptDescription = desc)

    }



    fun generateTaskPrompt() {

        val taskText = _state.value.taskPromptTaskText

        val action = _state.value.taskPromptAction ?: return

        val desc = _state.value.taskPromptDescription.trim()



        val typeCN = when (action) {

            PromptAction.BUG_FIX -> "修复bug"

            PromptAction.OPTIMIZE -> "功能优化"

            PromptAction.NEW_FEATURE -> "新增功能"

            PromptAction.FEATURE_LOCK -> "功能锁定"

        }



        val contentPart = extractTaskContent(taskText).ifBlank { _state.value.taskPromptTaskId }

        val fileMatch = Regex("目标文件:\\s*(.+)").find(taskText)

        val compMatch = Regex("组件/类/函数:\\s*(.+)").find(taskText)

        val file = fileMatch?.groupValues?.get(1)?.trim() ?: ""

        val component = compMatch?.groupValues?.get(1)?.trim() ?: ""



        val prompt = buildString {

            if (desc.isNotEmpty()) {

                append("【内容】$desc\n\n")

            } else {

                append("【内容】$contentPart\n\n")

            }

            append("【代码修改与优化任务】\n")

            if (file.isNotEmpty()) {

                append("目标文件: $file\n")

            }

            if (component.isNotEmpty()) {

                append("组件/类/函数: $component\n")

            }

            append("修改类型: $typeCN")

        }



        _state.value = _state.value.copy(taskPromptGenerated = prompt)

    }



    fun useTaskPrompt() {

        val prompt = _state.value.taskPromptGenerated

        if (prompt.isNotEmpty()) {

            _state.value = _state.value.copy(

                input = prompt,

                isPromptMode = true,

                showTaskPromptDialog = false,

                taskPromptTaskId = "",

                taskPromptTaskText = "",

                taskPromptAction = null,

                taskPromptDescription = "",

                taskPromptGenerated = "",

            )

        }

    }



    fun clearPromptMode() {

        _state.value = _state.value.copy(isPromptMode = false)

    }



    override fun onCleared() {

        super.onCleared()

        stopMonitorPolling()

        recycleOldBitmap(_state.value.monitorImage)

        recycleOldBitmap(_state.value.dialogUncroppedImage)

    }

}


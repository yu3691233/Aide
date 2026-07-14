package cc.aidelink.app.ui.screens.settings

import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.RadioButtonChecked
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import android.content.Context
import androidx.compose.material.icons.filled.Computer
import androidx.compose.material.icons.filled.Language
import androidx.compose.material.icons.filled.LocationSearching
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.PhoneAndroid
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.ui.graphics.Color
import dagger.hilt.android.qualifiers.ApplicationContext
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import cc.aidelink.app.BuildConfig
import cc.aidelink.app.data.api.BridgeApi
import cc.aidelink.app.data.repository.SettingsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import io.ktor.client.request.get
import io.ktor.client.call.body

internal fun normalizeWindowsPath(path: String): String = path.trim().replace('/', '\\')

@HiltViewModel
class AideLinkSettingsViewModel @Inject constructor(
    private val settings: SettingsRepository,
    private val bridgeApi: cc.aidelink.app.data.api.BridgeApi,
    private val bridgeServerRepo: cc.aidelink.app.data.repository.BridgeServerRepository,
    @ApplicationContext private val appContext: Context,
) : ViewModel() {

    var onNavigateBack: (() -> Unit)? = null

    data class UiState(
        val serverUrl: String = "",
        val xiaomenglingModel: String = "free",
        val availableModels: List<cc.aidelink.app.domain.model.bridge.ActiveModel> = emptyList(),
        val desktopIde: String = "trae",
        val desktopIdePath: String = "",
        val desktopIdeList: List<String> = emptyList(),
        val availableIdes: List<cc.aidelink.app.domain.model.bridge.DesktopIde> = emptyList(),
        val bridgeServers: List<cc.aidelink.app.domain.model.BridgeServerConfig> = emptyList(),
        val activeServerId: String? = null,
        val isScanning: Boolean = false,
        val scanMessage: String? = null,
        val isCheckingUpdate: Boolean = false,
        val isDownloadingUpdate: Boolean = false,
        val updateError: String? = null,
        val updateStatusMessage: String? = null,
        val notificationsEnabled: Boolean = true,
        val silentNotifications: Boolean = false,
        val hapticFeedback: Boolean = true,
        val globalLocatorEnabled: Boolean = false,
        val opencodeWebUrl: String = "",
        val opencodeWebUsername: String = "",
        val opencodeWebPassword: String = "",
        val opencodeWebConnection: String = "lan",
        val opencodeProjectDir: String = "",
        val projects: List<BridgeApi.ProjectInfo> = emptyList(),
        val currentProjectPath: String = "",
        val isLoadingProjects: Boolean = false,
        val isLan: Boolean = false,
        val isAdbInstalling: Boolean = false,
        val androidInstallStatus: String? = null,
        val androidInstallError: String? = null,
    )

    private val _state = kotlinx.coroutines.flow.MutableStateFlow(UiState())
    val state: kotlinx.coroutines.flow.StateFlow<UiState> = _state

    init {
        val cachedIdes = loadCachedIdes()
        val cachedModels = loadCachedModels()
        val savedUrl = settings.getServerUrl()
        val initialServers = if (savedUrl.isNotBlank() && !cc.aidelink.app.data.repository.BridgeServerRepository.isPhoneLoopbackUrl(savedUrl)) {
            listOf(cc.aidelink.app.domain.model.BridgeServerConfig(
                id = "__current__",
                name = "当前服务器",
                url = savedUrl.trimEnd('/'),
                serverType = if (savedUrl.contains("cciv.cc")) cc.aidelink.app.domain.model.BridgeServerType.FRP else cc.aidelink.app.domain.model.BridgeServerType.LOCAL,
                autoConnect = false,
                lastConnected = null
            ))
        } else {
            emptyList()
        }
        _state.value = UiState(
            serverUrl = savedUrl,
            xiaomenglingModel = settings.getXiaomenglingModel(),
            desktopIde = settings.getDesktopIde(),
            desktopIdePath = settings.getDesktopIdePath(),
            desktopIdeList = settings.getDesktopIdeList(),
            availableIdes = cachedIdes,
            availableModels = cachedModels,
            bridgeServers = initialServers,
            notificationsEnabled = settings.notificationsEnabledRaw(),
            silentNotifications = settings.silentNotificationsRaw(),
            hapticFeedback = settings.hapticFeedbackRaw(),
            globalLocatorEnabled = settings.globalLocatorEnabledRaw(),
            isLan = isLanUrl(savedUrl),
        )


        viewModelScope.launch {
            try {
                val ides = bridgeApi.fetchDesktopIdes()
                _state.value = _state.value.copy(availableIdes = ides)
                saveCachedIdes(ides)
            } catch (_: Exception) {}
            try {
                val models = bridgeApi.fetchActiveModels()
                _state.value = _state.value.copy(availableModels = models)
                saveCachedModels(models)
            } catch (_: Exception) {}

            try {
                val allServers = bridgeServerRepo.getAllServers()
                if (savedUrl.isNotBlank() &&
                    !cc.aidelink.app.data.repository.BridgeServerRepository.isPhoneLoopbackUrl(savedUrl) &&
                    allServers.none { it.url.trimEnd('/') == savedUrl.trimEnd('/') }
                ) {
                    val newServer = bridgeServerRepo.addServer(
                        name = "默认服务器",
                        url = savedUrl,
                        type = cc.aidelink.app.domain.model.BridgeServerType.CUSTOM
                    )
                    if (bridgeServerRepo.activeServerId.first() == null) {
                        bridgeServerRepo.setActiveServerId(newServer.id)
                    }
                }
            } catch (_: Exception) {}

            // 把当前服务器通过 FRP 暴露的公网域名自动同步进服务器列表，方便用户切换到公网访问
            try {
                val frpUrl = bridgeApi.fetchFrpPublicUrl()?.trim()?.trimEnd('/')
                if (!frpUrl.isNullOrBlank()) {
                    val existing = bridgeServerRepo.getAllServers()
                    if (existing.none { it.url.trim().trimEnd('/') == frpUrl }) {
                        val host = kotlin.runCatching {
                            java.net.URL(if (!frpUrl.startsWith("http://") && !frpUrl.startsWith("https://")) "https://$frpUrl" else frpUrl).host
                        }.getOrNull() ?: frpUrl
                        bridgeServerRepo.addServer(
                            name = "FRP · $host",
                            url = frpUrl,
                            type = cc.aidelink.app.domain.model.BridgeServerType.FRP
                        )
                    }
                }
            } catch (_: Exception) {}

            try {
                val settingsData = bridgeApi.fetchSettings()
                if (settingsData != null) {
                    val urls = settingsData.opencode_web_urls
                    _state.value = _state.value.copy(
                        opencodeWebUrl = urls?.get("frp") ?: urls?.get("lan") ?: "",
                        opencodeWebUsername = settingsData.opencode_web_username ?: "",
                        opencodeWebPassword = settingsData.opencode_web_password ?: "",
                        opencodeWebConnection = settingsData.opencode_web_connection ?: "lan",
                        opencodeProjectDir = normalizeWindowsPath(settingsData.project_dir ?: settingsData.opencode_project_dir ?: ""),
                    )
                }
            } catch (_: Exception) {}

            try {
                settings.setBridgeApi(bridgeApi)
                settings.syncFromServer()
            } catch (_: Exception) {}

            // 初始加载项目列表
            loadProjectsInternal()
        }
        viewModelScope.launch {
            bridgeServerRepo.servers.collect { servers ->
                _state.value = _state.value.copy(bridgeServers = servers)
            }
        }
        viewModelScope.launch {
            bridgeServerRepo.activeServerId.collect { activeId ->
                _state.value = _state.value.copy(activeServerId = activeId)
            }
        }
    }

    private fun getCachedPrefs() = appContext.getSharedPreferences("settings_cache", Context.MODE_PRIVATE)

    private val cacheJson = kotlinx.serialization.json.Json { ignoreUnknownKeys = true; encodeDefaults = true }

    private fun loadCachedIdes(): List<cc.aidelink.app.domain.model.bridge.DesktopIde> {
        return try {
            val raw = getCachedPrefs().getString("cached_ides", null) ?: return emptyList()
            cacheJson.decodeFromString<List<cc.aidelink.app.domain.model.bridge.DesktopIde>>(raw)
        } catch (_: Exception) { emptyList() }
    }

    private fun saveCachedIdes(ides: List<cc.aidelink.app.domain.model.bridge.DesktopIde>) {
        try {
            val serializer = kotlinx.serialization.builtins.ListSerializer(cc.aidelink.app.domain.model.bridge.DesktopIde.serializer())
            getCachedPrefs().edit().putString("cached_ides", cacheJson.encodeToString(serializer, ides)).apply()
        } catch (_: Exception) {}
    }

    private fun loadCachedModels(): List<cc.aidelink.app.domain.model.bridge.ActiveModel> {
        return try {
            val raw = getCachedPrefs().getString("cached_models", null) ?: return emptyList()
            cacheJson.decodeFromString<List<cc.aidelink.app.domain.model.bridge.ActiveModel>>(raw)
        } catch (_: Exception) { emptyList() }
    }

    private fun saveCachedModels(models: List<cc.aidelink.app.domain.model.bridge.ActiveModel>) {
        try {
            val serializer = kotlinx.serialization.builtins.ListSerializer(cc.aidelink.app.domain.model.bridge.ActiveModel.serializer())
            getCachedPrefs().edit().putString("cached_models", cacheJson.encodeToString(serializer, models)).apply()
        } catch (_: Exception) {}
    }


    fun save(serverUrl: String) {
        viewModelScope.launch {
            settings.setServerUrl(serverUrl)
            bridgeApi.updateBaseUrl(serverUrl)
            _state.value = _state.value.copy(serverUrl = serverUrl, isLan = isLanUrl(serverUrl))
        }
    }

    suspend fun getProjects(): BridgeApi.ProjectsResponse = bridgeApi.getProjects()
    suspend fun selectProject(path: String): Boolean = bridgeApi.selectProject(path)

    private suspend fun loadProjectsInternal() {
        _state.value = _state.value.copy(isLoadingProjects = true)
        try {
            val resp = bridgeApi.getProjects()
            _state.value = _state.value.copy(
                projects = resp.projects,
                currentProjectPath = normalizeWindowsPath(resp.current_project),
                isLoadingProjects = false,
            )
        } catch (_: Exception) {
            _state.value = _state.value.copy(isLoadingProjects = false)
        }
    }

    fun loadProjects() {
        viewModelScope.launch {
            loadProjectsInternal()
        }
    }

    fun deleteProject(idx: Int) {
        viewModelScope.launch {
            val ok = bridgeApi.deleteProject(idx)
            if (ok) loadProjectsInternal()
        }
    }

    fun selectProjectAndRefresh(path: String, navigateBack: Boolean = false) {
        viewModelScope.launch {
            val ok = bridgeApi.selectProject(normalizeWindowsPath(path))
            if (ok) {
                loadProjectsInternal()
                if (navigateBack) {
                    onNavigateBack?.invoke()
                }
            }
        }
    }

    fun saveXiaomenglingModel(model: String) {
        viewModelScope.launch {
            settings.setXiaomenglingModel(model)
            settings.pushToServer()
        }
    }

    fun saveDesktopIde(ide: String, path: String) {
        viewModelScope.launch {
            settings.setDesktopIde(ide)
            settings.setDesktopIdePath(path)
            settings.pushToServer()
        }
    }

    fun saveDesktopIdeList(list: List<String>) {
        _state.value = _state.value.copy(desktopIdeList = list)
        settings.saveDesktopIdeList(list)
    }

    fun setNotificationsEnabled(enabled: Boolean) {
        _state.value = _state.value.copy(notificationsEnabled = enabled)
        viewModelScope.launch {
            settings.setNotificationsEnabled(enabled)
            settings.pushToServer()
        }
    }

    fun setSilentNotifications(enabled: Boolean) {
        _state.value = _state.value.copy(silentNotifications = enabled)
        viewModelScope.launch { settings.setSilentNotifications(enabled) }
    }

    fun setHapticFeedback(enabled: Boolean) {
        _state.value = _state.value.copy(hapticFeedback = enabled)
        viewModelScope.launch {
            settings.setHapticFeedback(enabled)
            settings.pushToServer()
        }
    }

    fun setGlobalLocatorEnabled(enabled: Boolean) {
        _state.value = _state.value.copy(globalLocatorEnabled = enabled)
        viewModelScope.launch { settings.setGlobalLocatorEnabled(enabled) }
    }

    fun saveOpenCodeWebSettings(connection: String, password: String, projectDir: String) {
        _state.value = _state.value.copy(
            opencodeWebConnection = connection,
            opencodeWebPassword = password,
            opencodeProjectDir = projectDir,
        )
        viewModelScope.launch {
            bridgeApi.patchSetting("opencode_web_connection", kotlinx.serialization.json.JsonPrimitive(connection))
            bridgeApi.patchSetting("opencode_web_password", kotlinx.serialization.json.JsonPrimitive(password))
        }
    }

    fun refreshModels() {
        viewModelScope.launch {
            try {
                val models = bridgeApi.fetchActiveModels()
                _state.value = _state.value.copy(availableModels = models)
            } catch (e: Exception) {
            }
        }
    }

    fun refreshIdes() {
        viewModelScope.launch {
            try {
                // 设置页只显示当前连接电脑已经登记的 IDE；扫描由电脑端管理页显式触发。
                val ides = bridgeApi.fetchDesktopIdes()
                _state.value = _state.value.copy(availableIdes = ides)
            } catch (e: Exception) {
            }
        }
    }

    fun addBridgeServer(name: String, url: String, type: cc.aidelink.app.domain.model.BridgeServerType) {
        viewModelScope.launch {
            try {
                bridgeServerRepo.addServer(name, url, type)
            } catch (_: IllegalArgumentException) {
                _state.value = _state.value.copy(scanMessage = "不能添加手机本机地址，请填写电脑的局域网 IP 或公网域名")
            }
        }
    }

    fun addIdeFromDesktop() {
        viewModelScope.launch {
            val rawPath = bridgeApi.browsePath("从电脑选择 IDE 入口") ?: return@launch
            // 某些桥接/JSON 链路可能把反斜杠转义成两个，保存前统一归一化。
            val path = rawPath.replace("\\\\", "\\")
            // Windows 路径从电脑端返回，Android 的 java.io.File 不会把反斜杠
            // 识别为目录分隔符，必须手动兼容两种分隔符。
            val fileName = path.substringAfterLast('/').substringAfterLast('\\')
            val base = fileName.substringBeforeLast('.', fileName).ifBlank { "ide" }
            val key = base.lowercase().replace(Regex("[^a-z0-9]+"), "_").trim('_').ifBlank { "ide" }
            val ok = bridgeApi.saveManualIde(cc.aidelink.app.domain.model.bridge.DesktopIde(key = key, name = base, path = path))
            if (ok) refreshIdes()
        }
    }

    fun bindIdeWindow(ide: String) {
        viewModelScope.launch { bridgeApi.autoBindIdeWindow(ide) }
    }

    fun requestIdeCalibration(ide: String) {
        appContext.getSharedPreferences("aidelink_navigation", Context.MODE_PRIVATE)
            .edit().putString("pending_calibration_ide", ide).apply()
        onNavigateBack?.invoke()
    }

    fun installIdeMcp(ide: String) {
        viewModelScope.launch { bridgeApi.installMcp(ide) }
    }

    fun removeIde(ide: String) {
        viewModelScope.launch {
            if (bridgeApi.removeManualIde(ide)) refreshIdes()
        }
    }

    fun updateBridgeServer(server: cc.aidelink.app.domain.model.BridgeServerConfig) {
        viewModelScope.launch {
            try {
                bridgeServerRepo.updateServer(server)
            } catch (_: IllegalArgumentException) {
                _state.value = _state.value.copy(scanMessage = "不能保存手机本机地址，请填写电脑的局域网 IP 或公网域名")
            }
        }
    }

    fun deleteBridgeServer(serverId: String) {
        viewModelScope.launch {
            bridgeServerRepo.deleteServer(serverId)
        }
    }

    fun setActiveServer(serverId: String) {
        viewModelScope.launch {
            val currentActiveId = bridgeServerRepo.activeServerId.first()
            if (currentActiveId == serverId) {
                bridgeServerRepo.setActiveServerId(null)
            } else {
                val server = bridgeServerRepo.getAllServers().find { it.id == serverId }
                if (server != null) {
                    bridgeServerRepo.setActiveServerId(serverId)
                    settings.setServerUrl(server.url)
                    bridgeApi.updateBaseUrl(server.url)
                    bridgeServerRepo.updateLastConnected(serverId)
                    _state.value = _state.value.copy(serverUrl = server.url, isLan = isLanUrl(server.url))
                    try {
                        val ides = bridgeApi.fetchDesktopIdes()
                        _state.value = _state.value.copy(availableIdes = ides)
                    } catch (_: Exception) {}
                    try {
                        val models = bridgeApi.fetchActiveModels()
                        _state.value = _state.value.copy(availableModels = models)
                    } catch (_: Exception) {}
                    try {
                        val settingsData = bridgeApi.fetchSettings()
                        if (settingsData != null) {
                            _state.value = _state.value.copy(
                                opencodeWebUrl = settingsData.opencode_web_urls?.get("frp") ?: settingsData.opencode_web_urls?.get("lan") ?: "",
                                opencodeWebUsername = settingsData.opencode_web_username ?: "",
                                opencodeWebPassword = settingsData.opencode_web_password ?: "",
                                opencodeWebConnection = settingsData.opencode_web_connection ?: "lan",
                                opencodeProjectDir = normalizeWindowsPath(settingsData.project_dir ?: settingsData.opencode_project_dir ?: ""),
                            )
                        }
                    } catch (_: Exception) {}

                    // 切换服务器后刷新项目列表
                    loadProjectsInternal()
                }
            }
        }
    }

    fun scanLocalServers() {
        viewModelScope.launch {
            _state.value = _state.value.copy(isScanning = true)
            try {
                val nsdManager = appContext.getSystemService(android.content.Context.NSD_SERVICE) as android.net.nsd.NsdManager?
                
                if (nsdManager == null) {
                    _state.value = _state.value.copy(isScanning = false, scanMessage = "NSD 服务不可用")
                    return@launch
                }
                
                val discoveredServers = mutableListOf<cc.aidelink.app.domain.model.BridgeServerConfig>()
                val latch = java.util.concurrent.CountDownLatch(1)
                
                lateinit var discoveryListener: android.net.nsd.NsdManager.DiscoveryListener
                
                discoveryListener = object : android.net.nsd.NsdManager.DiscoveryListener {
                    override fun onStartDiscoveryFailed(serviceType: String?, errorCode: Int) {
                        _state.value = _state.value.copy(scanMessage = "mDNS 发现启动失败 (error=$errorCode)")
                        latch.countDown()
                    }
                    
                    override fun onStopDiscoveryFailed(serviceType: String?, errorCode: Int) {
                        latch.countDown()
                    }
                    
                    override fun onDiscoveryStarted(serviceType: String?) {
        viewModelScope.launch {
                            kotlinx.coroutines.delay(3000)
                            try {
                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                    nsdManager.stopServiceDiscovery(discoveryListener)
                                }
                            } catch (e: Exception) {
                            }
                            latch.countDown()
                        }
                    }
                    
                    override fun onDiscoveryStopped(serviceType: String?) {
                        latch.countDown()
                    }
                    
                    override fun onServiceFound(serviceInfo: android.net.nsd.NsdServiceInfo?) {
                        if (serviceInfo?.serviceType?.contains("_aidelink._tcp") == true) {
                            try {
                                nsdManager.resolveService(serviceInfo, object : android.net.nsd.NsdManager.ResolveListener {
                                    override fun onResolveFailed(serviceInfo: android.net.nsd.NsdServiceInfo?, errorCode: Int) {
                                    }
                                    
                                    override fun onServiceResolved(resolvedServiceInfo: android.net.nsd.NsdServiceInfo?) {
                                        val host = resolvedServiceInfo?.host?.hostAddress
                                        val port = resolvedServiceInfo?.port ?: 5000
                                        if (host != null && !host.matches(Regex("^172\\.(1[6-9]|2[0-9]|3[01])\\..*"))) {
                                            val server = cc.aidelink.app.domain.model.BridgeServerConfig(
                                                id = java.util.UUID.randomUUID().toString(),
                                                name = resolvedServiceInfo.serviceName ?: "局域网服务器",
                                                url = "http://$host:$port",
                                                serverType = cc.aidelink.app.domain.model.BridgeServerType.LOCAL,
                                                autoConnect = false,
                                                lastConnected = null
                                            )
                                            discoveredServers.add(server)
                                            _state.value = _state.value.copy(scanMessage = "发现: $host:$port")
                                        }
                                    }
                                })
                            } catch (e: Exception) {
                            }
                        }
                    }
                    
                    override fun onServiceLost(serviceInfo: android.net.nsd.NsdServiceInfo?) {
                    }
                }
                
                try {
                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                        nsdManager.discoverServices("_aidelink._tcp", android.net.nsd.NsdManager.PROTOCOL_DNS_SD, discoveryListener)
                    }
                    latch.await(5, java.util.concurrent.TimeUnit.SECONDS)

                    val existingServers = bridgeServerRepo.getAllServers()
                    discoveredServers.forEach { server ->
                        val isDuplicate = existingServers.any { existing ->
                            try {
                                val a = java.net.URL(existing.url)
                                val b = java.net.URL(server.url)
                                a.host.equals(b.host, ignoreCase = true) && a.port == b.port
                            } catch (_: Exception) {
                                existing.url.trimEnd('/') == server.url.trimEnd('/')
                            }
                        }
                        if (!isDuplicate) {
                            bridgeServerRepo.addServer(
                                name = server.name,
                                url = server.url,
                                type = server.serverType
                            )
                        }
                    }
                    if (discoveredServers.isNotEmpty()) {
                        val best = discoveredServers.first()
                        val existingMatch = existingServers.find { existing ->
                            try {
                                val a = java.net.URL(existing.url)
                                val b = java.net.URL(best.url)
                                a.host.equals(b.host, ignoreCase = true) && a.port == b.port
                            } catch (_: Exception) {
                                existing.url.trimEnd('/') == best.url.trimEnd('/')
                            }
                        }
                        val targetId = existingMatch?.id ?: best.id
                        val targetUrl = existingMatch?.url ?: best.url
                        bridgeServerRepo.setActiveServerId(targetId)
                        settings.setServerUrl(targetUrl)
                        bridgeApi.updateBaseUrl(targetUrl)
                        bridgeServerRepo.updateLastConnected(targetId)
                        _state.value = _state.value.copy(
                            scanMessage = "已切换到 ${targetUrl}",
                            serverUrl = targetUrl, isLan = isLanUrl(targetUrl)
                        )
                    } else {
                        _state.value = _state.value.copy(scanMessage = "未发现局域网服务器")
                    }
                } catch (e: Exception) {
                    _state.value = _state.value.copy(scanMessage = "扫描出错: ${e.message}")
                }
                
                _state.value = _state.value.copy(isScanning = false)
            } catch (e: Exception) {
                _state.value = _state.value.copy(isScanning = false, scanMessage = "扫描失败: ${e.message}")
            }
        }
    }

    fun forceRestartServer() {
        viewModelScope.launch {
            try {
                bridgeApi.restartServer()
            } catch (_: Exception) {}
        }
    }

    fun scanCurrentAndroidProject() {
        val path = _state.value.currentProjectPath
        if (path.isBlank()) return
        viewModelScope.launch {
            _state.value = _state.value.copy(androidInstallStatus = "正在扫描 Android 工程...", androidInstallError = null)
            val ok = bridgeApi.scanAndroidProject(path)
            loadProjectsInternal()
            _state.value = _state.value.copy(
                androidInstallStatus = if (ok) "扫描完成" else null,
                androidInstallError = if (ok) null else "Android 工程扫描失败",
            )
        }
    }

    fun browseAndAddProject() {
        viewModelScope.launch {
            val selected = bridgeApi.browseProjectFolder(_state.value.currentProjectPath)
            if (!selected.isNullOrBlank() && bridgeApi.selectProject(normalizeWindowsPath(selected))) {
                loadProjectsInternal()
            }
        }
    }

    private fun isLanUrl(url: String): Boolean {
        return url.contains("192.168.") || url.contains("10.") ||
               url.contains("172.16.") || url.contains("172.17.") ||
               url.contains("172.18.") || url.contains("172.19.") ||
               url.contains("172.2") || url.contains("172.3") ||
               url.contains("localhost") || url.contains("127.0.0.1")
    }

    fun adbSelfInstall() {
        viewModelScope.launch {
            _state.value = _state.value.copy(
                isAdbInstalling = true,
                updateError = null,
                updateStatusMessage = "正在检测无线调试..."
            )
            try {
                // 1) 检测 ADB 状态，未开启则自动开启
                val adbStatus = cc.aidelink.app.service.WirelessAdbManager.detectStatus(appContext)
                var targetPort = adbStatus.adbPort
                if (!adbStatus.wirelessAdbEnabled) {
                    _state.value = _state.value.copy(updateStatusMessage = "正在开启无线调试...")
                    val enableResult = cc.aidelink.app.service.WirelessAdbManager.enableWirelessAdb(appContext, _state.value.serverUrl)
                    if (enableResult.isFailure) {
                        _state.value = _state.value.copy(
                            isAdbInstalling = false,
                            updateError = "无法开启无线调试: ${enableResult.exceptionOrNull()?.message}",
                            updateStatusMessage = null
                        )
                        return@launch
                    }
                    val cr = enableResult.getOrNull()
                    if (cr != null) {
                        bridgeApi.deviceIp = cr.ip
                        targetPort = cr.port
                        // enableWirelessAdb 内部已等待端口就绪，直接用返回的端口
                    }
                }

                // 2) 执行 ADB 安装（携带 IP + port 确保连到正确设备）
                _state.value = _state.value.copy(updateStatusMessage = "通过 ADB 安装中...")
                val response = bridgeApi.adbSelfInstall(targetPort)
                if (response.ok) {
                    _state.value = _state.value.copy(
                        isAdbInstalling = false,
                        updateStatusMessage = "ADB 安装完成 ✓"
                    )
                } else {
                    _state.value = _state.value.copy(
                        isAdbInstalling = false,
                        updateError = response.error ?: "ADB 安装失败",
                        updateStatusMessage = null
                    )
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isAdbInstalling = false,
                    updateError = e.message ?: "ADB 安装失败",
                    updateStatusMessage = null
                )
            }
        }
    }

    fun adbProjectInstall(apkPath: String = "") {
        val projectPath = _state.value.currentProjectPath
        if (projectPath.isBlank()) {
            _state.value = _state.value.copy(androidInstallError = "请先选择目标项目")
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(isAdbInstalling = true, androidInstallError = null, androidInstallStatus = "正在检测无线调试...")
            try {
                val adbStatus = cc.aidelink.app.service.WirelessAdbManager.detectStatus(appContext)
                var targetPort = adbStatus.adbPort
                if (!adbStatus.wirelessAdbEnabled) {
                    _state.value = _state.value.copy(androidInstallStatus = "正在开启无线调试...")
                    val enabled = cc.aidelink.app.service.WirelessAdbManager.enableWirelessAdb(appContext, _state.value.serverUrl)
                    if (enabled.isFailure) {
                        _state.value = _state.value.copy(isAdbInstalling = false, androidInstallStatus = null, androidInstallError = "无法开启无线调试: ${enabled.exceptionOrNull()?.message}")
                        return@launch
                    }
                    enabled.getOrNull()?.let {
                        bridgeApi.deviceIp = it.ip
                        targetPort = it.port
                    }
                }
                _state.value = _state.value.copy(androidInstallStatus = "正在安装目标项目 APK...")
                val response = bridgeApi.adbProjectInstall(projectPath, apkPath, targetPort)
                _state.value = if (response.ok) {
                    _state.value.copy(isAdbInstalling = false, androidInstallStatus = response.message ?: "安装完成 ✓", androidInstallError = null)
                } else {
                    _state.value.copy(isAdbInstalling = false, androidInstallStatus = null, androidInstallError = response.error ?: "安装失败")
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(isAdbInstalling = false, androidInstallStatus = null, androidInstallError = e.message ?: "安装失败")
            }
        }
    }

    fun checkForUpdate(force: Boolean = false) {
        viewModelScope.launch {
            _state.value = _state.value.copy(
                isCheckingUpdate = true,
                updateError = null,
                updateStatusMessage = "正在检查更新..."
            )
            try {
                val response = bridgeApi.fetchAppVersion()
                if (response.ok) {
                    val serverCode = response.versionCode
                    val clientCode = BuildConfig.VERSION_CODE
                    if (serverCode > clientCode || force) {
                        _state.value = _state.value.copy(
                            isCheckingUpdate = false,
                            isDownloadingUpdate = true,
                            updateStatusMessage = "正在下载更新 (v${response.versionName})..."
                        )
                        downloadAndInstall()
                    } else {
                        _state.value = _state.value.copy(
                            isCheckingUpdate = false,
                            updateStatusMessage = "已是最新版本 (v${BuildConfig.VERSION_NAME})"
                        )
                    }
                } else {
                    _state.value = _state.value.copy(
                        isCheckingUpdate = false,
                        updateError = response.error ?: "获取版本信息失败",
                        updateStatusMessage = null
                    )
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isCheckingUpdate = false,
                    updateError = e.message ?: "检查更新失败",
                    updateStatusMessage = null
                )
            }
        }
    }

    private fun downloadAndInstall() {
        viewModelScope.launch {
            try {
                val response: io.ktor.client.statement.HttpResponse = bridgeApi.client.get("${bridgeApi.baseUrl}/app/download")
                if (response.status.value == 200) {
                    val bytes = response.body<ByteArray>()
                    val apkFile = java.io.File(appContext.cacheDir, "update.apk")
                    apkFile.writeBytes(bytes)

                    _state.value = _state.value.copy(
                        isDownloadingUpdate = false,
                        updateStatusMessage = "下载完成，准备安装..."
                    )

                    val authority = "${appContext.packageName}.fileprovider"
                    val uri = androidx.core.content.FileProvider.getUriForFile(appContext, authority, apkFile)
                    val intent = android.content.Intent(android.content.Intent.ACTION_VIEW).apply {
                        setDataAndType(uri, "application/vnd.android.package-archive")
                        addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    appContext.startActivity(intent)
                } else {
                    _state.value = _state.value.copy(
                        isDownloadingUpdate = false,
                        updateError = "下载失败: HTTP ${response.status.value}",
                        updateStatusMessage = null
                    )
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isDownloadingUpdate = false,
                    updateError = e.message ?: "下载更新失败",
                    updateStatusMessage = null
                )
            }
        }
    }

    fun reportAdbStatus(ip: String, port: Int, enabled: Boolean) {
        viewModelScope.launch {
            try {
                bridgeApi.reportAdbStatus(ip, port, enabled)
            } catch (_: Exception) {}
        }
    }
}


@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AideLinkSettingsScreen(
    onNavigateBack: () -> Unit,
    viewModel: AideLinkSettingsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsState()
    var serverUrl by remember(state.serverUrl) { mutableStateOf(state.serverUrl) }
    var xiaomenglingModel by remember(state.xiaomenglingModel) { mutableStateOf(state.xiaomenglingModel) }
    val context = LocalContext.current
    val lifecycleOwner = androidx.lifecycle.compose.LocalLifecycleOwner.current

    LaunchedEffect(Unit) {
        viewModel.onNavigateBack = onNavigateBack
    }

    androidx.compose.runtime.DisposableEffect(lifecycleOwner) {
        val observer = androidx.lifecycle.LifecycleEventObserver { _, event ->
            if (event == androidx.lifecycle.Lifecycle.Event.ON_RESUME) {
                viewModel.refreshModels()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("连接", "AI", "Android", "通用")

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("设置") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "返回")
                    }
                }
            )
        }
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            TabRow(selectedTabIndex = selectedTab) {
                tabs.forEachIndexed { index, title ->
                    Tab(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        text = { Text(title) }
                    )
                }
            }
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                when (selectedTab) {
                    0 -> tabConnectionItems(state, serverUrl, viewModel, context, xiaomenglingModel, state.desktopIde, state.desktopIdeList)
                    1 -> tabAiItems(state, viewModel, xiaomenglingModel)
                    2 -> tabToolsItems(state, viewModel, context, serverUrl)
                    3 -> tabGeneralItems(state, viewModel)
                }
            }
        }
    }
}

// UI 细分已拆到 SettingsScreenContent.kt，保留这里的 ViewModel 和入口屏幕，方便定位设置页主逻辑。

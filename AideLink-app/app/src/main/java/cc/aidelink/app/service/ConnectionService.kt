package cc.aidelink.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.net.wifi.WifiManager
import android.util.Log
import androidx.core.app.NotificationCompat
import cc.aidelink.app.MainActivity
import cc.aidelink.app.R
import cc.aidelink.app.data.api.BridgeApi
import cc.aidelink.app.data.api.BridgeEventClient
import cc.aidelink.app.data.repository.BridgeServerRepository
import cc.aidelink.app.data.repository.ConnectionState
import cc.aidelink.app.data.repository.ConnectionStatus
import cc.aidelink.app.data.repository.IdeConnectionManager
import cc.aidelink.app.data.repository.ServerConfigRepository
import cc.aidelink.app.data.repository.SettingsRepository
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import javax.inject.Inject

/**
 * AideLink 前台保活服务
 *
 * 职责：
 *  - 启动前台通知（必须，否则 Android 8+ 杀进程）
 *  - 持有 WakeLock 防止 Doze 模式杀连接
 *  - 接收 Wake-on-LAN 请求并发送魔术包
 *  - （后续：扩展为定期 ping + 新消息通知）
 */
@AndroidEntryPoint
class ConnectionService : Service() {

    @Inject lateinit var settings: SettingsRepository
    @Inject lateinit var bridgeApi: BridgeApi
    @Inject lateinit var ideServerRepo: ServerConfigRepository
    @Inject lateinit var ideConnectionMgr: IdeConnectionManager
    @Inject lateinit var bridgeEventClient: BridgeEventClient
    @Inject lateinit var taskNotificationHandler: TaskNotificationHandler
    @Inject lateinit var bridgeServerRepo: BridgeServerRepository

    private val binder = LocalBinder()
    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var monitorJob: Job? = null
    private var ideHealthJob: Job? = null
    private var adbPortJob: Job? = null

    /** 上次上报给 server 的 ADB 端口，用于检测变化 */
    private var lastReportedAdbPort: Int = -1

    /** 桥接服务器是否在线 */
    private var bridgeOnline: Boolean = false

    /** 上一次连接的服务器 URL，用于检测变化 */
    private var lastServerUrl: String? = null

    private var nsdManager: NsdManager? = null
    private var discoveryListener: NsdManager.DiscoveryListener? = null
    private var connectivityManager: ConnectivityManager? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    inner class LocalBinder : Binder() {
        fun getService(): ConnectionService = this@ConnectionService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        taskNotificationHandler.createChannels()
        lastServerUrl = settings.getServerUrl()
        // 立即应用已保存的 URL（覆盖 DI 的硬编码默认值），使 FRP/自定义 URL 立即生效
        bridgeApi.updateBaseUrl(lastServerUrl!!)
        // 上报设备 WiFi IP 和设备标识，供服务端更新设备别名
        scope.launch(Dispatchers.IO) {
            try {
                val wm = applicationContext.getSystemService(android.content.Context.WIFI_SERVICE) as android.net.wifi.WifiManager
                val ipInt = wm.connectionInfo.ipAddress
                if (ipInt != 0) {
                    val ip = String.format("%d.%d.%d.%d", ipInt and 0xff, ipInt shr 8 and 0xff, ipInt shr 16 and 0xff, ipInt shr 24 and 0xff)
                    bridgeApi.deviceIp = ip
                    Log.d(TAG, "Device WiFi IP: $ip")
                }
                val serial = android.provider.Settings.Secure.getString(contentResolver, android.provider.Settings.Secure.ANDROID_ID)
                if (serial.isNullOrBlank().not()) {
                    bridgeApi.deviceSerial = serial
                    Log.d(TAG, "Device serial: $serial")
                }
            } catch (_: Exception) {}
        }
        // 同步当前 URL 到桥接服务器列表，确保设置在重启后仍显示
        scope.launch {
            try {
                val servers = bridgeServerRepo.getAllServers()
                if (lastServerUrl!!.isNotBlank() && servers.none { it.url.trimEnd('/') == lastServerUrl!!.trimEnd('/') }) {
                    bridgeServerRepo.addServer(
                        name = "默认服务器",
                        url = lastServerUrl!!,
                        type = cc.aidelink.app.domain.model.BridgeServerType.CUSTOM
                    )
                }
            } catch (_: Exception) {}
        }
        startForeground(NOTIFICATION_ID, buildNotification(getString(R.string.notification_connecting, lastServerUrl!!)))
        acquireWakeLock()
        acquireWifiLock()
        registerNetworkCallback()
        startHealthMonitor()
        startIdeHealthMonitor()
        startAdbPortMonitor()
        autoConnectIdeServers()
        startNsdDiscovery()
        startBridgeEventStream()
        Log.d(TAG, "ConnectionService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "ConnectionService onStartCommand")
        // 处理 Wake-on-LAN intent
        if (intent?.action == ACTION_WAKE_ON_LAN) {
            val macAddress = intent.getStringExtra(EXTRA_MAC_ADDRESS)
            if (!macAddress.isNullOrBlank()) {
                sendWakeOnLan(macAddress)
            } else {
                Log.w(TAG, "WoL intent received but mac_address is empty")
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        unregisterNetworkCallback()
        stopNsdDiscovery()
        stopBridgeEventStream()
        monitorJob?.cancel()
        ideHealthJob?.cancel()
        adbPortJob?.cancel()
        scope.cancel()
        if (wakeLock?.isHeld == true) wakeLock?.release()
        if (wifiLock?.isHeld == true) wifiLock?.release()
        Log.d(TAG, "ConnectionService destroyed")
        super.onDestroy()
    }

    // ── Bridge Event Stream (SSE) ───────────────────────────

    /**
     * 启动桥接服务器 SSE 事件流，监听 IDE 任务完成通知
     */
    private fun startBridgeEventStream() {
        val url = settings.getServerUrl()
        Log.d(TAG, "Starting bridge event stream: $url")
        bridgeEventClient.start(url)
        taskNotificationHandler.startListening()
    }

    private fun stopBridgeEventStream() {
        bridgeEventClient.stop()
        taskNotificationHandler.stopListening()
    }

    // ── Wake-on-LAN ─────────────────────────────────────────

    fun sendWakeOnLan(macAddress: String) {
        scope.launch(Dispatchers.IO) {
            try {
                val macBytes = macAddress.replace(":", "").replace("-", "")
                    .chunked(2).map { it.toInt(16).toByte() }.toByteArray()
                if (macBytes.size != 6) {
                    Log.e(TAG, "Invalid MAC: $macAddress")
                    return@launch
                }

                val magic = ByteArray(6) { 0xFF.toByte() } + ByteArray(16 * 6) { i ->
                    macBytes[i % 6]
                }

                val broadcast = InetAddress.getByName("255.255.255.255")
                val packet = DatagramPacket(magic, magic.size, broadcast, 9)
                val socket = DatagramSocket()
                socket.broadcast = true
                socket.send(packet)
                socket.close()

                Log.d(TAG, "WoL packet sent to $macAddress")
                updateNotification(getString(R.string.notification_wake_sent))
            } catch (e: Exception) {
                Log.e(TAG, "WoL send error: ${e.message}")
            }
        }
    }

    // ── Health monitor ──────────────────────────────────────

    private fun startHealthMonitor() {
        monitorJob?.cancel()
        monitorJob = scope.launch {
            // 用 Flow 监听服务器 URL 变化，立即响应切换
            launch {
                settings.serverUrlFlow.collect { currentUrl ->
                    if (currentUrl != lastServerUrl) {
                        Log.i(TAG, "Server URL changed: $lastServerUrl -> $currentUrl, updating bridgeApi")
                        lastServerUrl = currentUrl
                        bridgeApi.updateBaseUrl(currentUrl)
                        bridgeOnline = false
                        ConnectionState.setConnecting(true)
                        updateNotification(getString(R.string.notification_connecting, currentUrl))
                        // 重启 SSE 连接
                        stopBridgeEventStream()
                        startBridgeEventStream()
                    }
                }
            }

            // 健康检查循环
            while (true) {
                runCatching { bridgeApi.ping() }
                    .onSuccess { ok ->
                        if (bridgeOnline != ok) {
                            bridgeOnline = ok
                            ConnectionState.setOnline(ok)
                            Log.d(TAG, "Bridge online status changed: $ok")
                            // 连接成功时记录网段→IP 映射
                            if (ok) {
                                try {
                                    val url = settings.getServerUrlRaw()
                                    val host = url?.substringAfter("://")?.substringBefore(":")?.substringBefore("/")
                                    if (!host.isNullOrBlank()) {
                                        cc.aidelink.app.data.repository.SubnetHistory.remember(this@ConnectionService, host)
                                    }
                                } catch (_: Exception) {}
                                // bridge 刚上线时强制上报一次 ADB 端口
                                launch(Dispatchers.IO) { reportAdbPortIfNeeded(force = true) }
                            }
                        }
                    }
                    .onFailure {
                        if (bridgeOnline) {
                            Log.d(TAG, "Bridge went offline")
                            bridgeOnline = false
                            ConnectionState.setOnline(false)
                            // 主服务器失联，尝试切换到 FRP 服务器
                            launch { tryFrpFailover() }
                        } else {
                            ConnectionState.setOnline(false)
                        }
                    }
                updateNotificationWithStatus()
                // 离线时快速探测（5s），上线后放松（30s）
                val interval = if (bridgeOnline) HEALTH_CHECK_INTERVAL_MS else HEALTH_CHECK_FAST_INTERVAL_MS
                delay(interval)
            }
        }
    }

    /**
     * 主服务器 ping 失败时，遍历已保存的服务器列表，找到 FRP 类型的服务器并切换过去。
     */
    private suspend fun tryFrpFailover() {
        try {
            val currentUrl = settings.getServerUrlRaw()
            val servers = bridgeServerRepo.getAllServers()
            val frpServer = servers.firstOrNull {
                it.serverType == cc.aidelink.app.domain.model.BridgeServerType.FRP
                    && it.url != currentUrl
            } ?: return
            Log.i(TAG, "LAN server unreachable, switching to FRP: ${frpServer.url}")
            settings.setServerUrl(frpServer.url)
            bridgeApi.updateBaseUrl(frpServer.url)
        } catch (e: Exception) {
            Log.e(TAG, "FRP failover error: ${e.message}")
        }
    }

    // ── ADB 端口监控（非 root 设备端口变化主动上报） ────────

    /**
     * 定期检测当前 ADB 端口，端口变化时主动上报给 server。
     *
     * 非 root 设备的无线调试端口是系统随机分配的 TLS 端口，会在 adbd 重启 /
     * 切换无线调试 / 设备重启时变化。仅靠用户手动刷新设置页或 server 下发命令
     * 应答来上报端口太滞后，server 持有的端口会陈旧导致托盘重连失败。
     */
    private fun startAdbPortMonitor() {
        adbPortJob?.cancel()
        adbPortJob = scope.launch(Dispatchers.IO) {
            // 启动后延迟 5 秒再首次检测，避免与 onCreate 中的其他初始化竞争
            delay(5_000)
            while (true) {
                reportAdbPortIfNeeded()
                delay(ADB_PORT_CHECK_INTERVAL_MS)
            }
        }
    }

    /**
     * 检测当前 ADB 端口，与上次上报的不同则推送给 server。
     * @param force true 时即使端口未变也强制上报（用于网络恢复/bridge 上线等场景）
     */
    private suspend fun reportAdbPortIfNeeded(force: Boolean = false) {
        try {
            val status = WirelessAdbManager.detectStatus(applicationContext)
            val port = status.adbPort
            val ip = status.deviceIp
            if (ip.isBlank() || port <= 0) return
            if (!force && port == lastReportedAdbPort) return
            val ok = bridgeApi.reportAdbStatus(ip, port, true)
            if (ok) {
                lastReportedAdbPort = port
                Log.d(TAG, "ADB port reported: $ip:$port (force=$force, root=${status.hasRoot})")
            }
        } catch (e: Exception) {
            Log.w(TAG, "ADB port report failed: ${e.message}")
        }
    }

    // ── IDE 服务器健康检查 ──────────────────────────────────

    /**
     * 定期检查 IDE 服务器健康状态
     * - 对已 CONNECTED 的服务器做健康检查，失败则断开
     * - 对 autoConnect=true 且 DISCONNECTED 的服务器尝试连接
     */
    private fun startIdeHealthMonitor() {
        ideHealthJob?.cancel()
        ideHealthJob = scope.launch {
            while (true) {
                try {
                    val servers = ideServerRepo.getServers()
                    val states = ideConnectionMgr.connectionStates.value

                    for (server in servers) {
                        val status = states[server.id]
                        when {
                            // 已连接的服务器做健康检查
                            status == ConnectionStatus.CONNECTED -> {
                                val healthy = ideConnectionMgr.healthCheck(server)
                                if (!healthy) {
                                    Log.w(TAG, "IDE health check failed for ${server.displayName}, disconnecting")
                                    ideConnectionMgr.disconnect(server.id)
                                }
                            }
                            // autoConnect 且已断开的服务器尝试连接
                            server.autoConnect && (status == null || status == ConnectionStatus.DISCONNECTED) -> {
                                Log.d(TAG, "Auto-connecting IDE server: ${server.displayName}")
                                ideConnectionMgr.connect(server.id, server)
                            }
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "IDE health monitor error: ${e.message}")
                }
                updateNotificationWithStatus()
                delay(HEALTH_CHECK_INTERVAL_MS)
            }
        }
    }

    /**
     * 服务启动时自动连接 autoConnect=true 的 IDE 服务器
     */
    private fun autoConnectIdeServers() {
        scope.launch {
            try {
                val servers = ideServerRepo.getServers()
                for (server in servers) {
                    if (server.autoConnect) {
                        Log.d(TAG, "Auto-connecting IDE server on start: ${server.displayName}")
                        ideConnectionMgr.connect(server.id, server)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Auto-connect IDE servers error: ${e.message}")
            }
        }
    }

    // ── Notification helpers ────────────────────────────────

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel_connection),
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.notification_channel_connection_desc)
                setShowBadge(false)
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(text: String): Notification {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val floatIntent = Intent(this, UiLocatorService::class.java)
        val floatPendingIntent = PendingIntent.getService(
            this, 1, floatIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("AideLink")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_notify_sync_noanim)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .addAction(
                android.R.drawable.ic_menu_compass,
                "开启悬浮窗",
                floatPendingIntent
            )
            .build()
    }

    private fun updateNotification(text: String) {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, buildNotification(text))
    }

    /**
     * 根据桥接和 IDE 服务器状态更新通知文本
     * 格式："AideLink: 桥接已连接 | 2 个 IDE 在线"
     */
    private fun updateNotificationWithStatus() {
        scope.launch(Dispatchers.IO) {
            val bridgePart = if (bridgeOnline) {
                getString(R.string.notification_bridge_connected)
            } else {
                getString(R.string.notification_bridge_disconnected)
            }
            val onlineCount = try {
                val url = java.net.URL("${settings.getServerUrl()}/ide/processes")
                val conn = url.openConnection() as java.net.HttpURLConnection
                conn.connectTimeout = 3000
                conn.readTimeout = 3000
                val body = conn.inputStream.bufferedReader().readText()
                conn.disconnect()
                val parsed = kotlinx.serialization.json.Json.parseToJsonElement(body)
                val ides = parsed.jsonObject["ides"]?.jsonArray ?: emptyList()
                ides.count {
                    it.jsonObject["running"]?.jsonPrimitive?.booleanOrNull == true
                }
            } catch (e: Exception) {
                ideConnectionMgr.connectionStates.value.count { it.value == ConnectionStatus.CONNECTED }
            }
            val idePart = getString(R.string.notification_ide_servers_online, onlineCount)
            val text = getString(R.string.notification_status_format, bridgePart, idePart)
            withContext(Dispatchers.Main) {
                updateNotification(text)
            }
        }
    }

    private fun acquireWakeLock() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "aidelink::connection_wakelock",
        ).apply { acquire() }  // 无超时，靠 onDestroy 释放
    }

    private fun acquireWifiLock() {
        val wifiManager = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        wifiLock = wifiManager.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "aidelink::wifi_lock")
        wifiLock?.acquire()
        Log.d(TAG, "WifiLock acquired (HIGH_PERF)")
    }

    private fun startNsdDiscovery() {
        try {
            nsdManager = getSystemService(Context.NSD_SERVICE) as NsdManager
            discoveryListener = object : NsdManager.DiscoveryListener {
                override fun onStartDiscoveryFailed(serviceType: String?, errorCode: Int) {
                    Log.e(TAG, "NSD Start Discovery Failed: $errorCode")
                    nsdManager?.stopServiceDiscovery(this)
                }

                override fun onStopDiscoveryFailed(serviceType: String?, errorCode: Int) {
                    Log.e(TAG, "NSD Stop Discovery Failed: $errorCode")
                    nsdManager?.stopServiceDiscovery(this)
                }

                override fun onDiscoveryStarted(serviceType: String?) {
                    Log.d(TAG, "NSD Discovery Started")
                }

                override fun onDiscoveryStopped(serviceType: String?) {
                    Log.d(TAG, "NSD Discovery Stopped")
                }

                override fun onServiceFound(serviceInfo: NsdServiceInfo?) {
                    Log.d(TAG, "NSD Service Found: ${serviceInfo?.serviceName}")
                    val type = serviceInfo?.serviceType ?: ""
                    if (type.contains("_aidelink._tcp")) {
                        nsdManager?.resolveService(serviceInfo, object : NsdManager.ResolveListener {
                            override fun onResolveFailed(serviceInfo: NsdServiceInfo?, errorCode: Int) {
                                Log.e(TAG, "NSD Resolve Failed: $errorCode")
                            }

                            override fun onServiceResolved(resolvedServiceInfo: NsdServiceInfo?) {
                                val host = resolvedServiceInfo?.host?.hostAddress
                                val port = resolvedServiceInfo?.port ?: 5000
                                if (host != null) {
                                    val newUrl = "http://$host:$port"
                                    scope.launch(Dispatchers.Main) {
                                        val currentUrl = settings.getServerUrl()
                                        if (currentUrl != newUrl) {
                                            Log.i(TAG, "NSD Auto-discovered AideLink PC at: $newUrl")
                                            settings.setServerUrl(newUrl)
                                            bridgeApi.updateBaseUrl(newUrl)
                                            lastServerUrl = newUrl  // 同步更新，避免健康检查重复触发
                                            updateNotification(getString(R.string.notification_connecting, newUrl))
                                        }
                                    }
                                }
                            }
                        })
                    }
                }

                override fun onServiceLost(serviceInfo: NsdServiceInfo?) {
                    Log.d(TAG, "NSD Service Lost: ${serviceInfo?.serviceName}")
                }
            }

            nsdManager?.discoverServices(
                "_aidelink._tcp",
                NsdManager.PROTOCOL_DNS_SD,
                discoveryListener
            )
        } catch (e: Exception) {
            Log.e(TAG, "Error starting NSD discovery: ${e.message}")
        }
    }

    private fun stopNsdDiscovery() {
        try {
            if (nsdManager != null && discoveryListener != null) {
                nsdManager?.stopServiceDiscovery(discoveryListener)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping NSD discovery: ${e.message}")
        } finally {
            nsdManager = null
            discoveryListener = null
        }
    }

    private fun registerNetworkCallback() {
        try {
            connectivityManager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            networkCallback = object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    Log.d(TAG, "Network available, trying smart reconnect")
                    scope.launch(Dispatchers.Main) {
                        stopNsdDiscovery()
                        smartReconnect()
                    }
                    // 网络恢复后强制上报 ADB 端口（IP 可能变了）
                    scope.launch(Dispatchers.IO) {
                        delay(3_000)
                        reportAdbPortIfNeeded(force = true)
                    }
                }

                override fun onLost(network: Network) {
                    Log.d(TAG, "Network lost, stopping NSD discovery")
                    scope.launch(Dispatchers.Main) {
                        stopNsdDiscovery()
                    }
                }
            }

            val request = NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build()
            connectivityManager?.registerNetworkCallback(request, networkCallback!!)
            Log.d(TAG, "Network callback registered")
        } catch (e: Exception) {
            Log.e(TAG, "Error registering network callback: ${e.message}")
        }
    }

    /**
     * 智能重连：网段匹配 → FRP → mDNS 扫描
     * 1. 检测当前网段，查找历史记录中匹配的 LAN IP
     * 2. 尝试连接该 IP（短超时 2 秒）
     * 3. 失败则尝试 FRP 服务器
     * 4. 都失败则启动 mDNS 扫描
     */
    private suspend fun smartReconnect() {
        // 1. 查找当前网段的历史 IP
        val lanIp = cc.aidelink.app.data.repository.SubnetHistory.lookupForCurrentSubnet(this)
        if (lanIp != null) {
            Log.i(TAG, "Smart reconnect: found LAN IP $lanIp for current subnet")
            val testUrl = "http://$lanIp:5000"
            val reachable = try {
                val resp = bridgeApi.ping(testUrl)
                resp
            } catch (_: Exception) { false }

            if (reachable) {
                Log.i(TAG, "Smart reconnect: LAN $testUrl reachable, switching")
                settings.setServerUrl(testUrl)
                bridgeApi.updateBaseUrl(testUrl)
                cc.aidelink.app.data.repository.SubnetHistory.remember(this, lanIp)
                return
            }
            Log.d(TAG, "Smart reconnect: LAN $testUrl unreachable")
        }

        // 2. 尝试 FRP
        try {
            val servers = bridgeServerRepo.getAllServers()
            val frpServer = servers.firstOrNull {
                it.serverType == cc.aidelink.app.domain.model.BridgeServerType.FRP
            }
            if (frpServer != null) {
                Log.i(TAG, "Smart reconnect: trying FRP ${frpServer.url}")
                val reachable = try {
                    bridgeApi.ping(frpServer.url)
                } catch (_: Exception) { false }
                if (reachable) {
                    Log.i(TAG, "Smart reconnect: FRP reachable, switching")
                    settings.setServerUrl(frpServer.url)
                    bridgeApi.updateBaseUrl(frpServer.url)
                    return
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Smart reconnect: FRP error: ${e.message}")
        }

        // 3. 回退到 mDNS 扫描
        Log.i(TAG, "Smart reconnect: falling back to NSD discovery")
        startNsdDiscovery()
    }

    private fun unregisterNetworkCallback() {
        try {
            if (connectivityManager != null && networkCallback != null) {
                connectivityManager?.unregisterNetworkCallback(networkCallback!!)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error unregistering network callback: ${e.message}")
        } finally {
            connectivityManager = null
            networkCallback = null
        }
    }

    companion object {
        private const val TAG = "ConnectionService"
        private const val CHANNEL_ID = "aidelink_connection_channel"
        private const val NOTIFICATION_ID = 1001
        private const val HEALTH_CHECK_INTERVAL_MS = 30_000L
        private const val HEALTH_CHECK_FAST_INTERVAL_MS = 5_000L
        private const val ADB_PORT_CHECK_INTERVAL_MS = 180_000L
        const val ACTION_WAKE_ON_LAN = "ACTION_WAKE_ON_LAN"
        const val EXTRA_MAC_ADDRESS = "mac_address"
    }
}

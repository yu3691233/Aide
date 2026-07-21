package cc.aidelink.app.service

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build
import android.provider.Settings
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.File
import java.net.Inet4Address
import java.net.NetworkInterface

internal fun selectAdbPort(preferClassic: Boolean, classicPort: Int, tlsPort: Int): Int {
    return if (preferClassic) {
        classicPort.takeIf { it > 0 } ?: tlsPort
    } else {
        tlsPort.takeIf { it > 0 } ?: classicPort
    }
}

object WirelessAdbManager {
    private const val TAG = "WirelessAdb"

    data class AdbStatus(
        val hasRoot: Boolean = false,
        val hasShizuku: Boolean = false,
        val wirelessAdbEnabled: Boolean = false,
        val deviceIp: String = "",
        val adbPort: Int = 0,
        val connectCommand: String = "",
        val method: Method = Method.NONE,
    )

    data class ConnectResult(
        val connectCmd: String,
        val method: String,
        val ip: String,
        val port: Int
    )

    enum class Method { ROOT, SHIZUKU, MANUAL, NONE }

    suspend fun detectStatus(context: Context): AdbStatus = withContext(Dispatchers.IO) {
        val hasRoot = checkRoot()
        val hasShizuku = false
        val ip = getDeviceIp(context)
        var port = getAdbPort(preferClassic = hasRoot)
        if (port <= 0) {
            port = discoverLocalAdbPort(context)
        }
        val wirelessEnabled = port > 0

        val method = when {
            hasRoot -> Method.ROOT
            else -> Method.MANUAL
        }

        val cmd = if (wirelessEnabled && ip.isNotBlank()) "adb connect $ip:$port" else ""

        AdbStatus(
            hasRoot = hasRoot,
            hasShizuku = hasShizuku,
            wirelessAdbEnabled = wirelessEnabled,
            deviceIp = ip,
            adbPort = port,
            connectCommand = cmd,
            method = method,
        )
    }

    suspend fun enableWirelessAdb(context: Context, serverUrl: String = ""): Result<ConnectResult> = withContext(Dispatchers.IO) {
        try {
            val ip = getDeviceIp(context)
            if (ip.isBlank()) return@withContext Result.failure(Exception("无法获取设备 IP，请检查 WiFi 连接"))

            val port = 5555

            // Root 设备始终优先固定经典 5555。不能先走 WRITE_SECURE_SETTINGS，
            // 否则系统随机 TLS 端口一旦开启成功，就永远不会执行 Root 固定端口逻辑。
            val rootGranted = requestRootPermission()
            if (rootGranted) {
                val result = execRoot("setprop service.adb.tcp.port $port && stop adbd && start adbd")
                Thread.sleep(1500)
                val classicPort = getClassicAdbPort()
                // stop/start adbd 会主动断开当前 shell，命令可能报告失败，但端口实际已经生效。
                if (result.isSuccess || classicPort == port || isPortOpen(port)) {
                    return@withContext Result.success(ConnectResult("adb connect $ip:$port", "root", ip, port))
                }
                Log.w(TAG, "Root 命令未能启用经典端口: ${result.exceptionOrNull()?.message.orEmpty()}")
            }

            // 非 Root 设备优先使用 WRITE_SECURE_SETTINGS，保留系统随机 TLS 端口。
            if (context.checkSelfPermission(android.Manifest.permission.WRITE_SECURE_SETTINGS) == android.content.pm.PackageManager.PERMISSION_GRANTED) {
                try {
                    Settings.Global.putInt(context.contentResolver, "adb_wifi_enabled", 1)
                    // 系统无线调试服务启动需要时间，轮询等待端口就绪（最长 8 秒）
                    var currentPort = 0
                    val waitDeadline = System.currentTimeMillis() + 8000
                    while (System.currentTimeMillis() < waitDeadline && currentPort <= 0) {
                        Thread.sleep(500)
                        currentPort = getAdbPort()
                        if (currentPort <= 0) {
                            currentPort = discoverLocalAdbPort(context)
                        }
                    }
                    if (currentPort > 0) {
                        return@withContext Result.success(ConnectResult("adb connect $ip:$currentPort", "secure_settings", ip, currentPort))
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "通过 WRITE_SECURE_SETTINGS 开启无线调试失败", e)
                }
            }

            try {
                val baseUrl = serverUrl.ifBlank {
                    val dataStoreFile = context.filesDir.resolve("datastore/aidelink_settings.preferences_pb")
                    if (dataStoreFile.exists()) {
                        val proto = dataStoreFile.readBytes()
                        Regex("server_url.*?value:\\s*\"([^\"]+)\"").find(String(proto))?.groupValues?.get(1)
                    } else null
                }
                if (!baseUrl.isNullOrBlank()) {
                    val url = java.net.URL("${baseUrl.trimEnd('/')}/api/adb/usb_tcpip")
                    val conn = url.openConnection() as java.net.HttpURLConnection
                    conn.requestMethod = "POST"
                    conn.setRequestProperty("Content-Type", "application/json")
                    conn.connectTimeout = 10000
                    conn.readTimeout = 10000
                    conn.doOutput = true
                    conn.outputStream.write("{}".toByteArray())
                    val code = conn.responseCode
                    val body = conn.inputStream.bufferedReader().readText()
                    conn.disconnect()
                    if (code == 200) {
                        val json = org.json.JSONObject(body)
                        if (json.optBoolean("ok", false)) {
                            Thread.sleep(2000)
                            return@withContext Result.success(ConnectResult("adb connect $ip:$port", "usb_tcpip", ip, port))
                        }
                    }
                }
            } catch (_: Exception) {}

            // 尝试本地内置 ADB 协议回环连接（免 Shizuku Fallback）
            val localAdbResult = enableViaLocalAdb(context)
            if (localAdbResult.isSuccess) {
                val cmd = localAdbResult.getOrNull()!!
                val resolvedPort = cmd.substringAfterLast(":", "5555").toIntOrNull() ?: 5555
                return@withContext Result.success(ConnectResult(cmd, "local_adblib", ip, resolvedPort))
            } else {
                val errMsg = localAdbResult.exceptionOrNull()?.message ?: ""
                if (errMsg.contains("鉴权失败") || errMsg.contains("允许调试") || errMsg.contains("允许")) {
                    return@withContext Result.failure(localAdbResult.exceptionOrNull()!!)
                }
            }

            Result.failure(Exception("开启失败：未检测到 Root，且本地无授权 ADB 连接。\n提示：你可以通过电脑执行以下命令授予权限，后续即可免 Root 一键开关：\nadb shell pm grant cc.aidelink.app android.permission.WRITE_SECURE_SETTINGS"))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun enableViaRoot(): Result<String> = withContext(Dispatchers.IO) {
        try {
            val ip = getDeviceIp(null)
            if (ip.isBlank()) return@withContext Result.failure(Exception("无法获取设备 IP"))
            val port = 5555

            // 先请求并确保获取 Root 权限（触发 Magisk 授权弹窗）
            val hasRoot = requestRootPermission()
            if (!hasRoot) {
                return@withContext Result.failure(Exception("未获得 Root 权限，请在 Magisk/超级用户中授权"))
            }

            // 方式1: libsu Shell.cmd
            try {
                val result = com.topjohnwu.superuser.Shell.cmd(
                    "setprop service.adb.tcp.port $port && stop adbd && start adbd"
                ).exec()
                if (result.isSuccess) {
                    Thread.sleep(1000)
                    return@withContext Result.success("adb connect $ip:$port")
                }
            } catch (e: Exception) {
                // 忽略异常，继续尝试方式 2
            }

            // 方式2: 传统 exec su
            try {
                val process = Runtime.getRuntime().exec("su")
                val os = java.io.DataOutputStream(process.outputStream)
                os.writeBytes("setprop service.adb.tcp.port $port\n")
                os.writeBytes("stop adbd\n")
                os.writeBytes("start adbd\n")
                os.writeBytes("exit\n")
                os.flush()
                val finished = process.waitFor(10, java.util.concurrent.TimeUnit.SECONDS)
                if (finished && process.exitValue() == 0) {
                    Thread.sleep(1000)
                    return@withContext Result.success("adb connect $ip:$port")
                }
            } catch (e: Exception) {
                return@withContext Result.failure(Exception("传统 Root 执行失败: ${e.message}"))
            }

            Result.failure(Exception("Root 命令执行失败"))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun execCommand(cmd: Array<String>): Result<String> {
        return try {
            val process = Runtime.getRuntime().exec(cmd)
            val finished = process.waitFor(10, java.util.concurrent.TimeUnit.SECONDS)
            if (finished) {
                val output = process.inputStream.bufferedReader().readText()
                val exitCode = process.exitValue()
                if (exitCode == 0) Result.success(output.trim())
                else Result.failure(Exception("exit=$exitCode"))
            } else {
                process.destroyForcibly()
                Result.failure(Exception("timeout"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * 用 libsu 打开 root shell（首次调用触发 Magisk 授权弹窗）
     */
    private suspend fun openRootShell(): Boolean = kotlinx.coroutines.suspendCancellableCoroutine { cont ->
        try {
            // 如果缓存的 shell 不是 root shell，强行将其关闭，以迫使 libsu 重新创建并触发授权弹窗
            val cached = com.topjohnwu.superuser.Shell.getCachedShell()
            if (cached != null && !cached.isRoot) {
                try {
                    cached.close()
                } catch (_: Exception) {}
            }

            // 配置 shell builder
            com.topjohnwu.superuser.Shell.setDefaultBuilder(
                com.topjohnwu.superuser.Shell.Builder.create()
                    .setTimeout(30)
            )
            // 获取 shell（异步，首次会弹 Magisk 授权）
            com.topjohnwu.superuser.Shell.getShell { shell ->
                if (shell.isRoot) {
                    cont.resume(true) {}
                } else {
                    cont.resume(false) {}
                }
            }
        } catch (e: Exception) {
            cont.resume(false) {}
        }
    }

    /**
     * 尝试触发 Magisk 授权弹窗
     */
    private suspend fun triggerMagiskGrant(): Boolean = withContext(Dispatchers.IO) {
        try {
            val process = Runtime.getRuntime().exec(arrayOf("su", "-c", "id"))
            val finished = process.waitFor(15, java.util.concurrent.TimeUnit.SECONDS)
            if (finished) {
                val output = process.inputStream.bufferedReader().readText()
                output.contains("uid=0")
            } else {
                process.destroyForcibly()
                false
            }
        } catch (_: Exception) {
            false
        }
    }

    suspend fun disableWirelessAdb(context: Context): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val rootGranted = requestRootPermission()
            if (rootGranted) {
                // 先关 adb_wifi_enabled（系统无线调试开关）
                com.topjohnwu.superuser.Shell.cmd(
                    "settings put global adb_wifi_enabled 0"
                ).exec()
                // 清空 TCP 端口属性，让 adbd 回退到 USB 模式
                com.topjohnwu.superuser.Shell.cmd(
                    "resetprop service.adb.tcp.port ''"
                ).exec()
                // 兜底：setprop（非 Magisk 设备）
                com.topjohnwu.superuser.Shell.cmd(
                    "setprop service.adb.tcp.port ''"
                ).exec()
                // 重启 adbd 使属性生效
                com.topjohnwu.superuser.Shell.cmd("stop adbd").exec()
                Thread.sleep(800)
                com.topjohnwu.superuser.Shell.cmd("start adbd").exec()
                Thread.sleep(500)
                return@withContext Result.success(Unit)
            }

            // 无 Root 时尝试 WRITE_SECURE_SETTINGS
            if (context.checkSelfPermission(android.Manifest.permission.WRITE_SECURE_SETTINGS) == android.content.pm.PackageManager.PERMISSION_GRANTED) {
                try {
                    Settings.Global.putInt(context.contentResolver, "adb_wifi_enabled", 0)
                    return@withContext Result.success(Unit)
                } catch (e: Exception) {
                    Log.e(TAG, "通过 WRITE_SECURE_SETTINGS 关闭无线调试失败", e)
                }
            }

            // 免 Shizuku: 尝试使用本地内置 ADB 协议关闭无线调试
            var port = getAdbPort()
            if (port <= 0) {
                port = discoverLocalAdbPort(context)
            }
            if (port > 0) {
                val result = executeLocalAdbCommand(context, port, "settings put global adb_wifi_enabled 0")
                if (result.isSuccess) {
                    Result.success(Unit)
                } else {
                    Result.failure(Exception("本地 ADB 关闭失败: ${result.exceptionOrNull()?.message}"))
                }
            } else {
                Result.failure(Exception("未检测到 Root 且本地无活跃无线调试端口。请在开发者选项中手动关闭无线调试"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }



    /**
     * 请求 Root 权限（触发 Magisk/SuperSU 弹窗）
     * 多种方式尝试，确保触发授权对话框
     */
    suspend fun requestRootPermissionPublic(): Result<Unit> = withContext(Dispatchers.IO) {
        Log.i(TAG, "开始主动请求 Root 权限...")
        
        // 1. 尝试 libsu
        try {
            Log.i(TAG, "尝试通过 libsu 获取 Root Shell...")
            val libsuSuccess = openRootShell()
            Log.i(TAG, "libsu 获取 Root Shell 结果: $libsuSuccess")
            if (libsuSuccess) {
                return@withContext Result.success(Unit)
            }
        } catch (e: Exception) {
            Log.w(TAG, "libsu 异常: ${e.message}", e)
        }

        // 2. 尝试传统 su (遍历可能的绝对路径)
        val suPaths = listOf("su", "/product/bin/su", "/system/bin/su", "/system/xbin/su", "/sbin/su")
        var lastError: Exception? = null
        for (suPath in suPaths) {
            try {
                Log.i(TAG, "尝试执行传统 '$suPath' 命令...")
                val process = Runtime.getRuntime().exec(arrayOf(suPath))
                val os = java.io.DataOutputStream(process.outputStream)
                os.writeBytes("id\n")
                os.writeBytes("exit\n")
                os.flush()
                val finished = process.waitFor(10, java.util.concurrent.TimeUnit.SECONDS)
                if (finished) {
                    val exitCode = process.exitValue()
                    val output = process.inputStream.bufferedReader().readText().trim()
                    val errorOutput = process.errorStream.bufferedReader().readText().trim()
                    Log.i(TAG, "'$suPath' 执行完成: exitCode=$exitCode, stdout='$output', stderr='$errorOutput'")
                    if (output.contains("uid=0") || exitCode == 0) {
                        return@withContext Result.success(Unit)
                    }
                } else {
                    process.destroyForcibly()
                    Log.w(TAG, "'$suPath' 执行超时")
                }
            } catch (e: Exception) {
                Log.w(TAG, "通过 '$suPath' 获取 Root 失败: ${e.message}")
                lastError = e
            }
        }
        return@withContext Result.failure(lastError ?: Exception("未找到可用的 su 路径或全部执行失败"))
    }

    private suspend fun requestRootPermission(): Boolean {
        return requestRootPermissionPublic().isSuccess
    }

    private fun checkRoot(): Boolean {
        // 使用 libsu 进行静默/被动检查，避免调用 su 引起频繁的 Magisk 授权弹窗干扰/超时被杀
        return com.topjohnwu.superuser.Shell.isAppGrantedRoot() == true
    }



    private fun execRoot(command: String): Result<String> {
        val suPaths = listOf("su", "/product/bin/su", "/system/bin/su", "/system/xbin/su", "/sbin/su")
        for (suPath in suPaths) {
            try {
                // 方式1: su -c
                try {
                    val process = Runtime.getRuntime().exec(arrayOf(suPath, "-c", command))
                    val finished = process.waitFor(8, java.util.concurrent.TimeUnit.SECONDS)
                    if (finished) {
                        val output = process.inputStream.bufferedReader().readText()
                        val exitCode = process.exitValue()
                        if (exitCode == 0) return Result.success(output.trim())
                    } else {
                        process.destroyForcibly()
                    }
                } catch (_: Exception) {}

                // 方式2: 交互式 su shell（写 stdin）
                try {
                    val process = Runtime.getRuntime().exec(suPath)
                    val os = java.io.DataOutputStream(process.outputStream)
                    os.writeBytes("$command\n")
                    os.writeBytes("echo EXIT_CODE=$?\n")
                    os.writeBytes("exit\n")
                    os.flush()
                    val finished = process.waitFor(8, java.util.concurrent.TimeUnit.SECONDS)
                    if (finished) {
                        val output = process.inputStream.bufferedReader().readText()
                        if (output.contains("EXIT_CODE=0") || output.contains("uid=0")) {
                            return Result.success(output.lines().filter { !it.contains("EXIT_CODE=") }.joinToString("\n").trim())
                        }
                    } else {
                        process.destroyForcibly()
                    }
                } catch (_: Exception) {}
            } catch (_: Exception) { continue }
        }
        return Result.failure(Exception("所有 su 路径均失败"))
    }



    private fun isPortOpen(port: Int): Boolean {
        if (port <= 0) return false
        return try {
            java.net.Socket().use { socket ->
                socket.connect(java.net.InetSocketAddress("127.0.0.1", port), 500)
                true
            }
        } catch (_: Exception) {
            false
        }
    }

    private fun getTlsAdbPort(): Int {
        try {
            val process = Runtime.getRuntime().exec(arrayOf("getprop", "service.adb.tls.port"))
            val port = process.inputStream.bufferedReader().readText().trim().toIntOrNull() ?: 0
            process.waitFor()
            if (port > 0 && isPortOpen(port)) return port
        } catch (_: Exception) {}
        return 0
    }

    suspend fun captureRootScreenshot(context: Context): ByteArray? = withContext(Dispatchers.IO) {
        if (!checkRoot()) return@withContext null
        val file = context.cacheDir.resolve("root_screen.png")
        try {
            file.delete()
            val result = com.topjohnwu.superuser.Shell.cmd("screencap -p ${file.absolutePath}").exec()
            if (result.isSuccess && file.exists()) file.readBytes() else null
        } catch (e: Exception) {
            Log.w(TAG, "Root 截图失败: ${e.message}")
            null
        } finally {
            file.delete()
        }
    }

    suspend fun grantOverlayPermissionAsRoot(): Boolean = withContext(Dispatchers.IO) {
        if (!checkRoot()) return@withContext false
        try {
            com.topjohnwu.superuser.Shell.cmd(
                "appops set cc.aidelink.app android:system_alert_window allow"
            ).exec().isSuccess
        } catch (_: Exception) {
            false
        }
    }

    suspend fun grantOverlayPermissionViaLocalAdb(context: Context, port: Int): Boolean {
        return executeLocalAdbCommand(
            context,
            port,
            "appops set cc.aidelink.app android:system_alert_window allow",
        ).isSuccess
    }

    private fun getClassicAdbPort(): Int {
        try {
            val process = Runtime.getRuntime().exec(arrayOf("getprop", "service.adb.tcp.port"))
            val port = process.inputStream.bufferedReader().readText().trim().toIntOrNull() ?: 0
            process.waitFor()
            if (port > 0 && isPortOpen(port)) return port
        } catch (_: Exception) {}
        return 0
    }

    private fun getAdbPort(preferClassic: Boolean = false): Int {
        val classicPort = getClassicAdbPort()
        val tlsPort = getTlsAdbPort()
        return selectAdbPort(preferClassic, classicPort, tlsPort)
    }

    /**
     * 通过局域网 mDNS (NDS) 服务发现，在 3 秒内主动搜寻本机的无线调试服务端口 (AOSP 标准服务类型 _adb-tls-connect._tcp)
     */
    private suspend fun discoverLocalAdbPort(context: Context): Int = kotlinx.coroutines.suspendCancellableCoroutine { cont ->
        val nsdManager = context.getSystemService(Context.NSD_SERVICE) as? android.net.nsd.NsdManager
        if (nsdManager == null) {
            cont.resume(0) {}
            return@suspendCancellableCoroutine
        }

        var resolved = false
        lateinit var discoveryListener: android.net.nsd.NsdManager.DiscoveryListener
        discoveryListener = object : android.net.nsd.NsdManager.DiscoveryListener {
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                if (!resolved) {
                    resolved = true
                    nsdManager.stopServiceDiscovery(this)
                    cont.resume(0) {}
                }
            }

            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}

            override fun onDiscoveryStarted(serviceType: String) {}

            override fun onDiscoveryStopped(serviceType: String) {}

            override fun onServiceFound(serviceInfo: android.net.nsd.NsdServiceInfo) {
                if (serviceInfo.serviceType.contains("_adb-tls-connect")) {
                    nsdManager.resolveService(serviceInfo, object : android.net.nsd.NsdManager.ResolveListener {
                        override fun onResolveFailed(serviceInfo: android.net.nsd.NsdServiceInfo, errorCode: Int) {
                            if (!resolved) {
                                resolved = true
                                try {
                                    nsdManager.stopServiceDiscovery(discoveryListener)
                                } catch (_: Exception) {}
                                cont.resume(0) {}
                            }
                        }

                        override fun onServiceResolved(resolvedServiceInfo: android.net.nsd.NsdServiceInfo) {
                            if (!resolved) {
                                val port = resolvedServiceInfo.port
                                if (isPortOpen(port)) {
                                    resolved = true
                                    try {
                                        nsdManager.stopServiceDiscovery(discoveryListener)
                                    } catch (_: Exception) {}
                                    cont.resume(port) {}
                                }
                            }
                        }
                    })
                }
            }

            override fun onServiceLost(serviceInfo: android.net.nsd.NsdServiceInfo) {}
        }

        nsdManager.discoverServices("_adb-tls-connect._tcp", android.net.nsd.NsdManager.PROTOCOL_DNS_SD, discoveryListener)

        // 3秒无应答超时退出
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
            if (!resolved) {
                resolved = true
                try {
                    nsdManager.stopServiceDiscovery(discoveryListener)
                } catch (_: Exception) {}
                cont.resume(0) {}
            }
        }, 3000)
    }

    private fun getDeviceIp(context: Context?): String {
        // 优先从 WiFi 获取
        if (context != null) {
            try {
                val wm = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
                val ip = wm.connectionInfo.ipAddress
                if (ip != 0) {
                    return String.format("%d.%d.%d.%d", ip and 0xff, ip shr 8 and 0xff, ip shr 16 and 0xff, ip shr 24 and 0xff)
                }
            } catch (_: Exception) {}
        }

        // 回退：遍历网络接口
        try {
            for (intf in NetworkInterface.getNetworkInterfaces()) {
                for (addr in intf.inetAddresses) {
                    if (!addr.isLoopbackAddress && addr is Inet4Address) {
                        return addr.hostAddress ?: ""
                    }
                }
            }
        } catch (_: Exception) {}

        return ""
    }

    suspend fun enableViaLocalAdb(context: Context): Result<String> = withContext(Dispatchers.IO) {
        try {
            val ip = getDeviceIp(context)
            if (ip.isBlank()) return@withContext Result.failure(Exception("无法获取设备 IP，请检查 WiFi 连接"))
            
            var port = getAdbPort()
            if (port <= 0) {
                port = discoverLocalAdbPort(context)
            }
            if (port <= 0) {
                return@withContext Result.failure(Exception("未检测到已启用的无线调试端口。请确保在系统“开发者选项”中已开启“无线调试”"))
            }

            // 尝试直接使用内置 ADB 客户端连接本地回环端口，并尝试开启维持无线调试的设置
            val res = executeLocalAdbCommand(context, port, "settings put global adb_wifi_enabled 1")
            if (res.isSuccess) {
                Result.success("adb connect $ip:$port")
            } else {
                val err = res.exceptionOrNull()?.message ?: ""
                if (err.contains("Connection refused") || err.contains("Timeout")) {
                    Result.failure(Exception("本地连接被拒绝，请确认系统已开启无线调试且端口匹配。"))
                } else {
                    Result.failure(Exception("本地 ADB 鉴权失败，请在弹出的系统“允许调试”窗口中点击“允许/始终允许”后重试。\n错误信息: $err"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun executeLocalAdbCommand(context: Context, port: Int, shellCommand: String): Result<String> = withContext(Dispatchers.IO) {
        var socket: java.net.Socket? = null
        var adbConn: com.cgutman.adblib.AdbConnection? = null
        try {
            val keyDir = File(context.filesDir, "adb_keys")
            if (!keyDir.exists()) keyDir.mkdirs()
            val privKey = File(keyDir, "adbkey")
            val pubKey = File(keyDir, "adbkey.pub")
            
            val base64 = object : com.cgutman.adblib.AdbBase64 {
                override fun encodeToString(b: ByteArray): String {
                    return android.util.Base64.encodeToString(b, android.util.Base64.NO_WRAP)
                }
            }
            
            val crypto = if (privKey.exists() && pubKey.exists()) {
                try {
                    com.cgutman.adblib.AdbCrypto.loadAdbKeyPair(base64, privKey, pubKey)
                } catch (e: Exception) {
                    privKey.delete()
                    pubKey.delete()
                    val c = com.cgutman.adblib.AdbCrypto.generateAdbKeyPair(base64)
                    c.saveAdbKeyPair(privKey, pubKey)
                    c
                }
            } else {
                val c = com.cgutman.adblib.AdbCrypto.generateAdbKeyPair(base64)
                c.saveAdbKeyPair(privKey, pubKey)
                c
            }
            
            socket = java.net.Socket("127.0.0.1", port)
            socket.soTimeout = 10000
            adbConn = com.cgutman.adblib.AdbConnection.create(socket, crypto)
            
            adbConn.connect()
            
            val stream = adbConn.open("shell:$shellCommand")
            val output = StringBuilder()
            
            while (!stream.isClosed) {
                try {
                    val data = stream.read()
                    if (data != null && data.isNotEmpty()) {
                        output.append(String(data))
                    }
                } catch (e: Exception) {
                    break
                }
            }
            
            try { stream.close() } catch (_: Exception) {}
            Result.success(output.toString().trim())
        } catch (e: Exception) {
            Log.e(TAG, "Local ADB Connection failed: ${e.message}", e)
            Result.failure(e)
        } finally {
            try { adbConn?.close() } catch (_: Exception) {}
            try { socket?.close() } catch (_: Exception) {}
        }
    }
}

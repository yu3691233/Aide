package cc.aidelink.app.data.repository

import android.content.Context
import android.content.SharedPreferences
import android.net.wifi.WifiManager
import java.net.Inet4Address
import java.net.NetworkInterface

/**
 * 网段历史记录：记住每个 WiFi 网段对应的服务器 IP
 * 例如：192.168.3 网段 → 192.168.3.50，192.168.1 网段 → 192.168.1.37
 */
object SubnetHistory {
    private const val PREFS_NAME = "subnet_history"
    private const val KEY_PREFIX = "subnet_"  // subnet_192.168.3 → 192.168.3.50

    private fun getPrefs(context: Context): SharedPreferences {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    /**
     * 记录成功的连接：将当前网段前缀映射到服务器 IP
     */
    fun remember(context: Context, serverIp: String) {
        val subnet = getSubnetPrefix(serverIp) ?: return
        getPrefs(context).edit().putString(KEY_PREFIX + subnet, serverIp).apply()
    }

    /**
     * 查询当前网段下曾经成功连接的服务器 IP
     */
    fun lookupForCurrentSubnet(context: Context): String? {
        val currentSubnet = getCurrentSubnetPrefix(context) ?: return null
        return getPrefs(context).getString(KEY_PREFIX + currentSubnet, null)
    }

    /**
     * 获取所有历史记录（用于显示/调试）
     */
    fun getAll(context: Context): Map<String, String> {
        val prefs = getPrefs(context)
        return prefs.all
            .filterKeys { it.startsWith(KEY_PREFIX) }
            .mapKeys { it.key.removePrefix(KEY_PREFIX) }
            .filterValues { it is String }
            .mapValues { it.value as String }
    }

    /**
     * 获取当前设备的网段前缀（如 "192.168.1"）
     */
    fun getCurrentSubnetPrefix(context: Context): String? {
        val ip = getDeviceIp(context) ?: return null
        return getSubnetPrefix(ip)
    }

    private fun getSubnetPrefix(ip: String): String? {
        val parts = ip.split(".")
        return if (parts.size == 4) "${parts[0]}.${parts[1]}.${parts[2]}" else null
    }

    private fun getDeviceIp(context: Context): String? {
        try {
            val wm = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            val ip = wm.connectionInfo.ipAddress
            if (ip != 0) {
                return String.format("%d.%d.%d.%d",
                    ip and 0xff, ip shr 8 and 0xff, ip shr 16 and 0xff, ip shr 24 and 0xff)
            }
        } catch (_: Exception) {}

        try {
            for (intf in NetworkInterface.getNetworkInterfaces()) {
                for (addr in intf.inetAddresses) {
                    if (!addr.isLoopbackAddress && addr is Inet4Address) {
                        return addr.hostAddress
                    }
                }
            }
        } catch (_: Exception) {}

        return null
    }
}

package cc.aidelink.app.domain.model

import kotlinx.serialization.Serializable

/**
 * 桥接服务器配置 - 支持多个服务器（局域网/FRP等）
 */
@Serializable
data class BridgeServerConfig(
    val id: String,
    val name: String,
    val url: String,
    val serverType: BridgeServerType = BridgeServerType.LOCAL,
    val autoConnect: Boolean = false,
    val lastConnected: Long? = null
)

/**
 * 桥接服务器类型
 */
@Serializable
enum class BridgeServerType {
    LOCAL,      // 局域网直连
    FRP,        // FRP内网穿透
    CUSTOM      // 自定义
}

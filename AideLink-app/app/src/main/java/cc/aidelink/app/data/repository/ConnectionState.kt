package cc.aidelink.app.data.repository

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * 全局桥接服务器连接状态，供 UI 层（输入框边框颜色等）观察。
 * ConnectionService 在健康检查循环中写入，ChatViewModel / SettingsViewModel 等读取。
 */
object ConnectionState {
    private val _bridgeOnline = MutableStateFlow(false)
    val bridgeOnline: StateFlow<Boolean> = _bridgeOnline.asStateFlow()

    /** 正在连接中（首次 ping 前的过渡状态） */
    private val _connecting = MutableStateFlow(true)
    val connecting: StateFlow<Boolean> = _connecting.asStateFlow()

    fun setOnline(online: Boolean) {
        _connecting.value = false
        _bridgeOnline.value = online
    }

    fun setConnecting(connecting: Boolean) {
        _connecting.value = connecting
    }
}

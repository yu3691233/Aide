package cc.aidelink.app.ui.screens.chat

import cc.aidelink.app.domain.model.bridge.MonitorInfo
import cc.aidelink.app.domain.model.bridge.WindowInfo

internal fun monitorContainingWindow(window: WindowInfo?, monitors: List<MonitorInfo>): String? {
    if (window == null) return null
    val centerX = (window.left + window.right) / 2
    val centerY = (window.top + window.bottom) / 2
    return monitors.firstOrNull { monitor ->
        centerX >= monitor.left && centerX < monitor.right &&
            centerY >= monitor.top && centerY < monitor.bottom
    }?.name
}

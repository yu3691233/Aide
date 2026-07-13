package cc.aidelink.app.ui.screens.chat

import cc.aidelink.app.domain.model.bridge.MonitorInfo
import cc.aidelink.app.domain.model.bridge.WindowInfo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MonitorIdentityUtilsTest {
    private val monitors = listOf(
        MonitorInfo("left", -1920, 0, 0, 1080, 1920, 1080, false),
        MonitorInfo("primary", 0, 0, 1920, 1080, 1920, 1080, true),
    )

    @Test
    fun detectsMonitorAfterWindowMoves() {
        val moved = WindowInfo(left = -1800, top = 100, right = -800, bottom = 900)
        assertEquals("left", monitorContainingWindow(moved, monitors))
    }

    @Test
    fun returnsNullWhenWindowIsOutsideKnownMonitors() {
        val unknown = WindowInfo(left = 3000, top = 0, right = 3500, bottom = 500)
        assertNull(monitorContainingWindow(unknown, monitors))
    }
}

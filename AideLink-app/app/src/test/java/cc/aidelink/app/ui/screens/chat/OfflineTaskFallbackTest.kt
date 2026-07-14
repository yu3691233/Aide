package cc.aidelink.app.ui.screens.chat

import cc.aidelink.app.ui.screens.chat.components.taskStatusMatchesTab
import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OfflineTaskFallbackTest {
    @Test
    fun cachesImmediatelyWhenBridgeIsOffline() {
        assertTrue(shouldFallbackToOfflineTaskCache(bridgeOnline = false, serverTaskCreated = false))
    }

    @Test
    fun cachesWhenHealthStateIsOnlineButCreateRequestFails() {
        assertTrue(shouldFallbackToOfflineTaskCache(bridgeOnline = true, serverTaskCreated = false))
    }

    @Test
    fun skipsCacheAfterServerCreatesTask() {
        assertFalse(shouldFallbackToOfflineTaskCache(bridgeOnline = true, serverTaskCreated = true))
    }

    @Test
    fun storesAideOfflineTaskWithoutDispatchTarget() {
        assertEquals("", normalizeTaskTarget("aide"))
        assertEquals("codex", normalizeTaskTarget("codex"))
    }

    @Test
    fun separatesOfflineTasksFromActiveTab() {
        assertTrue(taskStatusMatchesTab("pending_upload", 3))
        assertTrue(taskStatusMatchesTab("draft", 3))
        assertFalse(taskStatusMatchesTab("pending_upload", 0))
        assertFalse(taskStatusMatchesTab("draft", 0))
        assertTrue(taskStatusMatchesTab("queued", 0))
        assertFalse(taskStatusMatchesTab("failed", 2))
        assertTrue(taskStatusMatchesTab("done", 2))
    }

    @Test
    fun successfulDispatchAlwaysMovesToActiveTab() {
        assertEquals(0, taskTabAfterDispatch(currentTab = 3, success = true))
        assertEquals(0, taskTabAfterDispatch(currentTab = 2, success = true))
        assertEquals(3, taskTabAfterDispatch(currentTab = 3, success = false))
    }
}

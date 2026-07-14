package cc.aidelink.app.ui.screens.chat

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
}

package cc.aidelink.app.ui.screens.chat

import cc.aidelink.app.ui.screens.chat.components.taskStatusMatchesTab
import cc.aidelink.app.ui.screens.chat.components.filterTasksForIde
import cc.aidelink.app.ui.screens.chat.components.projectNameFromPath
import cc.aidelink.app.domain.model.bridge.AideTask
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
    fun separatesPendingRunningCompletedAndNotesTabs() {
        assertTrue(taskStatusMatchesTab("draft", 0))
        assertTrue(taskStatusMatchesTab("pending_dispatch", 0))
        assertTrue(taskStatusMatchesTab("queued", 1))
        assertTrue(taskStatusMatchesTab("pending_test", 1))
        assertFalse(taskStatusMatchesTab("failed", 2))
        assertTrue(taskStatusMatchesTab("done", 2))
        assertTrue(taskStatusMatchesTab("draft", 3, "inspiration"))
        assertFalse(taskStatusMatchesTab("draft", 0, "inspiration"))
    }

    @Test
    fun successfulDispatchAlwaysMovesToActiveTab() {
        assertEquals(1, taskTabAfterDispatch(currentTab = 3, success = true))
        assertEquals(1, taskTabAfterDispatch(currentTab = 2, success = true))
        assertEquals(3, taskTabAfterDispatch(currentTab = 3, success = false))
    }

    @Test
    fun currentIdeFilterKeepsIdeasAndAllShowsEveryIde() {
        val tasks = listOf(
            AideTask(task_id = "agy", text = "a", target_ide = "antigravity_ide", status = "queued"),
            AideTask(task_id = "trae", text = "b", target_ide = "trae", status = "queued"),
            AideTask(task_id = "idea", text = "c", target_ide = null, status = "draft", task_type = "inspiration"),
        )

        assertEquals(listOf("agy", "idea"), filterTasksForIde(tasks, "antigravity_ide", true).map { it.task_id })
        assertEquals(listOf("agy", "trae", "idea"), filterTasksForIde(tasks, "antigravity_ide", false).map { it.task_id })
    }

    @Test
    fun taskCardUsesProjectFolderAsTitle() {
        assertEquals("aide", projectNameFromPath("F:\\aide"))
        assertEquals("demo", projectNameFromPath("/workspace/demo/"))
        assertEquals("", projectNameFromPath(null))
    }
}

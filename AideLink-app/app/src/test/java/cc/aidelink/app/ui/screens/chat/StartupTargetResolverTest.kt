package cc.aidelink.app.ui.screens.chat

import cc.aidelink.app.domain.model.bridge.DesktopIde
import org.junit.Assert.assertEquals
import org.junit.Test


class StartupTargetResolverTest {
    private val selected = setOf("oc", "codex")

    @Test
    fun selectsTheOnlyRunningDesktopIdeBeforeInitialRender() {
        val processes = listOf(
            DesktopIde(key = "oc", running = false),
            DesktopIde(key = "codex", running = true),
        )

        assertEquals("codex", resolveStartupTargetKey("oc", processes, selected))
    }

    @Test
    fun preservesSavedTargetWhenMultipleIdesAreRunning() {
        val processes = listOf(
            DesktopIde(key = "oc", running = true),
            DesktopIde(key = "codex", running = true),
        )

        assertEquals("oc", resolveStartupTargetKey("oc", processes, selected))
    }

    @Test
    fun selectsRunningPrimaryIdeWhenMultipleIdesAreRunning() {
        val processes = listOf(
            DesktopIde(key = "oc", running = true),
            DesktopIde(key = "codex", running = true, is_primary = true),
        )

        assertEquals("codex", resolveStartupTargetKey("oc", processes, selected))
    }

    @Test
    fun ignoresPrimaryIdeWhenItIsNotRunning() {
        val processes = listOf(
            DesktopIde(key = "oc", running = true),
            DesktopIde(key = "codex", running = false, is_primary = true),
        )

        assertEquals("oc", resolveStartupTargetKey("codex", processes, selected))
    }

    @Test
    fun preservesSavedTargetWhenProcessLookupFails() {
        assertEquals("codex", resolveStartupTargetKey("codex", null, selected))
    }

    @Test
    fun preservesSavedTargetWhenNoIdeIsRunning() {
        val processes = listOf(
            DesktopIde(key = "oc", running = false),
            DesktopIde(key = "codex", running = false),
        )

        assertEquals("codex", resolveStartupTargetKey("codex", processes, selected))
    }

    @Test
    fun fallsBackToAideWhenNoDesktopIdeIsSelected() {
        val processes = listOf(DesktopIde(key = "codex", running = true))

        assertEquals("aide", resolveStartupTargetKey("oc", processes, emptySet()))
    }

    @Test
    fun ignoresRunningIdeThatUserDidNotSelect() {
        val processes = listOf(DesktopIde(key = "oc", running = true))

        assertEquals("codex", resolveStartupTargetKey("codex", processes, setOf("codex")))
    }
}

package cc.aidelink.app.ui.screens.sessions

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test


class SessionProjectPathTest {
    @Test
    fun windowsPathsCanNavigateAboveUserHomeToDriveRoot() {
        assertEquals("F:\\projects", parentFilesystemPath("F:\\projects\\demo"))
        assertEquals("F:\\", parentFilesystemPath("F:\\projects"))
        assertNull(parentFilesystemPath("F:\\"))
    }

    @Test
    fun searchResultsResolveAgainstCurrentDrive() {
        assertEquals(
            "F:\\projects\\demo",
            resolveFilesystemSearchPath("F:\\projects", "demo"),
        )
        assertEquals(
            "F:\\other\\demo",
            resolveFilesystemSearchPath("F:\\projects", "F:\\other\\demo"),
        )
    }
}

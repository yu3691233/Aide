package cc.aidelink.app.ui.screens.sessions

import org.junit.Assert.assertEquals
import org.junit.Test


class OpenCodeWebUrlTest {
    @Test
    fun buildsOfficialSessionRouteFromProjectDirectory() {
        assertEquals(
            "http://192.168.1.2:4096/RjpcYWlkZQ/session/ses_123",
            buildOpenCodeWebSessionUrl("http://192.168.1.2:4096/", "F:\\aide", "ses_123"),
        )
    }
}

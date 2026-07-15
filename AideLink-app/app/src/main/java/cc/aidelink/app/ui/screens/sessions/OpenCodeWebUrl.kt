package cc.aidelink.app.ui.screens.sessions

import java.net.URLEncoder
import java.util.Base64


internal fun buildOpenCodeWebSessionUrl(baseUrl: String, directory: String, sessionId: String): String {
    val encodedDirectory = Base64.getEncoder()
        .withoutPadding()
        .encodeToString(directory.toByteArray(Charsets.UTF_8))
    val encodedSession = URLEncoder.encode(sessionId, Charsets.UTF_8.name())
    return "${baseUrl.trimEnd('/')}/$encodedDirectory/session/$encodedSession"
}

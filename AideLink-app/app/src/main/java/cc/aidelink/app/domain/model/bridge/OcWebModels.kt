package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class OcWebStatus(
    val ok: Boolean = false,
    val running: Boolean = false,
    val port: Int = 4096,
    val pid: Int? = null,
)

@Serializable
data class OcWebActionResult(
    val ok: Boolean = false,
    val message: String? = null,
    val error: String? = null,
    val pid: Int? = null,
    val port: Int? = null,
)

@Serializable
data class OcWebLatestReply(
    val ok: Boolean = false,
    val reply: OcWebReplyData? = null,
    val error: String? = null,
)

@Serializable
data class OcWebReplyData(
    val session_id: String = "",
    val session_title: String = "",
    val text: String = "",
    val length: Int = 0,
)

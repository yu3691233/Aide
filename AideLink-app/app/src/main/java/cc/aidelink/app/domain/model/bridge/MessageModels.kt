package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class ChatMessage(
    val sender: String = "user",
    val text: String = "",
    val time: String = "",
    val msg_id: String? = null,
    val image: String? = null,
    val image_path: String? = null,
    val target: String? = null,
    val task_id: String? = null,
)

@Serializable
data class SendRequest(
    val text: String,
    val target: String = "auto",
    val image: String? = null,
    val task_id: String? = null,
)

@Serializable
data class SendResponse(
    val ok: Boolean = false,
    val raw: String = "",
    val routed_to: String? = null,
    val task_id: String? = null,
)

@Serializable
data class ClipboardItem(
    val text: String = "",
    val time: String = "",
    val source: String = "",
)

@Serializable
data class ClipboardAppendRequest(val text: String)

@Serializable
data class UploadResponse(
    val ok: Boolean = false,
    val raw: String = "",
    val path: String? = null,
    val url: String? = null,
)

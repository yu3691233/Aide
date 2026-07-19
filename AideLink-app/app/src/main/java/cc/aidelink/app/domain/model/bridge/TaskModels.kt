package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class AideTask(
    val task_id: String,
    val title: String? = null,
    val text: String = "",
    val status: String = "draft",
    val target_ide: String? = null,
    val project: String? = null,
    val priority: String? = "medium",
    val source: String? = null,
    val task_origin: String? = null,
    val task_origin_label: String? = null,
    val task_type: String? = null,
    val error: String? = null,
    val summary: String? = null,
    val result: String? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
    val queued_at: String? = null,
    val started_at: String? = null,
    val completed_at: String? = null,
    val app_version: String? = null,
    val git_version: String? = null,
    val device_label: String? = null,
    val feedbacks: List<TaskFeedback>? = null,
    val image: String? = null,
    val parsed_fields: ParsedTaskFields? = null,
)

@Serializable
data class ParsedTaskFields(
    val contact_phone: String = "",
    val detailed_address: String = "",
    val customer_name: String = "",
    val fault_type: String = "",
)

@Serializable
data class TaskFeedback(
    val time: String? = null,
    val text: String = "",
)

@Serializable
data class AideLinkSubmitRequest(
    val message: String,
    val task_type: String = "code",
    val async: Boolean = false,
)

@Serializable
data class AideLinkTaskResponse(
    val ok: Boolean = false,
    val raw: String = "",
    val task_id: String? = null,
    val success: Boolean? = null,
    val model_used: String? = null,
    val response: String? = null,
)

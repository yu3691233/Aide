package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class AppVersionResponse(
    val ok: Boolean = false,
    val versionCode: Int = 0,
    val versionName: String = "0.0.0",
    val error: String? = null
)

@Serializable
data class AdbInstallResponse(
    val ok: Boolean = false,
    val message: String? = null,
    val error: String? = null
)

@Serializable
data class PromptCandidate(
    val prompt: String,
    val effect: String = "",
    val reason: String = "",
)

@Serializable
data class PromptPredictResponse(
    val success: Boolean = false,
    val candidates: List<PromptCandidate> = emptyList(),
    val message: String? = null,
)

@Serializable
data class PromptComposeCandidate(
    val title: String = "",
    val understanding: String = "",
    val prompt: String = "",
)

@Serializable
data class PromptComposeResponse(
    val ok: Boolean = false,
    val used_ai: Boolean = false,
    val task_type: String = "feature_change",
    val task_type_label: String = "功能调整",
    val difficulty: String = "simple",
    val difficulty_label: String = "简单",
    val component_name: String = "",
    val component_location: String = "",
    val image_used: Boolean = false,
    val title: String = "",
    val prompt: String = "",
    val candidates: List<PromptComposeCandidate> = emptyList(),
    val message: String? = null,
)

@Serializable
data class ActiveModelsResponse(
    val models: List<ActiveModel> = emptyList(),
)

@Serializable
data class ActiveModel(
    val key: String = "",
    val description: String = "",
)

@Serializable
data class CodexQuota(
    val available: Boolean = false,
    val remaining_percent: Int? = null,
    val period: String? = null,
    val plan_type: String? = null,
    val reset_at: String? = null,
    val window_seconds: Long? = null,
    val updated_at: Long? = null,
    val error: String? = null,
)

@Serializable
data class CodexQuotaResponse(
    val ok: Boolean = false,
    val quota: CodexQuota = CodexQuota(),
)

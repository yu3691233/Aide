package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class MimoStatusResponse(
    val ok: Boolean = false,
    val running: Boolean = false,
    val pid: Int? = null,
    val port: Int = 4097,
)

@Serializable
data class MimoModel(
    val id: String = "",
    val name: String = "",
    val provider: String = "",
    val providerId: String = "",
)

@Serializable
data class MimoModelsEnvelope(
    val ok: Boolean = false,
    val models: List<MimoModel> = emptyList(),
    val current_model: String = "",
    val current_provider: String = "",
)

@Serializable
data class MimoWebUrlResponse(
    val ok: Boolean = false,
    val url: String = "",
    val message: String = "",
)

@Serializable
data class NewSessionResponse(
    val ok: Boolean = false,
    val session_id: String = "",
    val url: String = "",
    val message: String = "",
)

package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class UiLocatorCaptureResponse(
    val ok: Boolean = false,
    val device: String? = null,
    val screen_url: String? = null,
    val error: String? = null,
)

@Serializable
data class UiLocatorLocateRequest(
    val x: Int,
    val y: Int,
    val width: Int,
    val height: Int,
)

@Serializable
data class UiLocatorLocateResponse(
    val ok: Boolean = false,
    val element: UiLocatorElement? = null,
    val matched_code: ProjectNode? = null,
    val error: String? = null,
)

@Serializable
data class UiLocatorElement(
    val text: String = "",
    val `class`: String = "",
    val resource_id: String = "",
    val content_desc: String = "",
    val bounds: String = "",
)

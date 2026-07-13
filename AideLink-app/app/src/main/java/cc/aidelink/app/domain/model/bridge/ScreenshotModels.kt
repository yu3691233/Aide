package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class CropConfig(
    val left: Int = 0,
    val right: Int = 0,
    val top: Int = 0,
    val bottom: Int = 0,
    val dialog_position: String = "center",
    val calib_width: Int = 0,
    val calib_height: Int = 0,
)

@Serializable
data class ActiveCropConfigResponse(
    val ok: Boolean = false,
    val target: String = "",
    val monitor: String = "",
    val config: CropConfig = CropConfig(),
)

@Serializable
data class CropSaveRequest(
    val target: String,
    val left: Int,
    val right: Int,
    val top: Int,
    val bottom: Int,
    val monitor: String? = null,
    val dialog_position: String? = null,
    val calib_width: Int? = null,
    val calib_height: Int? = null,
)

@Serializable
data class MonitorInfo(
    val name: String,
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int,
    val width: Int,
    val height: Int,
    val primary: Boolean,
    val scale_factor: Float = 1.0f,
)

@Serializable
data class MonitorsResponse(
    val ok: Boolean,
    val monitors: List<MonitorInfo>,
)

@Serializable
data class WindowInfoResponse(
    val ok: Boolean = false,
    val window: WindowInfo? = null,
    val error: String? = null,
)

@Serializable
data class WindowInfo(
    val target: String = "",
    val title: String = "",
    val left: Int = 0,
    val top: Int = 0,
    val right: Int = 0,
    val bottom: Int = 0,
    val width: Int = 0,
    val height: Int = 0,
)

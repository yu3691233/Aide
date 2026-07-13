package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class WakeResult(
    val ok: Boolean,
    val skipped: Boolean = false,
    val reason: String? = null,
)

@Serializable
data class ScreenStatus(
    val ok: Boolean = false,
    val locked: Boolean = false,
    val platform: String = "",
    val supported: Boolean = false,
    val autoSkipLock: Boolean = false,
)

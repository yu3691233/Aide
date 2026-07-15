package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class IdeSession(
    val id: String = "",
    val ide: String = "",
    val title: String = "",
    val status: String = "idle",
    val last_message: String = "",
    val updated_at: String = "",
)

@Serializable
data class DesktopIdesResponse(
    val ides: List<DesktopIde> = emptyList(),
)

@Serializable
data class DesktopIde(
    val key: String = "",
    val name: String = "",
    val path: String = "",
    val version: String? = null,
    val source: String = "",
    val running: Boolean = false,
    val is_primary: Boolean = false,
    val icon: String = "",
    val color: String = "#90A4AE",
    val profile_version: String = "",
    val profile_source: String = "",
    val capabilities: List<String> = emptyList(),
)

@Serializable
data class IdeProcessesResponse(
    val ides: List<DesktopIde> = emptyList(),
)

@Serializable
data class IdeHistorySession(
    val id: String = "",
    val title: String = "",
    val updated_at: String = "",
)

@Serializable
data class IdeHistoryResponse(
    val ok: Boolean = false,
    val sessions: List<IdeHistorySession> = emptyList(),
)

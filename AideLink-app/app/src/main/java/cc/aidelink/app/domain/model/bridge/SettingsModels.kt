package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class SettingsEnvelope(
    val settings: SettingsPayload = SettingsPayload(),
    val schema: Map<String, SettingsSchemaField> = emptyMap(),
)

@Serializable
data class SettingsSchemaField(
    val type: String = "",
    val default: kotlinx.serialization.json.JsonElement? = null,
)

@Serializable
data class SettingsPayload(
    val server_url: String? = null,
    val wol_mac: String? = null,
    val app_language: String? = null,
    val app_theme: String? = null,
    val dynamic_color: Boolean? = null,
    val notifications_enabled: Boolean? = null,
    val haptic_feedback: Boolean? = null,
    val monitor_interval_ms: Long? = null,
    val monitor_height_dp: Int? = null,
    val xiaomengling_model: String? = null,
    val desktop_ide: String? = null,
    val desktop_ide_path: String? = null,
    val opencode_web_urls: Map<String, String>? = null,
    val opencode_web_mode: String? = null,
    val opencode_web_password: String? = null,
    val opencode_web_username: String? = null,
    val opencode_web_port: Int? = null,
    val opencode_web_connection: String? = null,
    val opencode_project_dir: String? = null,
    val project_dir: String? = null,
    val current_project: String? = null,
) {
    fun size(): Int = listOf(
        server_url, wol_mac, app_language, app_theme,
        dynamic_color, notifications_enabled, haptic_feedback,
        monitor_interval_ms, monitor_height_dp, xiaomengling_model,
        desktop_ide, desktop_ide_path,
        opencode_web_urls, opencode_web_mode, opencode_web_password,
        opencode_web_port,
    ).count { it != null }
}

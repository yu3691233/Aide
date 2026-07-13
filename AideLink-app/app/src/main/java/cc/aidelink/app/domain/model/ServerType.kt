package cc.aidelink.app.domain.model

/**
 * Server Type - identifies the type of IDE server
 */
enum class ServerType {
    OPENCODE,
    MIMOCODE,
    HAPPY;
    
    val displayName: String
        get() = when (this) {
            OPENCODE -> "OpenCode"
            MIMOCODE -> "MiMo Code"
            HAPPY -> "Happy"
        }
    
    companion object {
        fun fromString(value: String): ServerType {
            return when (value.lowercase()) {
                "opencode", "oc" -> OPENCODE
                "mimocode", "mimo" -> MIMOCODE
                "happy" -> HAPPY
                else -> OPENCODE
            }
        }
    }
}

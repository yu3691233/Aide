package cc.aidelink.app.domain.model.bridge

import kotlinx.serialization.Serializable

@Serializable
data class ProjectMapResponse(
    val ok: Boolean = false,
    val version: Int = 0,
    val scan_time: String = "",
    val project_root: String = "",
    val categories: List<ProjectNode> = emptyList(),
)

@Serializable
data class ProjectNode(
    val id: String = "",
    val name: String = "",
    val icon: String? = null,
    val file: String? = null,
    val line_start: Int? = null,
    val line_end: Int? = null,
    val composable: String? = null,
    val function: String? = null,
    @kotlinx.serialization.SerialName("class")
    val className: String? = null,
    val description: String? = null,
    val children: List<ProjectNode> = emptyList(),
) {
    /** 用于显示的位置标签，如 "HomeScreen.kt L421-L776" */
    val locationLabel: String
        get() {
            val f = file?.substringAfterLast('/') ?: return ""
            return if (line_start != null && line_end != null) {
                "$f L$line_start-$line_end"
            } else if (line_start != null) {
                "$f L$line_start"
            } else {
                f
            }
        }

    /** 代码符号名（composable / function / class） */
    val symbolName: String
        get() = composable ?: function ?: className ?: ""

    /** 是否为叶子节点（无子节点或只有文件级信息） */
    val isLeaf: Boolean
        get() = children.isEmpty()
}

@Serializable
data class ProjectLockRequest(
    val node_id: String,
    val node_name: String,
    val file: String,
    val symbol: String,
    val version: String,
    val description: String,
)

@Serializable
data class ProjectLockResponse(
    val ok: Boolean = false,
    val message: String? = null,
    val error: String? = null,
)

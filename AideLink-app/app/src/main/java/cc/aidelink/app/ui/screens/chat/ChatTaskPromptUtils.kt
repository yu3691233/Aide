package cc.aidelink.app.ui.screens.chat

internal fun extractTaskContent(text: String): String {
    val newFormat = Regex("【内容】(.+?)(?:\n\n【代码修改与优化任务】|\\Z)", RegexOption.DOT_MATCHES_ALL)
        .find(text)?.groupValues?.get(1)?.trim()
    if (!newFormat.isNullOrBlank()) return newFormat

    val oldFormat = Regex("【修改需求说明】\n?(.+?)(?:\n\n请针对|\n\n以下是待合并|\\Z)", RegexOption.DOT_MATCHES_ALL)
        .find(text)?.groupValues?.get(1)?.trim()
    if (!oldFormat.isNullOrBlank()) return oldFormat

    return text
}

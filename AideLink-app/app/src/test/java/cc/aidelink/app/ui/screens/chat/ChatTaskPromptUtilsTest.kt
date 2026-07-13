package cc.aidelink.app.ui.screens.chat

import org.junit.Assert.assertEquals
import org.junit.Test


class ChatTaskPromptUtilsTest {
    @Test
    fun extractsNewTaskFormatContent() {
        val prompt = """
            【内容】
            修复任务状态迁移，并补充测试。

            【代码修改与优化任务】
            下面是自动生成的细节。
        """.trimIndent()

        assertEquals("修复任务状态迁移，并补充测试。", extractTaskContent(prompt))
    }

    @Test
    fun extractsLegacyTaskFormatContent() {
        val prompt = """
            【修改需求说明】
            保留旧格式兼容。

            请针对以上需求修改代码。
        """.trimIndent()

        assertEquals("保留旧格式兼容。", extractTaskContent(prompt))
    }

    @Test
    fun returnsOriginalTextWhenNoEnvelopeExists() {
        val text = "直接发送的普通任务"
        assertEquals(text, extractTaskContent(text))
    }
}

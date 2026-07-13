package cc.aidelink.app.ui.screens.idechat

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mikepenz.markdown.m3.Markdown
import kotlinx.coroutines.delay

// 消息角色枚举
enum class IdeChatRole {
    USER,
    ASSISTANT
}

// 工具调用数据类
data class ToolCallInfo(
    val toolName: String,
    val toolIcon: String = "🔧", // 使用 emoji 作为默认图标
    val output: String = "",
    val isSuccess: Boolean = true,
    val executionTime: String = ""
)

// 消息数据类
data class IdeChatMessageItem(
    val id: String = "",
    val role: IdeChatRole = IdeChatRole.USER,
    val content: String = "",
    val timestamp: String = "",
    val isStreaming: Boolean = false,
    val toolCalls: List<ToolCallInfo> = emptyList()
)

/**
 * 消息气泡主组件
 * 根据消息角色自动选择左对齐（AI）或右对齐（用户）样式
 *
 * @param msg 消息数据对象
 * @param modifier 修饰符
 */
@Composable
fun IdeChatMessageBubble(
    msg: IdeChatMessageItem,
    modifier: Modifier = Modifier
) {
    when (msg.role) {
        IdeChatRole.USER -> UserMessageBubble(msg = msg, modifier = modifier)
        IdeChatRole.ASSISTANT -> AssistantMessageBubble(msg = msg, modifier = modifier)
    }
}

/**
 * 用户消息气泡 - 右对齐，使用 primary 颜色背景
 */
@Composable
private fun UserMessageBubble(
    msg: IdeChatMessageItem,
    modifier: Modifier = Modifier
) {
    val colorScheme = MaterialTheme.colorScheme

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        horizontalAlignment = Alignment.End
    ) {
        // 用户消息卡片
        Surface(
            modifier = Modifier.widthIn(max = 320.dp),
            shape = RoundedCornerShape(
                topStart = 16.dp,
                topEnd = 4.dp,
                bottomStart = 16.dp,
                bottomEnd = 16.dp
            ),
            color = colorScheme.primary,
            tonalElevation = 2.dp
        ) {
            Text(
                text = msg.content,
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                color = colorScheme.onPrimary,
                style = MaterialTheme.typography.bodyLarge.copy(
                    fontSize = 15.sp,
                    lineHeight = 22.sp
                )
            )
        }

        // 时间戳
        if (msg.timestamp.isNotEmpty()) {
            Text(
                text = msg.timestamp,
                modifier = Modifier.padding(top = 2.dp, end = 4.dp),
                style = MaterialTheme.typography.labelSmall,
                color = colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
            )
        }
    }
}

/**
 * AI 助手消息气泡 - 左对齐，使用 surfaceVariant 颜色背景
 * 支持 Markdown 渲染、流式显示和工具调用卡片
 */
@Composable
private fun AssistantMessageBubble(
    msg: IdeChatMessageItem,
    modifier: Modifier = Modifier
) {
    val colorScheme = MaterialTheme.colorScheme

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        horizontalAlignment = Alignment.Start
    ) {
        // AI 头像 + 消息内容行
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.Top
        ) {
            // AI 头像
            Surface(
                modifier = Modifier
                    .size(32.dp)
                    .padding(top = 2.dp),
                shape = RoundedCornerShape(8.dp),
                color = colorScheme.secondaryContainer
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        imageVector = Icons.Filled.AutoAwesome,
                        contentDescription = "AI助手",
                        modifier = Modifier.size(18.dp),
                        tint = colorScheme.onSecondaryContainer
                    )
                }
            }

            Spacer(modifier = Modifier.width(8.dp))

            // 消息内容区域
            Column(
                modifier = Modifier.weight(1f)
            ) {
                // 非流式消息 - 显示 Markdown 内容
                if (msg.content.isNotEmpty()) {
                    Surface(
                        modifier = Modifier.widthIn(max = 680.dp),
                        shape = RoundedCornerShape(
                            topStart = 4.dp,
                            topEnd = 16.dp,
                            bottomStart = 16.dp,
                            bottomEnd = 16.dp
                        ),
                        color = colorScheme.surfaceVariant.copy(alpha = 0.6f),
                        tonalElevation = 1.dp
                    ) {
                        if (msg.isStreaming) {
                            // 流式消息 - 显示实时文本 + 光标
                            StreamingContent(
                                content = msg.content,
                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp)
                            )
                        } else {
                            // 普通消息 - Markdown 渲染
                            MarkdownContent(
                                markdownText = msg.content,
                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp)
                            )
                        }
                    }
                }

                // 流式加载中指示器（无内容时光标动画）
                if (msg.isStreaming && msg.content.isEmpty()) {
                    StreamingIndicator(
                        modifier = Modifier.padding(start = 4.dp, top = 4.dp)
                    )
                }
            }
        }

        // 工具调用卡片列表
        if (msg.toolCalls.isNotEmpty()) {
            Column(
                modifier = Modifier
                    .padding(start = 40.dp, top = 6.dp)
                    .fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                msg.toolCalls.forEach { toolCall ->
                    ToolCallCard(toolCall = toolCall)
                }
            }
        }

        // 时间戳
        if (msg.timestamp.isNotEmpty()) {
            Text(
                text = msg.timestamp,
                modifier = Modifier.padding(start = 40.dp, top = 4.dp),
                style = MaterialTheme.typography.labelSmall,
                color = colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
            )
        }
    }
}

/**
 * Markdown 内容渲染组件
 */
@Composable
private fun MarkdownContent(
    markdownText: String,
    modifier: Modifier = Modifier
) {
    Markdown(
        modifier = modifier.fillMaxWidth(),
        content = markdownText
    )
}

/**
 * 流式内容组件 - 显示实时文本 + 闪烁光标
 */
@Composable
private fun StreamingContent(
    content: String,
    modifier: Modifier = Modifier
) {
    val colorScheme = MaterialTheme.colorScheme

    // 光标闪烁动画
    val infiniteTransition = rememberInfiniteTransition(label = "cursor_blink")
    val cursorAlpha by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = 0f,
        animationSpec = infiniteRepeatable(
            animation = tween(500, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "cursor_alpha"
    )

    Row(modifier = modifier) {
        // Markdown 渲染
        Box(modifier = Modifier.weight(1f)) {
            Markdown(
                modifier = Modifier.fillMaxWidth(),
                content = content
            )
        }

        // 闪烁光标
        Box(
            modifier = Modifier
                .width(2.dp)
                .height(20.dp)
                .background(
                    color = colorScheme.primary.copy(alpha = cursorAlpha),
                    shape = RoundedCornerShape(1.dp)
                )
                .align(Alignment.Bottom)
        )
    }
}

/**
 * 流式加载指示器 - 三点跳动动画
 */
@Composable
private fun StreamingIndicator(
    modifier: Modifier = Modifier
) {
    val colorScheme = MaterialTheme.colorScheme

    Row(
        modifier = modifier.padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        repeat(3) { index ->
            val infiniteTransition = rememberInfiniteTransition(label = "dot_$index")
            val alpha by infiniteTransition.animateFloat(
                initialValue = 0.3f,
                targetValue = 1f,
                animationSpec = infiniteRepeatable(
                    animation = tween(600, easing = LinearEasing),
                    repeatMode = RepeatMode.Reverse,
                    initialStartOffset = StartOffset(index * 200)
                ),
                label = "dot_alpha_$index"
            )

            Box(
                modifier = Modifier
                    .size(6.dp)
                    .clip(RoundedCornerShape(3.dp))
                    .background(
                        colorScheme.primary.copy(alpha = alpha)
                    )
            )
        }
    }
}

/**
 * 工具调用卡片组件 - 可展开/折叠显示工具详情
 */
@Composable
private fun ToolCallCard(
    toolCall: ToolCallInfo,
    modifier: Modifier = Modifier
) {
    val colorScheme = MaterialTheme.colorScheme
    var expanded by remember { mutableStateOf(false) }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable { expanded = !expanded },
        shape = RoundedCornerShape(10.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (toolCall.isSuccess) {
                colorScheme.surfaceVariant.copy(alpha = 0.5f)
            } else {
                colorScheme.errorContainer.copy(alpha = 0.4f)
            }
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.5.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // 卡片头部 - 工具名称和状态
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // 工具图标
                    Text(
                        text = toolCall.toolIcon,
                        fontSize = 16.sp
                    )

                    // 工具名称
                    Text(
                        text = toolCall.toolName,
                        style = MaterialTheme.typography.labelLarge,
                        fontFamily = FontFamily.Monospace,
                        color = if (toolCall.isSuccess) {
                            colorScheme.onSurfaceVariant
                        } else {
                            colorScheme.onErrorContainer
                        }
                    )

                    // 执行耗时
                    if (toolCall.executionTime.isNotEmpty()) {
                        Text(
                            text = toolCall.executionTime,
                            style = MaterialTheme.typography.labelSmall,
                            color = colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                        )
                    }
                }

                // 状态图标 + 展开指示器
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    // 成功/失败状态图标
                    Icon(
                        imageVector = if (toolCall.isSuccess) Icons.Filled.CheckCircle else Icons.Filled.Error,
                        contentDescription = if (toolCall.isSuccess) "成功" else "失败",
                        modifier = Modifier.size(14.dp),
                        tint = if (toolCall.isSuccess) {
                            Color(0xFF4CAF50)
                        } else {
                            colorScheme.error
                        }
                    )

                    // 展开/折叠箭头
                    Icon(
                        imageVector = if (expanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                        contentDescription = if (expanded) "收起" else "展开",
                        modifier = Modifier.size(18.dp),
                        tint = colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                    )
                }
            }

            // 展开详情 - 工具输出内容
            if (expanded && toolCall.output.isNotEmpty()) {
                Spacer(modifier = Modifier.height(8.dp))

                // 分割线
                HorizontalDivider(
                    color = colorScheme.outlineVariant.copy(alpha = 0.4f),
                    thickness = 0.5.dp
                )

                Spacer(modifier = Modifier.height(8.dp))

                // 输出标签
                Text(
                    text = "输出",
                    style = MaterialTheme.typography.labelSmall,
                    color = colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )

                Spacer(modifier = Modifier.height(4.dp))

                // 工具输出内容
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(6.dp),
                    color = colorScheme.surface
                ) {
                    Text(
                        text = toolCall.output,
                        modifier = Modifier.padding(10.dp),
                        style = MaterialTheme.typography.bodySmall.copy(
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp,
                            lineHeight = 18.sp
                        ),
                        color = colorScheme.onSurface.copy(alpha = 0.85f),
                        maxLines = 20,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}

// ============================================
// 预览
// ============================================

@Composable
@androidx.compose.ui.tooling.preview.Preview(name = "用户消息")
private fun PreviewUserMessage() {
    MaterialTheme {
        IdeChatMessageBubble(
            msg = IdeChatMessageItem(
                id = "1",
                role = IdeChatRole.USER,
                content = "请帮我写一个快速排序的 Kotlin 实现",
                timestamp = "14:30"
            )
        )
    }
}

@Composable
@androidx.compose.ui.tooling.preview.Preview(name = "AI 消息")
private fun PreviewAssistantMessage() {
    MaterialTheme {
        IdeChatMessageBubble(
            msg = IdeChatMessageItem(
                id = "2",
                role = IdeChatRole.ASSISTANT,
                content = "好的，这是一个快速排序的 Kotlin 实现：\n\n```kotlin\nfun quickSort(arr: IntArray, low: Int = 0, high: Int = arr.size - 1) {\n    if (low < high) {\n        val pi = partition(arr, low, high)\n        quickSort(arr, low, pi - 1)\n        quickSort(arr, pi + 1, high)\n    }\n}\n```",
                timestamp = "14:30",
                toolCalls = listOf(
                    ToolCallInfo(
                        toolName = "code_analysis",
                        toolIcon = "🔍",
                        output = "分析完成：代码复杂度 O(n log n)",
                        isSuccess = true,
                        executionTime = "0.3s"
                    )
                )
            )
        )
    }
}

@Composable
@androidx.compose.ui.tooling.preview.Preview(name = "流式消息")
private fun PreviewStreamingMessage() {
    MaterialTheme {
        IdeChatMessageBubble(
            msg = IdeChatMessageItem(
                id = "3",
                role = IdeChatRole.ASSISTANT,
                content = "正在分析您的代码，请稍候...",
                timestamp = "14:31",
                isStreaming = true
            )
        )
    }
}

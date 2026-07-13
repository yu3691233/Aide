package cc.aidelink.app.ui.screens.chat.components

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cc.aidelink.app.domain.model.bridge.ChatMessage
import cc.aidelink.app.ui.screens.chat.parseChoices
import cc.aidelink.app.ui.screens.chat.TargetBadge

@Composable
fun MessageBubble(
    msg: ChatMessage,
    onChoiceClick: (String) -> Unit
) {
    val isUser = msg.sender == "user"
    val isThinking = msg.target == "aide_thinking"
    val (cleanedText, choices) = remember(msg.text) { parseChoices(msg.text) }

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = if (isUser) Alignment.End else Alignment.Start
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
        ) {
            Surface(
                shape = RoundedCornerShape(
                    topStart = 12.dp,
                    topEnd = 12.dp,
                    bottomStart = if (isUser) 12.dp else 2.dp,
                    bottomEnd = if (isUser) 2.dp else 12.dp,
                ),
                color = when {
                    isUser -> MaterialTheme.colorScheme.primary
                    isThinking -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                    else -> MaterialTheme.colorScheme.surfaceVariant
                },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    if (!isUser) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            if (isThinking) {
                                Text(
                                    "💭 思考中",
                                    style = MaterialTheme.typography.labelSmall,
                                    fontWeight = FontWeight.SemiBold,
                                    color = MaterialTheme.colorScheme.tertiary,
                                )
                            } else {
                                TargetBadge(msg.target)
                                if (msg.sender.isNotBlank()) {
                                    Text(
                                        msg.sender,
                                        style = MaterialTheme.typography.labelSmall,
                                        fontWeight = FontWeight.SemiBold,
                                        color = MaterialTheme.colorScheme.primary,
                                    )
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(2.dp))
                    }
                    SelectionContainer {
                        Text(
                            cleanedText,
                            color = when {
                                isUser -> MaterialTheme.colorScheme.onPrimary
                                isThinking -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                                else -> MaterialTheme.colorScheme.onSurface
                            },
                            style = if (isThinking) MaterialTheme.typography.bodySmall
                            else MaterialTheme.typography.bodyMedium,
                            fontStyle = if (isThinking) androidx.compose.ui.text.font.FontStyle.Italic
                            else androidx.compose.ui.text.font.FontStyle.Normal,
                        )
                    }
                    Spacer(modifier = Modifier.height(2.dp))
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        if (isUser && msg.target != null && msg.target != "auto") {
                            TargetBadge(msg.target)
                        }
                        if (msg.time.isNotBlank()) {
                            Text(
                                msg.time,
                                style = MaterialTheme.typography.labelSmall,
                                color = if (isUser) MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.7f)
                                else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                            )
                        }
                    }
                }
            }
        }

        if (choices.isNotEmpty()) {
            Spacer(modifier = Modifier.height(4.dp))
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                choices.forEach { choice ->
                    SuggestionChip(
                        onClick = { onChoiceClick(choice) },
                        label = { Text(choice) }
                    )
                }
            }
        }
    }
}

@Composable
fun MimoControlBar(
    running: Boolean,
    loading: Boolean,
    onToggle: () -> Unit,
    onRefresh: () -> Unit,
) {
    Surface(
        tonalElevation = 2.dp,
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // 状态指示灯
            Box(
                modifier = Modifier
                    .size(10.dp)
                    .background(
                        color = if (running) Color(0xFF4CAF50) else Color(0xFF9E9E9E),
                        shape = CircleShape,
                    )
            )
            Text(
                text = if (running) "OpenCode 在线" else "OpenCode 离线",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(modifier = Modifier.weight(1f))
            // 刷新按钮
            IconButton(
                onClick = onRefresh,
                enabled = !loading,
                modifier = Modifier.size(32.dp),
            ) {
                if (loading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                    )
                } else {
                    Icon(
                        Icons.Default.Refresh,
                        contentDescription = "刷新状态",
                        modifier = Modifier.size(16.dp),
                    )
                }
            }
            // 启停按钮
            Button(
                onClick = onToggle,
                enabled = !loading,
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp),
                colors = if (running) {
                    ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error,
                        contentColor = MaterialTheme.colorScheme.onError,
                    )
                } else {
                    ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF4CAF50),
                        contentColor = Color.White,
                    )
                },
                modifier = Modifier.height(32.dp),
            ) {
                Text(
                    text = if (running) "停止" else "启动",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

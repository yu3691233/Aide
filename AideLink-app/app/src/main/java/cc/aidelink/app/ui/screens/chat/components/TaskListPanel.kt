package cc.aidelink.app.ui.screens.chat.components

import android.widget.Toast
import androidx.compose.animation.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cc.aidelink.app.ui.screens.chat.extractTaskContent
import cc.aidelink.app.domain.model.bridge.AideTask
import cc.aidelink.app.ui.screens.chat.PromptAction
import coil.compose.AsyncImage

// IDE badge 颜色辅助（背景色 + 文字色）
private data class IdeBadgeColors(val bg: Color, val text: Color)

private fun getIdeBadgeColors(ide: String): IdeBadgeColors = when (ide.lowercase()) {
    "mimo" -> IdeBadgeColors(bg = Color(0xFFFFF3E0), text = Color(0xFFF57C00))
    "agy" -> IdeBadgeColors(bg = Color(0xFFF3E5F5), text = Color(0xFF7B1FA2))
    "trae" -> IdeBadgeColors(bg = Color(0xFFE1F5FE), text = Color(0xFF0288D1))
    "oc", "oc_web" -> IdeBadgeColors(bg = Color(0xFFE8F5E9), text = Color(0xFF388E3C))
    else -> IdeBadgeColors(bg = Color(0xFFECEFF1), text = Color(0xFF455A64))
}

private val offlineTaskStatuses = setOf("draft", "pending_upload")

internal fun taskStatusMatchesTab(status: String, tab: Int): Boolean {
    val normalized = status.lowercase()
    return when (tab) {
        0 -> normalized !in setOf("done", "failed", "pending_test") && normalized !in offlineTaskStatuses
        1 -> normalized == "pending_test"
        2 -> normalized == "done"
        3 -> normalized in offlineTaskStatuses
        else -> true
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskListPanel(
    tasks: List<AideTask>,
    loading: Boolean,
    batchMode: Boolean,
    selectedTaskIds: Set<String>,
    currentTarget: String = "",
    onComplete: (String) -> Unit,
    onFail: (String) -> Unit,
    onDelete: (String) -> Unit,
    onLongPress: (String) -> Unit,
    onToggleSelect: (String) -> Unit,
    onSelectTasks: (Set<String>) -> Unit = {},
    onExitBatchMode: () -> Unit,
    onBatchDelete: () -> Unit,
    onBatchComplete: () -> Unit,
    onBatchDispatch: () -> Unit,
    onDispatch: (String) -> Unit,
    onSyncOfflineTask: (String) -> Unit,
    onOpenTask: (String) -> Unit,
    onEditTask: (String) -> Unit,
    onConfirm: (String) -> Unit = {},
    onPromptBuilder: (String) -> Unit = {},
    selectedTab: Int = 0,
    onSelectedTabChange: (Int) -> Unit = {},
    bridgeUrl: String = "",
    modifier: Modifier = Modifier
) {
    // Tab 过滤状态：0=进行中 1=待测试 2=已完成 3=离线任务
    // 当前IDE / 全部切换
    var filterCurrentIdeOnly by remember { mutableStateOf(true) }

    // 按 IDE 预筛选
    val filteredTasksByIde = remember(tasks, filterCurrentIdeOnly, currentTarget) {
        if (filterCurrentIdeOnly && currentTarget.isNotBlank()) {
            tasks.filter { it.target_ide?.lowercase() == currentTarget.lowercase() }
        } else {
            tasks
        }
    }

    val activeTasksCount = remember(filteredTasksByIde) {
        filteredTasksByIde.count { taskStatusMatchesTab(it.status, 0) }
    }
    val pendingTestTasksCount = remember(filteredTasksByIde) {
        filteredTasksByIde.count { it.status.lowercase() == "pending_test" }
    }
    val offlineTasksCount = remember(filteredTasksByIde) {
        filteredTasksByIde.count { taskStatusMatchesTab(it.status, 3) }
    }

    // 排序：最新的在前
    val sortedTasks = remember(filteredTasksByIde) {
        filteredTasksByIde.sortedByDescending { it.created_at ?: "" }
    }

    // 按 Tab 过滤
    val displayedTasks = remember(sortedTasks, selectedTab) {
        sortedTasks.filter { taskStatusMatchesTab(it.status, selectedTab) }
    }
    val displayedTaskIds = remember(displayedTasks) { displayedTasks.map { it.task_id }.toSet() }
    val allDisplayedSelected = displayedTaskIds.isNotEmpty() && displayedTaskIds.all { it in selectedTaskIds }

    Column(modifier = modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        // Tab 行 + 当前/全部 切换
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface)
                .padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Tab 列表
            Row(
                modifier = Modifier.weight(1f).horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(14.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                val tabs = listOf(
                    "进行中${if (activeTasksCount > 0) " $activeTasksCount" else ""}" to 0,
                    "待测试${if (pendingTestTasksCount > 0) " $pendingTestTasksCount" else ""}" to 1,
                    "已完成" to 2,
                    "离线任务${if (offlineTasksCount > 0) " $offlineTasksCount" else ""}" to 3,
                )
                tabs.forEach { (label, index) ->
                    val isSelected = selectedTab == index
                    Column(
                        modifier = Modifier
                            .clickable { onSelectedTabChange(index) }
                            .padding(vertical = 4.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = label,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                            color = if (isSelected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Box(
                            modifier = Modifier
                                .height(2.dp)
                                .width(28.dp)
                                .background(if (isSelected) MaterialTheme.colorScheme.primary else Color.Transparent)
                        )
                    }
                }
            }

            // 当前 IDE / 全部切换（仅当 currentTarget 非空时显示）
            if (currentTarget.isNotBlank()) {
                Row(
                    modifier = Modifier
                        .clip(RoundedCornerShape(6.dp))
                        .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
                        .padding(2.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    listOf(true to "当前", false to "全部").forEach { (onlyCurrent, label) ->
                        val isSelected = filterCurrentIdeOnly == onlyCurrent
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(if (isSelected) MaterialTheme.colorScheme.surface.copy(alpha = 0.9f) else Color.Transparent)
                                .clickable { filterCurrentIdeOnly = onlyCurrent }
                                .padding(horizontal = 8.dp, vertical = 4.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = label,
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                color = if (isSelected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
        }

        // 批量操作工具栏
        AnimatedVisibility(
            visible = batchMode,
            enter = fadeIn() + expandVertically(),
            exit = fadeOut() + shrinkVertically()
        ) {
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 6.dp),
                shape = RoundedCornerShape(10.dp),
                color = MaterialTheme.colorScheme.surface,
                tonalElevation = 1.dp,
                shadowElevation = 1.dp,
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.45f))
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 10.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        IconButton(
                            onClick = onExitBatchMode,
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Close,
                                contentDescription = "取消",
                                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.size(18.dp)
                            )
                        }
                        Text(
                            text = "已选择 ${selectedTaskIds.size}",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        TextButton(
                            onClick = {
                                if (allDisplayedSelected) onSelectTasks(emptySet())
                                else onSelectTasks(displayedTaskIds)
                            },
                            enabled = displayedTaskIds.isNotEmpty(),
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)
                        ) {
                            Text(
                                text = if (allDisplayedSelected) "清空" else "全选",
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                    }

                    val isEnabled = selectedTaskIds.isNotEmpty()
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Button(
                            onClick = onBatchDispatch,
                            enabled = isEnabled,
                            modifier = Modifier.weight(1f).height(36.dp),
                            shape = RoundedCornerShape(8.dp),
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)
                        ) {
                            Icon(Icons.Default.Send, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("合并派发", fontSize = 13.sp, maxLines = 1)
                        }
                        OutlinedButton(
                            onClick = onBatchComplete,
                            enabled = isEnabled,
                            modifier = Modifier.weight(1f).height(36.dp),
                            shape = RoundedCornerShape(8.dp),
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)
                        ) {
                            Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("完成", fontSize = 13.sp, maxLines = 1)
                        }
                        OutlinedButton(
                            onClick = onBatchDelete,
                            enabled = isEnabled,
                            modifier = Modifier.weight(1f).height(36.dp),
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)
                        ) {
                            Icon(Icons.Default.Delete, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("删除", fontSize = 13.sp, maxLines = 1)
                        }
                    }
                }
            }
        }

        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.4f))

        if (loading && tasks.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (displayedTasks.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("暂无任务", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f)),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(displayedTasks.size, key = { displayedTasks[it].task_id }) { i ->
                    SwipeableTaskCard(
                        task = displayedTasks[i],
                        batchMode = batchMode,
                        isSelected = displayedTasks[i].task_id in selectedTaskIds,
                        onComplete = onComplete,
                        onFail = onFail,
                        onDelete = onDelete,
                        onDispatch = onDispatch,
                        onSyncOfflineTask = onSyncOfflineTask,
                        onOpenTask = onOpenTask,
                        onEditTask = onEditTask,
                        onLongPress = onLongPress,
                        onToggleSelect = onToggleSelect,
                        onConfirm = onConfirm,
                        onPromptBuilder = onPromptBuilder,
                        bridgeUrl = bridgeUrl,
                    )
                }
            }
        }
    }
}

// 支持左滑的任务卡片容器
@Composable
fun SwipeableTaskCard(
    task: AideTask,
    batchMode: Boolean,
    isSelected: Boolean,
    onComplete: (String) -> Unit,
    onFail: (String) -> Unit,
    onDelete: (String) -> Unit,
    onDispatch: (String) -> Unit,
    onSyncOfflineTask: (String) -> Unit,
    onOpenTask: (String) -> Unit,
    onEditTask: (String) -> Unit,
    onLongPress: (String) -> Unit,
    onToggleSelect: (String) -> Unit,
    onConfirm: (String) -> Unit = {},
    onPromptBuilder: (String) -> Unit = {},
    bridgeUrl: String = "",
) {
    val context = LocalContext.current
    var swipeOffset by remember { mutableStateOf(0f) }
    val density = LocalDensity.current
    val totalWidthDp = 198.dp
    val totalWidthPx = with(density) { totalWidthDp.toPx() }

    // 进入批量模式时复位滑动偏移
    LaunchedEffect(batchMode) {
        if (batchMode) swipeOffset = 0f
    }

    val wrapperBgColor = MaterialTheme.colorScheme.surface

    Box(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Color.Transparent)) {
        // 背景操作层（右侧，圆形图标按钮）
        Row(
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .fillMaxHeight()
                .padding(end = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 派发
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(CircleShape)
                    .background(Color(0xFFE3F2FD))
                    .clickable {
                        swipeOffset = 0f
                        onDispatch(task.task_id)
                    },
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Default.Send, contentDescription = "派发", tint = Color(0xFF1E88E5), modifier = Modifier.size(18.dp))
            }
            // 修改
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(CircleShape)
                    .background(Color(0xFFFFF3E0))
                    .clickable {
                        swipeOffset = 0f
                        onEditTask(task.task_id)
                    },
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Default.Edit, contentDescription = "修改", tint = Color(0xFFF57C00), modifier = Modifier.size(18.dp))
            }
            // 完成
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(CircleShape)
                    .background(Color(0xFFE8F5E9))
                    .clickable {
                        swipeOffset = 0f
                        onComplete(task.task_id)
                    },
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Default.CheckCircle, contentDescription = "完成", tint = Color(0xFF43A047), modifier = Modifier.size(18.dp))
            }
            // 删除
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(CircleShape)
                    .background(Color(0xFFFFEBEE))
                    .clickable {
                        swipeOffset = 0f
                        onDelete(task.task_id)
                    },
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Default.Delete, contentDescription = "删除", tint = Color(0xFFE53935), modifier = Modifier.size(18.dp))
            }
        }

        // 前景任务卡片（可左滑）
        Box(
            modifier = Modifier
                .offset { IntOffset(swipeOffset.toInt(), 0) }
                .background(wrapperBgColor)
                .draggable(
                    orientation = Orientation.Horizontal,
                    enabled = !batchMode,
                    state = rememberDraggableState { delta ->
                        swipeOffset = (swipeOffset + delta).coerceIn(-totalWidthPx, 0f)
                    },
                    onDragStopped = { velocity ->
                        swipeOffset = if (swipeOffset < -totalWidthPx / 2 || velocity < -800f) {
                            -totalWidthPx
                        } else {
                            0f
                        }
                    }
                )
        ) {
            TaskCard(
                task = task,
                batchMode = batchMode,
                isSelected = isSelected,
                onToggleSelect = onToggleSelect,
                onLongPress = onLongPress,
                onComplete = onComplete,
                onFail = onFail,
                onDelete = onDelete,
                onDispatch = onDispatch,
                onSyncOfflineTask = onSyncOfflineTask,
                onOpenTask = onOpenTask,
                onConfirm = onConfirm,
                onPromptBuilder = onPromptBuilder,
                bridgeUrl = bridgeUrl,
            )
        }
    }
}

@Composable
fun TaskCard(
    task: AideTask,
    batchMode: Boolean = false,
    isSelected: Boolean = false,
    onToggleSelect: (String) -> Unit = {},
    onLongPress: (String) -> Unit = {},
    onComplete: (String) -> Unit,
    onFail: (String) -> Unit,
    onDelete: (String) -> Unit,
    onDispatch: (String) -> Unit = {},
    onSyncOfflineTask: (String) -> Unit = {},
    onOpenTask: (String) -> Unit = {},
    onConfirm: (String) -> Unit = {},
    onPromptBuilder: (String) -> Unit = {},
    bridgeUrl: String = "",
) {
    var expanded by remember { mutableStateOf(false) }

    val statusColor = when (task.status.lowercase()) {
        "done" -> Color(0xFF4CAF50)
        "failed" -> Color(0xFFF44336)
        "running", "dispatched" -> Color(0xFF2196F3)
        "pending_test" -> Color(0xFFFFA000)
        "queued" -> Color(0xFF9C27B0)
        "draft", "pending" -> Color(0xFF9E9E9E)
        "pending_dispatch" -> Color(0xFF9C27B0)
        "pending_upload" -> Color(0xFFFB8C00)
        "offline" -> Color(0xFF757575)
        else -> Color(0xFF2196F3)
    }

    val statusText = when (task.status.lowercase()) {
        "done" -> "已完成"
        "failed" -> "失败"
        "running", "dispatched" -> "运行中"
        "pending_test" -> "待测试"
        "queued" -> "排队中"
        "draft" -> "草稿"
        "pending_dispatch" -> "待派发"
        "pending_upload" -> "待同步"
        "offline" -> "离线"
        else -> task.status
    }

    val sourceLabel = when (task.source?.lowercase()) {
        "phone" -> task.device_label?.ifBlank { null } ?: "手机"
        "api" -> "API"
        "user" -> "用户"
        "web" -> "Web"
        "app" -> "APP"
        else -> task.source ?: ""
    }
    val originLabel = task.task_origin_label ?: if (task.task_origin == "agent" || task.source == "primary_ide") "Agent任务" else "用户任务"

    val cardBgColor = MaterialTheme.colorScheme.surface
    val selectedBgColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.14f)

    val cardBorder = if (isSelected) BorderStroke(
        width = 1.dp,
        color = MaterialTheme.colorScheme.primary.copy(alpha = 0.22f)
    ) else null

    ElevatedCard(
        modifier = Modifier
            .fillMaxWidth()
            .pointerInput(batchMode, task.task_id, task.status) {
                detectTapGestures(
                    onTap = {
                        if (batchMode) {
                            onToggleSelect(task.task_id)
                        } else {
                            // 离线任务点击时同步并派发，不进入任务会话。
                            val s = task.status.lowercase()
                            if (s in offlineTaskStatuses) {
                                onSyncOfflineTask(task.task_id)
                            } else if (s == "pending_dispatch" || s == "queued") {
                                onDispatch(task.task_id)
                            } else {
                                onOpenTask(task.task_id)
                            }
                        }
                    },
                    onLongPress = { if (!batchMode) onLongPress(task.task_id) }
                )
            }
            .let { if (cardBorder != null) it.border(cardBorder, RoundedCornerShape(12.dp)) else it },
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.elevatedCardColors(
            containerColor = if (isSelected) selectedBgColor else cardBgColor
        ),
        elevation = CardDefaults.elevatedCardElevation(defaultElevation = if (isSelected) 2.dp else 1.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(IntrinsicSize.Min)
        ) {
            Box(
                modifier = Modifier
                    .width(4.dp)
                    .fillMaxHeight()
                    .background(
                        color = statusColor,
                        shape = RoundedCornerShape(topStart = 12.dp, bottomStart = 12.dp)
                    )
            )

            if (batchMode) {
                Box(
                    modifier = Modifier
                        .padding(start = 12.dp)
                        .size(20.dp)
                        .clip(CircleShape)
                        .background(
                            if (isSelected) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.surface
                        )
                        .border(
                            width = 1.dp,
                            color = if (isSelected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline.copy(alpha = 0.45f),
                            shape = CircleShape
                        )
                        .align(Alignment.CenterVertically),
                    contentAlignment = Alignment.Center
                ) {
                    if (isSelected) {
                        Icon(
                            Icons.Default.Check,
                            contentDescription = null,
                            tint = Color.White,
                            modifier = Modifier.size(14.dp)
                        )
                    }
                }
            }

            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(12.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(
                        modifier = Modifier.weight(1f),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = statusColor.copy(alpha = 0.08f)
                        ) {
                            Text(
                                text = " $statusText ",
                                color = statusColor,
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                            )
                        }

                        // 标题异步出现前后都占用同一左侧区域，避免尾部 IDE 标签跳位。
                        val displayTitle = task.title?.takeIf { it.isNotBlank() }
                        if (displayTitle != null) {
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = displayTitle,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.75f),
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }

                    task.target_ide?.let { ide ->
                        Spacer(modifier = Modifier.width(8.dp))
                        val badgeColors = getIdeBadgeColors(ide)
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = badgeColors.bg
                        ) {
                            Text(
                                text = " ${ide.uppercase()} ",
                                color = badgeColors.text,
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                val snippet = task.text.let { extractTaskContent(it) }.ifBlank { task.task_id }
                Text(
                    text = if (expanded) (task.text.ifBlank { task.task_id }) else snippet,
                    style = MaterialTheme.typography.bodyMedium.copy(
                        fontWeight = FontWeight.Medium,
                        fontSize = 15.sp,
                        lineHeight = 20.sp
                    ),
                    color = MaterialTheme.colorScheme.onSurface,
                    maxLines = if (expanded) Int.MAX_VALUE else 6,
                    overflow = TextOverflow.Ellipsis
                )

                if (expanded) {
                    if (task.title != null && task.text.isNotBlank()) {
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = task.text,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    if (!task.summary.isNullOrBlank()) {
                        Spacer(modifier = Modifier.height(8.dp))
                        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f))
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            text = "摘要: ${task.summary}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }

                    if (!task.error.isNullOrBlank()) {
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "错误: ${task.error}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error
                        )
                    }

                    if (!task.image.isNullOrBlank()) {
                        Spacer(modifier = Modifier.height(8.dp))
                        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f))
                        Spacer(modifier = Modifier.height(8.dp))
                        val imageUrl = if (task.image!!.startsWith("http")) {
                            task.image
                        } else {
                            "${bridgeUrl}${if (task.image.startsWith("/")) task.image else "/${task.image}"}"
                        }
                        AsyncImage(
                            model = imageUrl,
                            contentDescription = "任务截图",
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp)),
                            contentScale = ContentScale.FillWidth,
                            error = painterResource(id = android.R.drawable.ic_menu_gallery)
                        )
                    }

                    if (!task.feedbacks.isNullOrEmpty()) {
                        Spacer(modifier = Modifier.height(8.dp))
                        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f))
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "💬 反学历史 (${task.feedbacks!!.size} 条)",
                            style = MaterialTheme.typography.labelSmall,
                            color = Color(0xFFFFA726),
                            fontWeight = FontWeight.Bold
                        )
                        task.feedbacks!!.forEachIndexed { idx, fb ->
                            Spacer(modifier = Modifier.height(4.dp))
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = Color(0xFFFFA726).copy(alpha = 0.08f)
                            ) {
                                Column(modifier = Modifier.padding(8.dp).fillMaxWidth()) {
                                    val fbTime = fb.time?.let {
                                        try {
                                            it.substringAfter('T').substringBefore('.').take(5)
                                        } catch (_: Exception) { "" }
                                    } ?: ""
                                    Text(
                                        text = "#${idx + 1}${if (fbTime.isNotBlank()) " · $fbTime" else ""}",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                                    )
                                    Spacer(modifier = Modifier.height(2.dp))
                                    Text(
                                        text = fb.text,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = Color(0xFFFFA726)
                                    )
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(6.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        val displayVersion = task.git_version?.ifBlank { null }
                            ?: task.app_version?.ifBlank { null }
                        if (displayVersion != null) {
                            Surface(
                                shape = RoundedCornerShape(3.dp),
                                color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                            ) {
                                Text(
                                    text = " $displayVersion ",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                                )
                            }
                        }
                        if (sourceLabel.isNotBlank()) {
                            Text(
                                text = "$originLabel · $sourceLabel",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                            )
                        }
                    }
                    task.created_at?.let { t ->
                        val cleanTime = buildString {
                            val date = t.substringBefore('T')
                            val time = t.substringAfter('T').substringBefore('.')
                            append(date.substring(5))
                            append(" ")
                            append(time.substring(0, 5))
                        }
                        Text(
                            text = cleanTime,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                        )
                    }
                }

                if (expanded && !batchMode) {
                    Spacer(modifier = Modifier.height(6.dp))
                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f))
                    Spacer(modifier = Modifier.height(6.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Button(
                            onClick = {
                                onDispatch(task.task_id)
                                expanded = false
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2196F3)),
                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                            modifier = Modifier.height(30.dp)
                        ) {
                            Icon(Icons.Default.Send, contentDescription = "派发", modifier = Modifier.size(14.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("派发", fontSize = 11.sp, color = Color.White)
                        }
                        if (task.status.lowercase() != "done") {
                            if (task.status.lowercase() == "pending_test") {
                                Button(
                                    onClick = { onConfirm(task.task_id) },
                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFFFC107)),
                                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                                    modifier = Modifier.height(30.dp)
                                ) {
                                    Icon(Icons.Default.CheckCircle, contentDescription = "确认完成", modifier = Modifier.size(14.dp), tint = Color.Black)
                                    Spacer(Modifier.width(4.dp))
                                    Text("确认完成", fontSize = 11.sp, color = Color.Black)
                                }
                            } else {
                                Button(
                                    onClick = { onComplete(task.task_id) },
                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF4CAF50)),
                                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                                    modifier = Modifier.height(30.dp)
                                ) {
                                    Text("完成", fontSize = 11.sp, color = Color.White)
                                }
                            }
                            if (task.status.lowercase() != "failed") {
                                Button(
                                    onClick = { onPromptBuilder(task.task_id) },
                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF9C27B0)),
                                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                                    modifier = Modifier.height(30.dp)
                                ) {
                                    Icon(Icons.Default.AutoAwesome, contentDescription = "AI提示词", modifier = Modifier.size(14.dp))
                                    Spacer(Modifier.width(4.dp))
                                    Text("AI提示词", fontSize = 11.sp, color = Color.White)
                                }
                            }
                        }
                        Spacer(modifier = Modifier.weight(1f))
                        OutlinedButton(
                            onClick = { onDelete(task.task_id) },
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                            modifier = Modifier.height(30.dp)
                        ) {
                            Icon(Icons.Default.Delete, contentDescription = "删除", modifier = Modifier.size(14.dp))
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskPromptBuilderDialog(
    taskText: String,
    action: PromptAction?,
    description: String,
    generatedPrompt: String,
    promptCandidates: List<cc.aidelink.app.domain.model.bridge.PromptCandidate>,
    promptPredictLoading: Boolean,
    onSetAction: (PromptAction) -> Unit,
    onSetDescription: (String) -> Unit,
    onPredictPrompts: (String) -> Unit,
    onGenerate: () -> Unit,
    onUsePrompt: () -> Unit,
    onDismiss: () -> Unit,
) {
    val clipboardManager = LocalClipboardManager.current

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Default.AutoAwesome,
                        contentDescription = null,
                        modifier = Modifier.size(20.dp),
                        tint = Color(0xFF9C27B0),
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("AI 提示词生成器", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                }
                IconButton(onClick = onDismiss, modifier = Modifier.size(28.dp)) {
                    Icon(Icons.Default.Close, contentDescription = "关闭", modifier = Modifier.size(16.dp))
                }
            }
        },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                val taskContent = extractTaskContent(taskText).ifBlank { "（无内容）" }
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(8.dp)) {
                        Text("📋 任务内容", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(taskContent, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 4, overflow = TextOverflow.Ellipsis)
                    }
                }
                Text("操作类型", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.horizontalScroll(rememberScrollState())) {
                    PromptAction.entries.forEach { a ->
                        FilterChip(selected = action == a, onClick = { onSetAction(a) }, label = { Text("${a.emoji} ${a.label}", style = MaterialTheme.typography.labelMedium) },
                            colors = FilterChipDefaults.filterChipColors(selectedContainerColor = MaterialTheme.colorScheme.primaryContainer, selectedLabelColor = MaterialTheme.colorScheme.onPrimaryContainer))
                    }
                }
                OutlinedTextField(
                    value = description,
                    onValueChange = onSetDescription,
                    modifier = Modifier.fillMaxWidth(),
                    textStyle = MaterialTheme.typography.bodySmall,
                    placeholder = { Text("补充描述（可选，如：添加重置按钮）", style = MaterialTheme.typography.bodySmall) },
                    maxLines = 3,
                    shape = RoundedCornerShape(12.dp)
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = { onPredictPrompts(description) },
                        modifier = Modifier.weight(1f),
                        enabled = action != null && !promptPredictLoading,
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary)
                    ) {
                        if (promptPredictLoading) {
                            CircularProgressIndicator(modifier = Modifier.size(16.dp), color = MaterialTheme.colorScheme.onSecondary, strokeWidth = 2.dp)
                            Spacer(Modifier.width(6.dp))
                            Text("正在分析...", fontSize = 11.sp)
                        } else {
                            Icon(Icons.Default.AutoAwesome, contentDescription = null, modifier = Modifier.size(14.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("AI 预测/分析需求", fontSize = 11.sp)
                        }
                    }

                    Button(
                        onClick = onGenerate,
                        modifier = Modifier.weight(1f),
                        enabled = action != null
                    ) {
                        Icon(Icons.Default.Build, contentDescription = null, modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("生成提示词", fontSize = 11.sp)
                    }
                }

                if (promptCandidates.isNotEmpty()) {
                    Text("推荐候选 (点击可填入)", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        promptCandidates.forEachIndexed { idx, c ->
                            Card(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { onSetDescription(c.prompt) },
                                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f)),
                                shape = RoundedCornerShape(8.dp),
                                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f))
                            ) {
                                Column(modifier = Modifier.padding(10.dp)) {
                                    Text(
                                        text = "推荐 ${idx + 1}: ${c.prompt}",
                                        style = MaterialTheme.typography.bodySmall,
                                        fontWeight = FontWeight.Medium,
                                        color = MaterialTheme.colorScheme.onSurface
                                    )
                                    if (c.effect.isNotEmpty() || c.reason.isNotEmpty()) {
                                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp), color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f))
                                        if (c.effect.isNotEmpty()) {
                                            Text("🎯 预期效果: ${c.effect}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.secondary)
                                        }
                                        if (c.reason.isNotEmpty()) {
                                            Text("💡 建议理由: ${c.reason}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                if (generatedPrompt.isNotEmpty()) {
                    Surface(color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.3f), shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(10.dp)) {
                            Text("生成的提示词", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
                            Spacer(modifier = Modifier.height(4.dp))
                            SelectionContainer { Text(generatedPrompt, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface) }
                            Spacer(modifier = Modifier.height(8.dp))
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Button(
                                    onClick = onUsePrompt,
                                    modifier = Modifier.weight(1.5f),
                                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary),
                                    contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp)
                                ) {
                                    Text("填入输入框", fontSize = 10.sp)
                                }
                                OutlinedButton(
                                    onClick = { clipboardManager.setText(AnnotatedString(generatedPrompt)) },
                                    modifier = Modifier.weight(1f),
                                    contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp)
                                ) {
                                    Icon(Icons.Default.ContentCopy, contentDescription = null, modifier = Modifier.size(12.dp))
                                    Spacer(Modifier.width(2.dp))
                                    Text("复制", fontSize = 10.sp)
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } }
    )
}

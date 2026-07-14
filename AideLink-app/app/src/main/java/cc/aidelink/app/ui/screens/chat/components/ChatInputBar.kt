package cc.aidelink.app.ui.screens.chat.components

import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import cc.aidelink.app.ui.screens.chat.AideLinkChatViewModel
import cc.aidelink.app.ui.screens.chat.TargetIcon

@Composable
fun ChatInputBar(
    input: String,
    sending: Boolean,
    uploading: Boolean,
    currentTarget: AideLinkChatViewModel.Target,
    monitorByTarget: Map<AideLinkChatViewModel.Target, Boolean>,
    selectedIdeList: List<String> = emptyList(),
    ideRunningMap: Map<String, Boolean> = emptyMap(),
    quickReplies: List<String> = emptyList(),
    isPromptMode: Boolean = false,
    onInputChange: (String) -> Unit,
    onSend: () -> Unit,
    onSendToTaskList: () -> Unit = {},
    onUploadImage: (String) -> Unit,
    onTargetChange: (AideLinkChatViewModel.Target) -> Unit,
    onMonitorToggle: (AideLinkChatViewModel.Target) -> Unit,
    onClipboard: () -> Unit,
    onWakeScreen: () -> Unit,
    onStartIde: (String) -> Unit = {},
    onStopIde: (String) -> Unit = {},
    onRefreshIdeStatus: () -> Unit = {},
    onQuickReply: (String) -> Unit = {},
    onAddQuickReply: (String) -> Unit = {},
    onRemoveQuickReply: (String) -> Unit = {},
    onShowDesktopIdeDialog: () -> Unit = {},
    projectMapExpanded: Boolean = false,
    onToggleProjectMap: () -> Unit = {},
    onRefreshTasks: () -> Unit = {},
    onStartUiLocator: () -> Unit = {},
    onCreateNewSession: () -> Unit = {},
    bridgeOnline: Boolean = false,
    bridgeConnecting: Boolean = true,
    showTaskList: Boolean = false,
    taskThreadMode: Boolean = false,
    taskEditMode: Boolean = false,
    onToggleTaskList: () -> Unit = {},
    onEnterTaskList: () -> Unit = {},
    onSaveTaskEdit: () -> Unit = {},
    onCancelTaskEdit: () -> Unit = {},
    onOptimizeTaskPrompt: () -> Unit = {},
    ocWebRunning: Boolean = false,
    onOcWebToggle: () -> Unit = {},
    onOpenWeb: () -> Unit = {},
) {
    val context = LocalContext.current
    val focusManager = LocalFocusManager.current
    val imagePickerLauncher = rememberLauncherForActivityResult(
        contract = androidx.activity.result.contract.ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        if (uri != null) {
            val path = copyUriToTempFile(context, uri)
            if (path != null) {
                onUploadImage(path)
            } else {
                Toast.makeText(context, "无法读取图片", Toast.LENGTH_SHORT).show()
            }
        }
    }

    var showQuickReplyManager by remember { mutableStateOf(false) }

    Surface(
        color = MaterialTheme.colorScheme.background,
        shadowElevation = 4.dp,
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            // 工具栏行：目标选择器 + 监视器 + 菜单
            if (!taskEditMode) Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // 目标选择器
                var targetDropdown by remember { mutableStateOf(false) }
                TextButton(onClick = {
                    onRefreshIdeStatus()
                    targetDropdown = true
                }, contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        TargetIcon(currentTarget, size = 16.dp)
                        Text(currentTarget.label, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelMedium)
                        Icon(Icons.Default.ArrowDropDown, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(16.dp))
                    }
                    val visibleTargets = buildList {
                        add(AideLinkChatViewModel.Target.AIDELINK)
                        for (key in selectedIdeList) {
                            if (key == "aide") continue
                            val target = AideLinkChatViewModel.Target.fromKey(key)
                            if (target.key != "aide") add(target)
                        }
                        if (none { it.key == "oc_web" }) add(AideLinkChatViewModel.Target.OPENCODE_WEB)
                    }
                    DropdownMenu(
                        expanded = targetDropdown,
                        onDismissRequest = { targetDropdown = false }
                    ) {
                        visibleTargets.forEach { t ->
                            val isIdeTarget = t.key != "aide"
                            val isOcWeb = t.key == "oc_web"
                            val isRunning = if (isOcWeb) ocWebRunning else (ideRunningMap[t.key] ?: false)
                            DropdownMenuItem(
                                text = {
                                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        TargetIcon(t, size = 16.dp)
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(t.label)
                                            if (isIdeTarget) {
                                                Text(
                                                    if (isRunning) "运行中" else "未运行",
                                                    style = MaterialTheme.typography.labelSmall,
                                                    color = if (isRunning) Color(0xFF4CAF50) else MaterialTheme.colorScheme.onSurfaceVariant
                                                )
                                            }
                                        }
                                        if (isIdeTarget) {
                                            Switch(
                                                checked = isRunning,
                                                onCheckedChange = { checked ->
                                                    if (isOcWeb) {
                                                        onOcWebToggle()
                                                    } else {
                                                        if (checked) onStartIde(t.key) else onStopIde(t.key)
                                                    }
                                                },
                                                modifier = Modifier.height(24.dp)
                                            )
                                        }
                                    }
                                },
                                onClick = {
                                    onTargetChange(t)
                                    targetDropdown = false
                                }
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.weight(1f))

                // OC Web 启停开关 + 打开Web / 其他 IDE 监控开关
                if (currentTarget == AideLinkChatViewModel.Target.OPENCODE_WEB) {
                    IconButton(onClick = onOpenWeb, modifier = Modifier.size(32.dp)) {
                        Icon(
                            Icons.Default.OpenInNew,
                            contentDescription = "打开完整 Web",
                            modifier = Modifier.size(16.dp),
                            tint = MaterialTheme.colorScheme.primary
                        )
                    }
                    IconButton(onClick = onOcWebToggle, modifier = Modifier.size(32.dp)) {
                        Icon(
                            if (ocWebRunning) Icons.Default.Stop else Icons.Default.PlayArrow,
                            contentDescription = if (ocWebRunning) "停止 OC Web" else "启动 OC Web",
                            modifier = Modifier.size(16.dp),
                            tint = if (ocWebRunning) Color(0xFFE57373) else Color(0xFF81C784)
                        )
                    }
                } else {
                    IconButton(onClick = { onMonitorToggle(currentTarget) }, modifier = Modifier.size(32.dp)) {
                        Icon(
                            Icons.Default.Tv,
                            contentDescription = if (monitorByTarget[currentTarget] == true) "关闭监控" else "开启监控",
                            modifier = Modifier.size(16.dp),
                            tint = if (monitorByTarget[currentTarget] == true) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                // 更多菜单
                var menuExpanded by remember { mutableStateOf(false) }
                IconButton(onClick = { menuExpanded = true }, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Default.Add, contentDescription = "更多", modifier = Modifier.size(18.dp))
                    DropdownMenu(
                        expanded = menuExpanded,
                        onDismissRequest = { menuExpanded = false }
                    ) {
                        DropdownMenuItem(
                            text = { Text("🔄 刷新任务") },
                            leadingIcon = { Icon(Icons.Default.Refresh, contentDescription = null) },
                            onClick = { onRefreshTasks(); menuExpanded = false }
                        )
                        HorizontalDivider()
                        if (currentTarget == AideLinkChatViewModel.Target.AIDELINK) {
                            DropdownMenuItem(
                                text = { Text("➕ 新开会话") },
                                leadingIcon = { Icon(Icons.Default.Add, contentDescription = null) },
                                onClick = { onCreateNewSession(); menuExpanded = false }
                            )
                            HorizontalDivider()
                        }
                        DropdownMenuItem(
                            text = { Text("🗺️ 项目地图 (${if (projectMapExpanded) "已开启" else "已关闭"})") },
                            leadingIcon = { Icon(Icons.Default.FolderOpen, contentDescription = null) },
                            onClick = { onToggleProjectMap(); menuExpanded = false }
                        )
                        DropdownMenuItem(
                            text = { Text("🎯 标记定位") },
                            leadingIcon = { Icon(Icons.Default.OpenInBrowser, contentDescription = null) },
                            onClick = { onStartUiLocator(); menuExpanded = false }
                        )
                        HorizontalDivider()
                        DropdownMenuItem(
                            text = { Text("唤醒电脑屏幕") },
                            leadingIcon = { Icon(Icons.Default.Lightbulb, contentDescription = null, tint = Color(0xFFFFC107)) },
                            onClick = { onWakeScreen(); menuExpanded = false }
                        )
                        HorizontalDivider()
                        DropdownMenuItem(
                            text = { Text("剪贴板") },
                            leadingIcon = { Icon(Icons.Default.ContentPaste, contentDescription = null) },
                            onClick = { onClipboard(); menuExpanded = false }
                        )

                    }
                }

                if (showQuickReplyManager) {
                    QuickReplyManagerDialog(
                        quickReplies = quickReplies,
                        onAdd = onAddQuickReply,
                        onRemove = onRemoveQuickReply,
                        onDismiss = { showQuickReplyManager = false }
                    )
                }
            }

            // 输入行
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                var isFocused by remember { mutableStateOf(false) }

                // 对话框左侧快捷回复按钮
                var quickReplyDropdownExpanded by remember { mutableStateOf(false) }
                Box {
                    IconButton(
                        onClick = { quickReplyDropdownExpanded = true },
                        modifier = Modifier.size(36.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.FlashOn,
                            contentDescription = "快捷回复",
                            tint = MaterialTheme.colorScheme.primary
                        )
                    }
                    DropdownMenu(
                        expanded = quickReplyDropdownExpanded,
                        onDismissRequest = { quickReplyDropdownExpanded = false }
                    ) {
                        if (quickReplies.isEmpty()) {
                            DropdownMenuItem(
                                text = { Text("暂无快捷回复") },
                                onClick = { quickReplyDropdownExpanded = false }
                            )
                        } else {
                            quickReplies.forEach { reply ->
                                DropdownMenuItem(
                                    text = { Text(reply, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                                    leadingIcon = { Icon(Icons.Default.FlashOn, contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
                                    onClick = {
                                        onQuickReply(reply)
                                        quickReplyDropdownExpanded = false
                                    }
                                )
                            }
                        }
                        HorizontalDivider()
                        DropdownMenuItem(
                            text = { Text("管理快捷回复") },
                            leadingIcon = { Icon(Icons.Default.Edit, contentDescription = null) },
                            onClick = {
                                showQuickReplyManager = true
                                quickReplyDropdownExpanded = false
                            }
                        )
                    }
                }

                Spacer(modifier = Modifier.width(4.dp))

                val borderColor = when {
                    bridgeConnecting -> Color(0xFFFFC107)
                    !bridgeOnline -> Color(0xFFF44336)
                    else -> Color(0xFF4CAF50)
                }
                OutlinedTextField(
                    value = input,
                    onValueChange = onInputChange,
                    placeholder = {
                        Text(
                            when {
                                taskEditMode -> "修改任务内容…"
                                taskThreadMode -> "补充到当前任务…"
                                else -> "发消息…"
                            }
                        )
                    },
                    modifier = Modifier
                        .weight(1f)
                        .onFocusChanged { isFocused = it.isFocused },
                    singleLine = false,
                    maxLines = 2,
                    shape = RoundedCornerShape(18.dp),
                    textStyle = MaterialTheme.typography.bodyLarge,
                    colors = OutlinedTextFieldDefaults.colors(
                        unfocusedBorderColor = borderColor.copy(alpha = 0.6f),
                        focusedBorderColor = borderColor,
                    ),
                )

                Spacer(modifier = Modifier.width(6.dp))

                if (taskEditMode) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        IconButton(
                            onClick = {
                                onOptimizeTaskPrompt()
                                focusManager.clearFocus()
                            },
                            enabled = input.isNotBlank() && !sending,
                            modifier = Modifier.size(36.dp),
                        ) {
                            Icon(
                                Icons.Default.AutoAwesome,
                                contentDescription = "AI 优化",
                                modifier = Modifier.size(18.dp),
                                tint = if (input.isNotBlank()) Color(0xFF9C27B0) else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                            )
                        }
                        IconButton(
                            onClick = {
                                onSaveTaskEdit()
                                focusManager.clearFocus()
                            },
                            enabled = input.isNotBlank() && !sending,
                            modifier = Modifier.size(36.dp),
                        ) {
                            Icon(
                                Icons.Default.Check,
                                contentDescription = "保存修改",
                                modifier = Modifier.size(18.dp),
                                tint = if (input.isNotBlank()) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                            )
                        }
                        IconButton(
                            onClick = {
                                onCancelTaskEdit()
                                focusManager.clearFocus()
                            },
                            modifier = Modifier.size(36.dp),
                        ) {
                            Icon(
                                Icons.Default.Close,
                                contentDescription = "取消修改",
                                modifier = Modifier.size(18.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                } else if (!isFocused) {
                    // 没有点击对话框时：右侧发送按钮隐藏，将顶部的任务和对话切换按钮移下来
                    IconButton(
                        onClick = onToggleTaskList,
                        modifier = Modifier.size(36.dp)
                    ) {
                        Icon(
                            imageVector = if (showTaskList) Icons.Default.Chat else Icons.Default.FormatListBulleted,
                            contentDescription = "切换视图",
                            modifier = Modifier.size(18.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                } else {
                    // 点击对话框后：隐藏切换按钮，显示为 AI 优化 + 发送 + 添加到任务列表
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        // AI 优化提示词按钮
                        IconButton(
                            onClick = {
                                onOptimizeTaskPrompt()
                                focusManager.clearFocus()
                            },
                            enabled = input.isNotBlank() && !sending,
                            modifier = Modifier.size(36.dp),
                        ) {
                            Icon(
                                Icons.Default.AutoAwesome,
                                contentDescription = "AI 优化",
                                modifier = Modifier.size(18.dp),
                                tint = if (input.isNotBlank()) Color(0xFF9C27B0) else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                            )
                        }
                        // 直接发送按钮
                        IconButton(
                            onClick = {
                                onSend()
                                focusManager.clearFocus()
                            },
                            enabled = input.isNotBlank() && !sending,
                            modifier = Modifier.size(36.dp),
                        ) {
                            if (sending) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    strokeWidth = 1.5.dp,
                                )
                            } else {
                                Icon(
                                    imageVector = Icons.Default.Send,
                                    contentDescription = if (isPromptMode) "发送提示词" else "发送",
                                    modifier = Modifier.size(18.dp),
                                    tint = if (input.isNotBlank()) {
                                        if (isPromptMode) Color(0xFF9C27B0) else MaterialTheme.colorScheme.primary
                                    } else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                                )
                            }
                        }

                        // 添加到任务列表按钮
                        // 任务是显式动作，不依赖目标或网络状态；普通发送仍保持为聊天。
                        if (!taskThreadMode) {
                            IconButton(
                                onClick = {
                                    onSendToTaskList()
                                    focusManager.clearFocus()
                                },
                                enabled = input.isNotBlank() && !sending,
                                modifier = Modifier.size(36.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.PlaylistAdd,
                                    contentDescription = "添加到任务",
                                    modifier = Modifier.size(18.dp),
                                    tint = if (input.isNotBlank()) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

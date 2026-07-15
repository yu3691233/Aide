package cc.aidelink.app.ui.screens.chat.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.MoreHoriz
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import cc.aidelink.app.data.api.BridgeApi
import cc.aidelink.app.domain.model.bridge.DesktopIde
import cc.aidelink.app.ui.screens.chat.AideLinkChatViewModel
import cc.aidelink.app.ui.screens.chat.TargetIcon

@Composable
fun IdeControlDialog(
    currentTarget: AideLinkChatViewModel.Target,
    ides: List<DesktopIde>,
    desktopIdesLoading: Boolean,
    ideRunningMap: Map<String, Boolean>,
    projects: List<BridgeApi.ProjectInfo>,
    currentProjectPath: String,
    onRefresh: () -> Unit,
    onScan: () -> Unit,
    onStart: (String) -> Unit,
    onStop: (String) -> Unit,
    onSwitchProject: (String, String) -> Unit,
    onUpdateProfile: (String) -> Unit,
    historySessions: List<cc.aidelink.app.domain.model.bridge.IdeHistorySession>,
    historyLoading: Boolean,
    onLoadHistory: (String) -> Unit,
    onOpenHistory: (String, String) -> Unit,
    onInstallMcp: (String) -> Unit,
    onBindWindow: (String) -> Unit,
    onCalibrate: (String) -> Unit,
    ocWebRunning: Boolean,
    onOcWebToggle: () -> Unit,
    onOpenSessions: () -> Unit,
    onOpenWeb: () -> Unit,
    onDismiss: () -> Unit,
) {
    var showProjectMenu by remember { mutableStateOf(false) }
    var showMore by remember { mutableStateOf(false) }
    var showHistory by remember { mutableStateOf(false) }
    var pendingCloseIde by remember { mutableStateOf<DesktopIde?>(null) }

    val selectedIde = ides.firstOrNull { it.key == currentTarget.key }
    val isRunning = selectedIde?.let { ideRunningMap[it.key] ?: it.running } ?: false

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (showHistory) {
                    IconButton(onClick = { showHistory = false }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "返回")
                    }
                }
                Text(if (showHistory) "历史会话" else "目标与 IDE", fontWeight = FontWeight.Bold)
            }
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                if (showHistory && selectedIde != null) {
                    if (historyLoading) {
                        Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    } else if (historySessions.isEmpty()) {
                        Text("没有找到历史会话。", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        OutlinedButton(
                            onClick = { onLoadHistory(selectedIde.key) },
                            modifier = Modifier.fillMaxWidth(),
                        ) { Icon(Icons.Default.Refresh, null); Spacer(Modifier.width(6.dp)); Text("重新读取") }
                    } else {
                        historySessions.forEach { session ->
                            Surface(
                                onClick = {
                                    onOpenHistory(selectedIde.key, session.id)
                                    onDismiss()
                                },
                                shape = MaterialTheme.shapes.medium,
                                color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f),
                            ) {
                                Column(Modifier.fillMaxWidth().padding(12.dp)) {
                                    Text(
                                        session.title.ifBlank { "未命名会话" },
                                        fontWeight = FontWeight.Medium,
                                        maxLines = 2,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                    if (session.updated_at.isNotBlank()) {
                                        Text(
                                            session.updated_at.replace('T', ' ').take(16),
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                    }
                                }
                            }
                        }
                    }
                } else {
                    when {
                    desktopIdesLoading && currentTarget.key != "aide" && currentTarget.key != "oc_web" -> {
                        Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    }
                    currentTarget.key == "aide" -> Text(
                        "Aide 是内置助手，不需要单独启动或关闭。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    currentTarget.key == "oc_web" -> {
                        ElevatedCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text("OpenCode", fontWeight = FontWeight.SemiBold)
                                Text(if (ocWebRunning) "● 运行中" else "○ 未运行")
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Button(onClick = onOpenSessions, modifier = Modifier.weight(1f), enabled = ocWebRunning) { Text("会话") }
                                    OutlinedButton(onClick = onOpenWeb, modifier = Modifier.weight(1f), enabled = ocWebRunning) { Text("Web 界面") }
                                }
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    OutlinedButton(
                                        onClick = onOcWebToggle,
                                        modifier = Modifier.weight(1f),
                                        enabled = !ocWebRunning,
                                    ) { Text("启动服务") }
                                    OutlinedButton(
                                        onClick = onOcWebToggle,
                                        modifier = Modifier.weight(1f),
                                        enabled = ocWebRunning,
                                        colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                                    ) { Text("停止服务") }
                                }
                            }
                        }
                    }
                    selectedIde == null -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            "当前目标尚未出现在桌面 IDE 扫描结果中。",
                            color = MaterialTheme.colorScheme.error,
                        )
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = onRefresh, modifier = Modifier.weight(1f)) { Text("刷新列表") }
                            Button(onClick = onScan, modifier = Modifier.weight(1f)) { Text("重新扫描") }
                        }
                    }
                    else -> {
                        ElevatedCard(Modifier.fillMaxWidth()) {
                            Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                                TargetIcon(currentTarget, size = 28.dp)
                                Spacer(Modifier.width(10.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(selectedIde.name.ifBlank { selectedIde.key }, fontWeight = FontWeight.SemiBold)
                                    Text(
                                        if (isRunning) "● 运行中" else "○ 未运行",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = if (isRunning) Color(0xFF4CAF50) else MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                                if (selectedIde.profile_version.isNotBlank()) {
                                    Text("v${selectedIde.profile_version}", style = MaterialTheme.typography.labelSmall)
                                }
                            }
                        }

                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if ("launch" in selectedIde.capabilities) {
                                Button(onClick = { onStart(selectedIde.key) }, modifier = Modifier.weight(1f)) {
                                    Icon(Icons.Default.PlayArrow, null)
                                    Spacer(Modifier.width(4.dp))
                                    Text(if (isRunning) "激活" else "启动")
                                }
                            }
                            if ("history" in selectedIde.capabilities) {
                                OutlinedButton(
                                    onClick = {
                                        showHistory = true
                                        onLoadHistory(selectedIde.key)
                                    },
                                    modifier = Modifier.weight(1f),
                                ) {
                                    Icon(Icons.Default.History, null)
                                    Spacer(Modifier.width(4.dp))
                                    Text("历史会话")
                                }
                            }
                        }

                        if ("open_project" in selectedIde.capabilities) {
                            Text("目标项目", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Box {
                                OutlinedButton(
                                    onClick = { showProjectMenu = true },
                                    modifier = Modifier.fillMaxWidth(),
                                ) {
                                    val currentName = projects.firstOrNull { it.path == currentProjectPath }?.name
                                    Text(currentName?.ifBlank { currentProjectPath } ?: currentProjectPath.ifBlank { "选择项目" }, modifier = Modifier.weight(1f))
                                    Icon(Icons.Default.ArrowDropDown, contentDescription = null)
                                }
                                DropdownMenu(
                                    expanded = showProjectMenu,
                                    onDismissRequest = { showProjectMenu = false },
                                ) {
                                    projects.forEach { project ->
                                        DropdownMenuItem(
                                            text = {
                                                Column {
                                                    Text(project.name.ifBlank { project.path.substringAfterLast('\\') })
                                                    Text(project.path, style = MaterialTheme.typography.labelSmall)
                                                }
                                            },
                                            onClick = {
                                                onSwitchProject(selectedIde.key, project.path)
                                                showProjectMenu = false
                                            },
                                        )
                                    }
                                }
                            }
                        }

                        TextButton(onClick = { showMore = !showMore }, modifier = Modifier.align(Alignment.End)) {
                            Icon(Icons.Default.MoreHoriz, null)
                            Spacer(Modifier.width(4.dp))
                            Text(if (showMore) "收起" else "更多功能")
                        }

                        if (showMore) {
                            HorizontalDivider()
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedButton(onClick = onRefresh, modifier = Modifier.weight(1f)) { Text("刷新状态") }
                                OutlinedButton(onClick = onScan, modifier = Modifier.weight(1f)) { Text("重新扫描") }
                            }
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                if ("bind_window" in selectedIde.capabilities) {
                                    TextButton(onClick = { onBindWindow(selectedIde.key) }, modifier = Modifier.weight(1f)) { Text("绑定窗口") }
                                }
                                if ("calibrate" in selectedIde.capabilities) {
                                    TextButton(onClick = { onCalibrate(selectedIde.key) }, modifier = Modifier.weight(1f)) { Text("校准监控") }
                                }
                            }
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                if ("install_mcp" in selectedIde.capabilities) {
                                    TextButton(onClick = { onInstallMcp(selectedIde.key) }, modifier = Modifier.weight(1f)) { Text("安装 MCP") }
                                }
                                if ("profile_update" in selectedIde.capabilities) {
                                    TextButton(onClick = { onUpdateProfile(selectedIde.key) }, modifier = Modifier.weight(1f)) { Text("更新适配") }
                                }
                            }
                            if ("stop" in selectedIde.capabilities) {
                                TextButton(
                                    onClick = { pendingCloseIde = selectedIde },
                                    modifier = Modifier.fillMaxWidth(),
                                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                                ) { Text("关闭 IDE") }
                            }
                        }
                    }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("关闭") }
        }
    )

    pendingCloseIde?.let { ide ->
        AlertDialog(
            onDismissRequest = { pendingCloseIde = null },
            title = { Text("确认关闭 ${ide.name.ifBlank { ide.key }}？") },
            text = { Text("关闭是独立操作，不再作为启动按钮的开关状态。IDE 会先收到正常关闭请求。") },
            confirmButton = {
                TextButton(
                    onClick = {
                        onStop(ide.key)
                        pendingCloseIde = null
                    },
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                ) { Text("关闭 IDE") }
            },
            dismissButton = { TextButton(onClick = { pendingCloseIde = null }) { Text("取消") } },
        )
    }
}

@Composable
fun QuickReplyManagerDialog(
    quickReplies: List<String>,
    onAdd: (String) -> Unit,
    onRemove: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var newText by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("管理快捷回复", fontWeight = FontWeight.Bold) },
        text = {
            Column(modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedTextField(
                        value = newText,
                        onValueChange = { newText = it },
                        placeholder = { Text("输入快捷回复") },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        textStyle = MaterialTheme.typography.bodyMedium,
                    )
                    IconButton(
                        onClick = {
                            if (newText.isNotBlank()) {
                                onAdd(newText.trim())
                                newText = ""
                            }
                        },
                        enabled = newText.isNotBlank()
                    ) {
                        Icon(Icons.Default.Add, contentDescription = "添加")
                    }
                }
                Spacer(modifier = Modifier.height(12.dp))
                if (quickReplies.isEmpty()) {
                    Text(
                        "暂无快捷回复",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall
                    )
                } else {
                    quickReplies.forEach { reply ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 2.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                reply,
                                modifier = Modifier.weight(1f),
                                style = MaterialTheme.typography.bodySmall,
                                maxLines = 1
                            )
                            IconButton(
                                onClick = { onRemove(reply) },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(
                                    Icons.Default.Close,
                                    contentDescription = "删除",
                                    modifier = Modifier.size(14.dp),
                                    tint = MaterialTheme.colorScheme.error
                                )
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text("完成")
            }
        }
    )
}

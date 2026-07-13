package cc.aidelink.app.ui.screens.chat.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cc.aidelink.app.domain.model.bridge.DesktopIde

@Composable
fun DesktopIdeManagerDialog(
    ides: List<DesktopIde>,
    ideRunningMap: Map<String, Boolean>,
    onRefresh: () -> Unit,
    onScan: () -> Unit,
    onBrowse: ((String?) -> Unit) -> Unit,
    onAdd: (String, String, String, (Boolean) -> Unit) -> Unit,
    onRemove: (String) -> Unit,
    onStart: (String) -> Unit,
    onStop: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var showAdd by remember { mutableStateOf(false) }
    var key by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var path by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("桌面 IDE 管理", fontWeight = FontWeight.Bold) },
        text = {
            Column(modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    OutlinedButton(onClick = onRefresh) { Text("刷新 IDE 列表") }
                }
                Spacer(modifier = Modifier.height(12.dp))
                if (ides.isEmpty()) {
                    Text("暂无可用 IDE，请在电脑管理端扫描或添加", color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .verticalScroll(rememberScrollState()),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        ides.forEach { ide ->
                            val isRunning = ideRunningMap[ide.key] ?: false
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(ide.name.ifBlank { ide.key }, fontWeight = FontWeight.SemiBold)
                                    Text(
                                        text = if (ide.path.isNotBlank()) ide.path else "(未配置路径)",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = if (ide.path.isNotBlank()) MaterialTheme.colorScheme.onSurfaceVariant
                                        else Color(0xFFFF6B6B),
                                    )
                                    Text(
                                        text = if (isRunning) "运行中" else "未运行",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = if (isRunning) Color(0xFF4CAF50) else MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                                Button(
                                    onClick = { if (isRunning) onStop(ide.key) else onStart(ide.key) },
                                    modifier = Modifier.height(32.dp),
                                ) {
                                    Text(if (isRunning) "停止" else "启动", style = MaterialTheme.typography.labelMedium)
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

    if (showAdd) {
        AlertDialog(
            onDismissRequest = { showAdd = false },
            title = { Text("添加 IDE", fontWeight = FontWeight.Bold) },
            text = {
                Column(modifier = Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = key,
                        onValueChange = { key = it },
                        label = { Text("英文键名 (如 trae / mimo)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it },
                        label = { Text("显示名称") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = path,
                        onValueChange = { path = it },
                        label = { Text("可执行文件路径 (.exe)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        trailingIcon = {
                            IconButton(onClick = { onBrowse { p -> if (!p.isNullOrBlank()) path = p } }) {
                                Icon(Icons.Default.Folder, contentDescription = "选择文件")
                            }
                        }
                    )
                    Text(
                        text = "提示：也可在桌面端打开文件选择器选择 exe，或直接手动输入路径",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        if (key.isNotBlank() && name.isNotBlank() && path.isNotBlank()) {
                            onAdd(key.trim(), name.trim(), path.trim()) { ok ->
                                if (ok) showAdd = false
                            }
                        }
                    }
                ) { Text("保存") }
            },
            dismissButton = { TextButton(onClick = { showAdd = false }) { Text("取消") } }
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

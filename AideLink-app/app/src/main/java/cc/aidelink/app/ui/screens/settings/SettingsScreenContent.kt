package cc.aidelink.app.ui.screens.settings

import android.content.Context
import android.net.Uri
import android.provider.Settings
import android.widget.Toast
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Android
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Computer
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Language
import androidx.compose.material.icons.filled.LocationSearching
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.PhoneAndroid
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.RadioButtonChecked
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import cc.aidelink.app.BuildConfig
import cc.aidelink.app.data.api.BridgeApi
import kotlinx.coroutines.launch

internal fun LazyListScope.tabConnectionItems(
    state: AideLinkSettingsViewModel.UiState,
    serverUrl: String,
    viewModel: AideLinkSettingsViewModel,
    context: Context,
    xiaomenglingModel: String,
    desktopIde: String,
    desktopIdeList: List<String>,
) {
    item {
        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
            ),
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(modifier = Modifier.size(12.dp).background(
                    if (serverUrl.isNotBlank()) Color(0xFF4CAF50) else Color(0xFFF44336), CircleShape))
                Spacer(modifier = Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text("连接状态", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    Text(serverUrl.ifBlank { "未连接" }, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                }
                Surface(shape = RoundedCornerShape(12.dp),
                    color = if (serverUrl.contains("cciv.cc")) Color(0xFFFF9800).copy(alpha = 0.15f)
                    else MaterialTheme.colorScheme.secondaryContainer) {
                    Text(
                        if (serverUrl.isBlank()) "未连接"
                        else if (serverUrl.contains("cciv.cc")) "FRP"
                        else if (serverUrl.contains("192.168") || serverUrl.contains("10.")) "LAN"
                        else "远程",
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.labelSmall,
                        color = if (serverUrl.contains("cciv.cc")) Color(0xFFFF9800)
                        else MaterialTheme.colorScheme.onSecondaryContainer,
                        fontWeight = FontWeight.Medium
                    )
                }
            }
        }
    }
    item {
        if (serverUrl.isNotBlank()) {
            Surface(modifier = Modifier.fillMaxWidth().clickable { viewModel.forceRestartServer() },
                shape = RoundedCornerShape(8.dp),
                color = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)) {
                Row(modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.SystemUpdate, contentDescription = null,
                        modifier = Modifier.size(16.dp), tint = MaterialTheme.colorScheme.error)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("强杀重启服务器", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.Medium)
                }
            }
        }
    }
    item { Spacer(modifier = Modifier.height(4.dp)) }
    item {
        ServerListSection(
            servers = state.bridgeServers,
            activeServerId = state.activeServerId,
            currentUrl = serverUrl,
            isScanning = state.isScanning,
            scanMessage = state.scanMessage,
            onSwitchServer = { viewModel.setActiveServer(it) },
            onDeleteServer = { viewModel.deleteBridgeServer(it) },
            onAddServer = { name, url, type -> viewModel.addBridgeServer(name, url, type) },
            onEditServer = { viewModel.updateBridgeServer(it) },
            onScan = { viewModel.scanLocalServers() },
            onScanQr = {}
        )
    }
    item { Spacer(modifier = Modifier.height(8.dp)) }
    item { SectionTitle("目标项目", Icons.Default.Folder) }
    item {
        val showManualInput = remember { mutableStateOf(false) }
        val manualPath = remember { mutableStateOf("") }
        var showDeleteDialog by remember { mutableStateOf<Int?>(null) }

        Card(shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("选择当前开发的项目", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Row {
                        IconButton(onClick = { viewModel.browseAndAddProject() }) {
                            Icon(Icons.Default.FolderOpen, contentDescription = "扫描并选择项目目录", modifier = Modifier.size(20.dp))
                        }
                        IconButton(onClick = { viewModel.loadProjects() }) {
                            if (state.isLoadingProjects) {
                                CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                            } else {
                                Icon(Icons.Default.Search, contentDescription = "刷新", modifier = Modifier.size(20.dp))
                            }
                        }
                        IconButton(onClick = { showManualInput.value = !showManualInput.value }) {
                            Icon(Icons.Default.Add, contentDescription = "添加", modifier = Modifier.size(20.dp))
                        }
                    }
                }

                if (state.projects.isEmpty() && !state.isLoadingProjects) {
                    Text("暂无项目，点击 + 添加",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(vertical = 12.dp))
                }

                state.projects.forEachIndexed { idx, proj ->
                    val displayPath = normalizeWindowsPath(proj.path)
                    val isCurrent = displayPath.equals(normalizeWindowsPath(state.currentProjectPath), ignoreCase = true)
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 3.dp)
                            .clickable { if (!isCurrent) viewModel.selectProjectAndRefresh(displayPath, navigateBack = true) },
                        shape = RoundedCornerShape(8.dp),
                        color = if (isCurrent) MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.4f)
                                else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f),
                        border = if (isCurrent) androidx.compose.foundation.BorderStroke(1.5.dp, MaterialTheme.colorScheme.primary)
                                 else null,
                    ) {
                        Row(modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(modifier = Modifier.weight(1f)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(proj.name.ifBlank { "未命名" }, fontWeight = FontWeight.Medium, style = MaterialTheme.typography.bodyMedium)
                                    if (isCurrent) {
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Surface(shape = RoundedCornerShape(4.dp), color = MaterialTheme.colorScheme.primary) {
                                            Text("当前", modifier = Modifier.padding(horizontal = 6.dp, vertical = 1.dp),
                                                style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onPrimary, fontWeight = FontWeight.Bold)
                                        }
                                    }
                                }
                                Text(displayPath, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                                if (proj.android.is_android) {
                                    Text(
                                        if (proj.android.apks.isEmpty()) "Android · 未发现 APK" else "Android · ${proj.android.apks.size} 个 APK",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.primary,
                                    )
                                }
                            }
                            IconButton(onClick = { showDeleteDialog = idx }, modifier = Modifier.size(32.dp)) {
                                Icon(Icons.Default.Delete, contentDescription = "删除", modifier = Modifier.size(18.dp), tint = MaterialTheme.colorScheme.error.copy(alpha = 0.7f))
                            }
                        }
                    }
                }

                if (showManualInput.value) {
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedTextField(value = manualPath.value, onValueChange = { manualPath.value = normalizeWindowsPath(it) },
                        label = { Text("项目路径 (如 D:\\Projects\\AideLink)") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    Spacer(modifier = Modifier.height(8.dp))
                    Button(onClick = {
                        val path = normalizeWindowsPath(manualPath.value)
                        if (path.isNotBlank()) { viewModel.selectProjectAndRefresh(path, navigateBack = true); manualPath.value = ""; showManualInput.value = false }
                    }, modifier = Modifier.fillMaxWidth(), enabled = manualPath.value.isNotBlank()) { Text("确认添加") }
                }
            }
        }

        showDeleteDialog?.let { deleteIdx ->
            val projName = state.projects.getOrNull(deleteIdx)?.name ?: ""
            AlertDialog(
                onDismissRequest = { showDeleteDialog = null },
                title = { Text("删除项目") },
                text = { Text("确定要删除关联项目 \"$projName\" 吗？\n（项目文件不会被删除）") },
                confirmButton = { TextButton(onClick = { viewModel.deleteProject(deleteIdx); showDeleteDialog = null }) { Text("删除", color = MaterialTheme.colorScheme.error) } },
                dismissButton = { TextButton(onClick = { showDeleteDialog = null }) { Text("取消") } }
            )
        }
    }
    item { Spacer(modifier = Modifier.height(8.dp)) }
    item {
        Button(onClick = {
            viewModel.save(serverUrl)
            viewModel.saveXiaomenglingModel(xiaomenglingModel)
            viewModel.saveDesktopIdeList(desktopIdeList)
        }, modifier = Modifier.fillMaxWidth().height(48.dp),
            shape = RoundedCornerShape(12.dp)) { Text("保存设置", fontWeight = FontWeight.Bold) }
    }
}

internal fun LazyListScope.tabAiItems(
    state: AideLinkSettingsViewModel.UiState,
    viewModel: AideLinkSettingsViewModel,
    currentModel: String,
) {
    item { SectionTitle("AI 模型", Icons.Default.SmartToy) }
    item {
        Card(shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("当消息未派发到 IDE 时使用的模型", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(bottom = 12.dp))
                var expanded by remember { mutableStateOf(false) }
                Box(modifier = Modifier.fillMaxWidth()) {
                    OutlinedTextField(
                        value = state.availableModels.find { it.key == currentModel }?.description ?: currentModel,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("当前模型") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .clickable { expanded = true }
                    )
                    DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                        state.availableModels.forEach { model ->
                            DropdownMenuItem(
                                text = { Text(model.description.ifBlank { model.key }) },
                                onClick = {
                                    viewModel.saveXiaomenglingModel(model.key)
                                    expanded = false
                                }
                            )
                        }
                    }
                }
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedButton(onClick = { viewModel.refreshModels() }, modifier = Modifier.fillMaxWidth()) { Text("刷新模型列表") }
            }
        }
    }
    item { SectionTitle("桌面 IDE", Icons.Default.Computer) }
    item {
        Card(shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.padding(16.dp)) {
                state.availableIdes.forEach { ide ->
                    val isChecked = state.desktopIdeList.contains(ide.key)
                    Row(modifier = Modifier.fillMaxWidth().clickable {
                        val newList = if (isChecked) state.desktopIdeList - ide.key else state.desktopIdeList + ide.key
                        viewModel.saveDesktopIdeList(newList)
                    }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = isChecked, onCheckedChange = { checked ->
                            val newList = if (checked) state.desktopIdeList + ide.key else state.desktopIdeList - ide.key
                            viewModel.saveDesktopIdeList(newList)
                        })
                        Spacer(modifier = Modifier.width(8.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(ide.name, fontWeight = FontWeight.Medium)
                            if (ide.path.isNotBlank()) Text(ide.path, style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2,
                                overflow = TextOverflow.Ellipsis)
                            OutlinedButton(
                                onClick = { viewModel.forceStopIde(ide.key) },
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                                modifier = Modifier.padding(top = 4.dp),
                            ) { Text("强制关闭", style = MaterialTheme.typography.labelSmall) }
                        }
                        TextButton(onClick = { viewModel.requestIdeCalibration(ide.key) }) { Text("校准监控") }
                        TextButton(onClick = { viewModel.installIdeMcp(ide.key) }) { Text("安装 MCP") }
                        TextButton(onClick = { viewModel.removeIde(ide.key) }) { Text("删除", color = Color(0xFFE5534B)) }
                    }
                }
                OutlinedButton(onClick = { viewModel.addIdeFromDesktop() }, modifier = Modifier.fillMaxWidth()) {
                    Text("添加 IDE（电脑端选择）")
                }
                OutlinedButton(onClick = { viewModel.refreshIdes() }, modifier = Modifier.fillMaxWidth()) { Text("刷新") }
            }
        }
    }
    item { SectionTitle("OpenCode Web", Icons.Default.Language) }
    item {
        Card(shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.padding(16.dp)) {
                var connectionType by remember(state.opencodeWebConnection) { mutableStateOf(state.opencodeWebConnection) }
                var ocPass by remember(state.opencodeWebPassword) { mutableStateOf(state.opencodeWebPassword) }

                Text("连接方式", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(modifier = Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = connectionType == "lan", onClick = { connectionType = "lan" }, label = { Text("局域网") })
                    FilterChip(selected = connectionType == "frp", onClick = { connectionType = "frp" }, label = { Text("FRP 内网穿透") })
                }
                if (connectionType == "frp") {
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedTextField(value = ocPass, onValueChange = { ocPass = it }, label = { Text("密码") },
                        modifier = Modifier.fillMaxWidth(), singleLine = true)
                }
                Spacer(modifier = Modifier.height(12.dp))
                Button(onClick = { viewModel.saveOpenCodeWebSettings(connectionType, ocPass, state.opencodeProjectDir) }, modifier = Modifier.fillMaxWidth()) { Text("保存") }
            }
        }
    }
}

internal fun LazyListScope.tabToolsItems(
    state: AideLinkSettingsViewModel.UiState,
    viewModel: AideLinkSettingsViewModel,
    context: Context,
    serverUrl: String = "",
) {
    val currentProject = state.projects.firstOrNull {
        normalizeWindowsPath(it.path).equals(normalizeWindowsPath(state.currentProjectPath), ignoreCase = true)
    }
    item { SectionTitle("当前项目 Android 应用", Icons.Default.Android) }
    item {
        Card(shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                if (currentProject == null) {
                    Text("请先在“连接”页选择目标项目", color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    Text(currentProject.name, fontWeight = FontWeight.Bold)
                    Text(currentProject.path, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(modifier = Modifier.height(8.dp))
                    when {
                        !currentProject.android.is_android -> Text("未识别到 Android 工程", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        currentProject.android.apks.isEmpty() -> Text("已识别 Android 工程，但尚未发现 APK，请先编译应用。", color = MaterialTheme.colorScheme.tertiary)
                        else -> currentProject.android.apks.forEach { apk ->
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(apk.name, fontWeight = FontWeight.Medium)
                                    Text("${apk.module} · ${apk.variant}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                                Button(onClick = { viewModel.adbProjectInstall(apk.path) }, enabled = !state.isAdbInstalling && state.isLan) {
                                    Text("安装")
                                }
                            }
                        }
                    }
                    state.androidInstallStatus?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall) }
                    state.androidInstallError?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                    if (state.isAdbInstalling) LinearProgressIndicator(modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedButton(onClick = { viewModel.scanCurrentAndroidProject() }, modifier = Modifier.fillMaxWidth(), enabled = !state.isAdbInstalling) {
                        Text("重新扫描 Android 工程与 APK")
                    }
                    if (!state.isLan) {
                        Text("项目 APK 安装仅在局域网连接下可用", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
    item { SectionTitle("无线调试 (ADB)", Icons.Default.PhoneAndroid) }
    item {
        val adbStatus = remember { mutableStateOf<cc.aidelink.app.service.WirelessAdbManager.AdbStatus?>(null) }
        val scope = rememberCoroutineScope()
        fun updateAdbStatus() {
            scope.launch {
                val s = cc.aidelink.app.service.WirelessAdbManager.detectStatus(context)
                adbStatus.value = s
                if (s.wirelessAdbEnabled) viewModel.reportAdbStatus(s.deviceIp, s.adbPort, true)
                else if (s.deviceIp.isNotBlank()) viewModel.reportAdbStatus(s.deviceIp, 0, false)
            }
        }
        LaunchedEffect(Unit) {
            while (true) {
                updateAdbStatus()
                kotlinx.coroutines.delay(2000)
            }
        }
        Card(shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.padding(16.dp)) {
                val s = adbStatus.value
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(bottom = 8.dp)) {
                    Box(modifier = Modifier.size(10.dp).background(if (s?.wirelessAdbEnabled == true) Color(0xFF4CAF50) else Color(0xFFF44336), CircleShape))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(if (s?.wirelessAdbEnabled == true) "已开启" else "未开启", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                }
                if (s != null) {
                    Text("IP: ${s.deviceIp.ifBlank { "未连接" }}  端口: ${s.adbPort}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Root=${s.hasRoot}  内置 ADB 客户端=启用", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(bottom = 8.dp))
                }
                Spacer(modifier = Modifier.height(8.dp))
                Button(onClick = {
                    scope.launch {
                        try {
                            val r = cc.aidelink.app.service.WirelessAdbManager.requestRootPermissionPublic()
                            updateAdbStatus()
                            if (r.isSuccess) {
                                Toast.makeText(context, "Root 权限获取成功", Toast.LENGTH_SHORT).show()
                            } else {
                                val err = r.exceptionOrNull()?.message ?: "未知错误"
                                Toast.makeText(context, "Root 权限获取失败: $err", Toast.LENGTH_LONG).show()
                            }
                        } catch (e: Exception) {
                            Toast.makeText(context, "获取 Root 权限异常: ${e.message}", Toast.LENGTH_LONG).show()
                        }
                    }
                }, modifier = Modifier.fillMaxWidth()) { Text("主动获取 Root 授权") }
                Spacer(modifier = Modifier.height(4.dp))
                Button(onClick = {
                    scope.launch {
                        try {
                            val r = cc.aidelink.app.service.WirelessAdbManager.enableWirelessAdb(context, serverUrl)
                            updateAdbStatus()
                            if (r.isSuccess) {
                                val cr = r.getOrNull()!!
                                Toast.makeText(context, "已开启 (${cr.method}): ${cr.connectCmd}", Toast.LENGTH_LONG).show()
                            } else {
                                Toast.makeText(context, "开启失败: ${r.exceptionOrNull()?.message}", Toast.LENGTH_LONG).show()
                            }
                        } catch (e: Exception) {
                            Toast.makeText(context, "开启异常: ${e.message}", Toast.LENGTH_LONG).show()
                        }
                    }
                }, modifier = Modifier.fillMaxWidth()) { Text("一键开启无线调试") }
                Spacer(modifier = Modifier.height(4.dp))
                Button(onClick = {
                    scope.launch {
                        try {
                            val r = cc.aidelink.app.service.WirelessAdbManager.disableWirelessAdb(context)
                            if (r.isSuccess) {
                                // 立即回报服务端清理旧端口死连接
                                val ip = adbStatus.value?.deviceIp ?: ""
                                if (ip.isNotBlank()) viewModel.reportAdbStatus(ip, 0, false)
                                updateAdbStatus()
                                Toast.makeText(context, "已关闭无线调试", Toast.LENGTH_SHORT).show()
                            } else {
                                Toast.makeText(context, "关闭失败: ${r.exceptionOrNull()?.message}", Toast.LENGTH_SHORT).show()
                            }
                        } catch (e: Exception) {
                            Toast.makeText(context, "关闭异常: ${e.message}", Toast.LENGTH_SHORT).show()
                        }
                    }
                },
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error), modifier = Modifier.fillMaxWidth()) { Text("关闭无线调试") }
                Spacer(modifier = Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = {
                        try {
                            val intent = android.content.Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS).apply {
                                addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                                putExtra(":settings:fragment_args_key", "toggle_adb_wireless")
                                val bundle = android.os.Bundle().apply {
                                    putString(":settings:fragment_args_key", "toggle_adb_wireless")
                                }
                                putExtra(":settings:show_fragment_args", bundle)
                            }
                            context.startActivity(intent)
                        } catch (_: Exception) {}
                    }, modifier = Modifier.weight(1f)) { Text("开发者选项") }
                    OutlinedButton(onClick = {
                        val s = adbStatus.value
                        if (s != null && s.deviceIp.isNotBlank() && s.adbPort > 0) {
                            val clipboardManager = context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                            val clipData = android.content.ClipData.newPlainText("ADB Address", "${s.deviceIp}:${s.adbPort}")
                            clipboardManager.setPrimaryClip(clipData)
                            Toast.makeText(context, "已复制 IP:端口 (${s.deviceIp}:${s.adbPort}) 到剪贴板", Toast.LENGTH_SHORT).show()
                        } else {
                            Toast.makeText(context, "未获取到有效的 IP:端口，请确认已开启无线调试", Toast.LENGTH_SHORT).show()
                        }
                    }, modifier = Modifier.weight(1f)) { Text("复制 IP:端口") }
                }
            }
        }
    }
    item { SectionTitle("组件定位器", Icons.Default.LocationSearching) }
    item {
        Card(shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.padding(16.dp)) {
                var locatorEnabled by remember(state.globalLocatorEnabled) { mutableStateOf(state.globalLocatorEnabled) }
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("全局悬浮窗定位器", fontWeight = FontWeight.Medium)
                        Text("截屏并定位 UI 组件", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Switch(checked = locatorEnabled, onCheckedChange = { checked ->
                        if (checked && !Settings.canDrawOverlays(context)) {
                            context.startActivity(android.content.Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}")))
                        } else {
                            locatorEnabled = checked; viewModel.setGlobalLocatorEnabled(checked)
                            val i = android.content.Intent(context, cc.aidelink.app.service.UiLocatorService::class.java)
                            if (checked) { if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) context.startForegroundService(i) else context.startService(i) } else context.stopService(i)
                        }
                    })
                }
            }
        }
    }
}

internal fun LazyListScope.tabGeneralItems(
    state: AideLinkSettingsViewModel.UiState,
    viewModel: AideLinkSettingsViewModel,
) {
    item { SectionTitle("通知设置", Icons.Default.Notifications) }
    item {
        Card(shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.padding(16.dp)) {
                var notifEnabled by remember { mutableStateOf(state.notificationsEnabled) }
                var silentMode by remember { mutableStateOf(state.silentNotifications) }
                var hapticEnabled by remember { mutableStateOf(state.hapticFeedback) }
                listOf(
                    Triple("任务完成通知", "IDE 完成任务时推送通知", notifEnabled) to { v: Boolean -> notifEnabled = v; viewModel.setNotificationsEnabled(v) },
                    Triple("静音模式", "通知不播放声音和震动", silentMode) to { v: Boolean -> silentMode = v; viewModel.setSilentNotifications(v) },
                    Triple("震动反馈", "通知到达时震动", hapticEnabled) to { v: Boolean -> hapticEnabled = v; viewModel.setHapticFeedback(v) },
                ).forEach { (triple, setter) ->
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Column(modifier = Modifier.weight(1f)) { Text(triple.first, fontWeight = FontWeight.Medium); Text(triple.second, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                        Switch(checked = triple.third, onCheckedChange = setter)
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }
            }
        }
    }
    item { SectionTitle("软件更新", Icons.Default.SystemUpdate) }
    item {
        Card(shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                Text("当前版本: v${BuildConfig.VERSION_NAME} (Code: ${BuildConfig.VERSION_CODE})", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
                state.updateStatusMessage?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(top = 4.dp)) }
                state.updateError?.let { Text("错误: $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 4.dp)) }
                if (state.isCheckingUpdate || state.isDownloadingUpdate || state.isAdbInstalling) { Spacer(modifier = Modifier.height(8.dp)); LinearProgressIndicator(modifier = Modifier.fillMaxWidth()) }
                Spacer(modifier = Modifier.height(12.dp))
                @OptIn(ExperimentalFoundationApi::class)
                Surface(modifier = Modifier.fillMaxWidth().combinedClickable(enabled = !state.isCheckingUpdate && !state.isDownloadingUpdate && !state.isAdbInstalling,
                    onClick = { viewModel.checkForUpdate(force = false) }, onLongClick = { viewModel.checkForUpdate(force = true) }),
                    shape = RoundedCornerShape(8.dp), color = MaterialTheme.colorScheme.primary, contentColor = MaterialTheme.colorScheme.onPrimary) {
                    Box(modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp, horizontal = 16.dp), contentAlignment = Alignment.Center) {
                        Text(if (state.isCheckingUpdate) "正在检查..." else if (state.isDownloadingUpdate) "正在下载..." else "点击检查更新 (长按强制更新)", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }
    }
    item { SectionTitle("关于", Icons.Default.Info) }
    item {
        Card(shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("AideLink", fontWeight = FontWeight.Bold)
                Text("手机 ⇄ 本地 IDE 智能桥接", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("v${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
internal fun SectionTitle(text: String, icon: ImageVector? = null) {
    Row(
        modifier = Modifier.padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (icon != null) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(18.dp),
                tint = MaterialTheme.colorScheme.primary)
            Spacer(modifier = Modifier.width(6.dp))
        }
        Text(
            text,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
internal fun ServerListSection(
    servers: List<cc.aidelink.app.domain.model.BridgeServerConfig>,
    activeServerId: String?,
    currentUrl: String,
    isScanning: Boolean,
    scanMessage: String? = null,
    onSwitchServer: (String) -> Unit,
    onDeleteServer: (String) -> Unit,
    onAddServer: (String, String, cc.aidelink.app.domain.model.BridgeServerType) -> Unit,
    onEditServer: (cc.aidelink.app.domain.model.BridgeServerConfig) -> Unit,
    onScan: () -> Unit,
    onScanQr: () -> Unit = {},
) {
    var showAddDialog by remember { mutableStateOf(false) }
    var editingServer by remember { mutableStateOf<cc.aidelink.app.domain.model.BridgeServerConfig?>(null) }
    var showScanResult by remember { mutableStateOf<String?>(null) }

    Card(shape = RoundedCornerShape(12.dp)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "已保存的服务器",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Row {
                    IconButton(onClick = onScan, enabled = !isScanning) {
                        if (isScanning) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(24.dp),
                                strokeWidth = 2.dp
                            )
                        } else {
                            Icon(Icons.Default.Search, contentDescription = "扫描局域网")
                        }
                    }
                    IconButton(onClick = { showAddDialog = true }) {
                        Icon(Icons.Default.Add, contentDescription = "添加服务器")
                    }
                }
            }

            scanMessage?.let { msg ->
                Text(
                    msg,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }

            if (servers.isEmpty()) {
                Text(
                    "暂无服务器配置，请添加或扫描",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 16.dp)
                )
            } else {
                Spacer(modifier = Modifier.height(8.dp))
                servers.forEach { server ->
                    val isActive = server.id == activeServerId
                    ServerItem(
                        server = server,
                        isActive = isActive,
                        onSwitch = { onSwitchServer(server.id) },
                        onEdit = { editingServer = server },
                        onDelete = { onDeleteServer(server.id) }
                    )
                }
            }

            showScanResult?.let { result ->
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    result,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary
                )
            }
        }
    }

    if (showAddDialog || editingServer != null) {
        val serverBeingEdited = editingServer
        AddServerDialog(
            editingServer = serverBeingEdited,
            onDismiss = { showAddDialog = false; editingServer = null },
            onConfirm = { name, url, type ->
                if (serverBeingEdited != null) {
                    val updated = serverBeingEdited.copy(name = name, url = url, serverType = type)
                    onEditServer(updated)
                } else {
                    onAddServer(name, url, type)
                }
                showAddDialog = false; editingServer = null
            }
        )
    }
}

@Composable
internal fun ServerItem(
    server: cc.aidelink.app.domain.model.BridgeServerConfig,
    isActive: Boolean,
    onSwitch: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit
) {
    var showDeleteDialog by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
            .clickable(onClick = onSwitch),
        colors = CardDefaults.cardColors(
            containerColor = if (isActive) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surfaceVariant
            }
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = if (isActive) Icons.Default.RadioButtonChecked else Icons.Default.RadioButtonUnchecked,
                contentDescription = null,
                tint = if (isActive) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = server.name,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium
                )
                Text(
                    text = server.url,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = when (server.serverType) {
                        cc.aidelink.app.domain.model.BridgeServerType.LOCAL -> "局域网"
                        cc.aidelink.app.domain.model.BridgeServerType.FRP -> "FRP"
                        cc.aidelink.app.domain.model.BridgeServerType.CUSTOM -> "自定义"
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            IconButton(onClick = onEdit) {
                Icon(
                    Icons.Default.Edit,
                    contentDescription = "编辑",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            IconButton(onClick = { showDeleteDialog = true }) {
                Icon(
                    Icons.Default.Delete,
                    contentDescription = "删除",
                    tint = MaterialTheme.colorScheme.error
                )
            }
        }
    }

    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            title = { Text("删除服务器") },
            text = { Text("确定要删除 ${server.name} 吗？") },
            confirmButton = {
                TextButton(
                    onClick = {
                        onDelete()
                        showDeleteDialog = false
                    }
                ) {
                    Text("删除", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) {
                    Text("取消")
                }
            }
        )
    }
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
internal fun AddServerDialog(
    editingServer: cc.aidelink.app.domain.model.BridgeServerConfig? = null,
    onDismiss: () -> Unit,
    onConfirm: (String, String, cc.aidelink.app.domain.model.BridgeServerType) -> Unit
) {
    var name by remember { mutableStateOf(editingServer?.name ?: "电脑") }
    var ip by remember { mutableStateOf("192.168.") }
    var port by remember { mutableStateOf("5000") }
    var selectedType by remember { mutableStateOf(editingServer?.serverType ?: cc.aidelink.app.domain.model.BridgeServerType.LOCAL) }
    var expanded by remember { mutableStateOf(false) }
    var ipError by remember { mutableStateOf<String?>(null) }
    var portError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(editingServer) {
        val url = editingServer?.url ?: return@LaunchedEffect
        val withScheme = if (!url.startsWith("http://") && !url.startsWith("https://")) "http://$url" else url
        kotlin.runCatching {
            val u = java.net.URL(withScheme)
            ip = u.host
            port = if (u.port > 0) u.port.toString() else ""
            selectedType = editingServer.serverType
            name = editingServer.name
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (editingServer != null) "编辑服务器" else "添加服务器") },
        text = {
            Column {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("名称") },
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = ip,
                    onValueChange = {
                        ip = it
                        ipError = null
                    },
                    label = { Text("IP / 域名（可填完整 URL）") },
                    isError = ipError != null,
                    modifier = Modifier.fillMaxWidth()
                )
                ipError?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error)
                }
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = port,
                    onValueChange = {
                        port = it.filter { c -> c.isDigit() }
                        portError = null
                    },
                    label = { Text(if (selectedType == cc.aidelink.app.domain.model.BridgeServerType.FRP) "端口（FRP 可选）" else "端口") },
                    isError = portError != null,
                    modifier = Modifier.fillMaxWidth()
                )
                portError?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val cleanedIp = ip.trim()
                val cleanedPort = port.trim()
                if (cleanedIp.isBlank()) {
                    ipError = "请输入 IP 或域名"
                    return@TextButton
                }
                val finalUrl = if (cleanedIp.contains("://")) {
                    cleanedIp
                } else {
                    val parsedPort = cleanedPort.toIntOrNull()
                    if (cleanedPort.isBlank() && selectedType == cc.aidelink.app.domain.model.BridgeServerType.FRP) {
                        "https://$cleanedIp"
                    } else if (parsedPort == null || parsedPort !in 1..65535) {
                        portError = if (selectedType == cc.aidelink.app.domain.model.BridgeServerType.FRP) {
                            "FRP 端口可选；若填写需在 1 - 65535 之间"
                        } else {
                            "请输入 1 - 65535 的端口"
                        }
                        return@TextButton
                    } else {
                        "http://$cleanedIp:$parsedPort"
                    }
                }
                if (cc.aidelink.app.data.repository.BridgeServerRepository.isPhoneLoopbackUrl(finalUrl)) {
                    ipError = "不能使用手机本机地址，请填写电脑的局域网 IP 或公网域名"
                    return@TextButton
                }
                onConfirm(name.trim(), finalUrl, selectedType)
            }) {
                Text("确定")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("取消") }
        }
    )
}

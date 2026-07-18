package cc.aidelink.app.ui.screens.chat

import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.widget.Toast
import androidx.compose.foundation.Image
import androidx.compose.foundation.Canvas
import androidx.compose.ui.unit.IntOffset
import androidx.compose.foundation.border
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.res.painterResource
import coil.compose.AsyncImage
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.core.content.FileProvider
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.compose.currentStateAsState
import androidx.activity.ComponentActivity
import kotlinx.coroutines.launch
import cc.aidelink.app.domain.model.bridge.ChatMessage
import java.io.File
import java.io.FileOutputStream
import java.util.Locale
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.platform.LocalClipboardManager
import cc.aidelink.app.domain.model.bridge.ProjectNode
import cc.aidelink.app.domain.model.bridge.AideTask
import cc.aidelink.app.ui.screens.chat.components.*
import cc.aidelink.app.ui.screens.sessions.SessionListScreen
import cc.aidelink.app.ui.screens.sessions.SessionListViewModel
import cc.aidelink.app.ui.screens.sessions.buildOpenCodeWebSessionUrl
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.platform.LocalFocusManager

internal fun targetColor(target: String?): Color {
    if (target == null) return Color(0xFF90A4AE)
    // 特殊 target 的固定颜色
    val fixed = when (target) {
        "aide" -> Color(0xFF64B5F6)
        "assistant" -> Color(0xFF90A4AE)
        else -> null
    }
    if (fixed != null) return fixed
    // 从动态 Target 列表查找
    val t = AideLinkChatViewModel.Target.entries.find { it.key == target }
    if (t != null && t.colorHex.isNotEmpty()) {
        return runCatching { Color(android.graphics.Color.parseColor(t.colorHex)) }.getOrDefault(Color(0xFF90A4AE))
    }
    return Color(0xFF90A4AE)
}

internal fun taskTabAfterDispatch(currentTab: Int, success: Boolean): Int {
    return if (success) 1 else currentTab
}

@Composable
private fun TaskThreadPanel(
    task: AideTask,
    messages: List<ChatMessage>,
    onBack: () -> Unit,
    onEdit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.background(MaterialTheme.colorScheme.background)) {
        Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 1.dp) {
            Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onBack, modifier = Modifier.size(34.dp)) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "返回任务列表", modifier = Modifier.size(18.dp))
                    }
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = task.title?.ifBlank { null } ?: task.text.ifBlank { task.task_id }.lineSequence().firstOrNull().orEmpty(),
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(task.task_id, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            task.target_ide?.let {
                                Text(it.uppercase(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                            }
                            Text(task.status, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    IconButton(onClick = onEdit, modifier = Modifier.size(34.dp)) {
                        Icon(Icons.Default.Edit, contentDescription = "修改任务", modifier = Modifier.size(18.dp))
                    }
                }
                if (task.text.isNotBlank()) {
                    Text(
                        text = task.text,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 4,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(start = 42.dp, top = 4.dp)
                    )
                }
            }
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (messages.isEmpty() && task.feedbacks.isNullOrEmpty()) {
                item {
                    Box(modifier = Modifier.fillParentMaxSize(), contentAlignment = Alignment.Center) {
                        Text("这个任务还没有专属对话", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            itemsIndexed(messages) { _, msg ->
                MessageBubble(msg, onChoiceClick = {})
            }
            task.feedbacks?.let { feedbacks ->
                itemsIndexed(feedbacks) { index, fb ->
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.45f),
                    ) {
                        Column(modifier = Modifier.fillMaxWidth().padding(10.dp)) {
                            Text(
                                text = "补充 ${index + 1}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSecondaryContainer,
                                fontWeight = FontWeight.SemiBold,
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(fb.text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSecondaryContainer)
                        }
                    }
                }
            }
        }
    }
}

// IDE badge 颜色辅助（背景色 + 文字色）
private data class IdeBadgeColors(val bg: Color, val text: Color)

private fun getIdeBadgeColors(ide: String): IdeBadgeColors = when (ide.lowercase()) {
    "mimo" -> IdeBadgeColors(bg = Color(0xFFFFF3E0), text = Color(0xFFF57C00))
    "antigravity_ide" -> IdeBadgeColors(bg = Color(0xFFF3E5F5), text = Color(0xFF7B1FA2))
    "trae" -> IdeBadgeColors(bg = Color(0xFFE1F5FE), text = Color(0xFF0288D1))
        "opencode", "oc_web" -> IdeBadgeColors(bg = Color(0xFFE8F5E9), text = Color(0xFF388E3C))
    else -> IdeBadgeColors(bg = Color(0xFFECEFF1), text = Color(0xFF455A64))
}

internal fun targetLabel(target: String?): String {
    if (target == null) return "未知"
    val fixed = when (target) {
        "aide" -> "Aide"
        "assistant" -> "小助手"
        else -> null
    }
    if (fixed != null) return fixed
    val t = AideLinkChatViewModel.Target.entries.find { it.key == target }
    return t?.label ?: target
}

@Composable
internal fun TargetIcon(target: AideLinkChatViewModel.Target, size: Dp = 16.dp) {
    val color = targetColor(target.key)
    Surface(
        modifier = Modifier.size(size),
        shape = RoundedCornerShape(4.dp),
        color = color.copy(alpha = 0.15f)
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(
                text = target.icon.ifEmpty { target.label.first().toString() },
                color = color,
                fontSize = (size.value * 0.55f).sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
internal fun TargetBadge(target: String?) {
    val color = targetColor(target)
    val label = targetLabel(target)
    Surface(
        shape = RoundedCornerShape(4.dp),
        color = color.copy(alpha = 0.15f),
        modifier = Modifier.padding(bottom = 4.dp)
    ) {
        Text(
            text = "  $label  ",
            color = color,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 2.dp)
        )
    }
}

fun parseChoices(text: String): Pair<String, List<String>> {
    val regex = Regex("\\[选择:\\s*([^\\]]+)\\]")
    val match = regex.find(text)
    if (match != null) {
        val choicesStr = match.groupValues[1]
        val choices = choicesStr.split("|").map { it.trim() }.filter { it.isNotEmpty() }
        val cleanedText = text.replace(match.value, "").trim()
        return Pair(cleanedText, choices)
    }
    return Pair(text, emptyList())
}

/**
 * AideLink 聊天 Screen（精简增强版）
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AideLinkChatScreen(
    onNavigateBack: () -> Unit,
    onNavigateToSettings: () -> Unit,
    onNavigateToOpenCodeWeb: ((url: String, username: String, pwd: String) -> Unit)? = null,
    onNavigateToOpenCodeSessions: ((url: String, username: String, pwd: String) -> Unit)? = null,
    initialTarget: String? = null,
    viewModel: AideLinkChatViewModel = hiltViewModel(),
) {
    val state = viewModel.state.collectAsStateWithLifecycle().value
    // 服务端可返回不同名称/图标的动态 Target，OpenCode Web 必须按稳定 key 判断。
    val isOpenCodeWebTarget = state.target.key == AideLinkChatViewModel.Target.OPENCODE_WEB.key

    LaunchedEffect(initialTarget, state.targetInitialized) {
        if (state.targetInitialized && initialTarget != null && state.target.key != initialTarget) {
            val targetEnum = AideLinkChatViewModel.Target.entries.find { it.key == initialTarget }
            if (targetEnum != null) viewModel.setTarget(targetEnum, persist = false)
        }
    }

    if (!state.targetInitialized || (initialTarget != null && state.target.key != initialTarget)) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }
    val listState = rememberLazyListState()
    val context = LocalContext.current
    val activity = context as? ComponentActivity
    val mainViewModel: cc.aidelink.app.ui.navigation.MainViewModel? = if (activity != null) {
        hiltViewModel(activity)
    } else {
        null
    }
    var showTaskList by remember { mutableStateOf(false) }
    var selectedTaskTab by remember { mutableIntStateOf(0) }
    var showClipboardSheet by remember { mutableStateOf(false) }
    val sheetState = rememberModalBottomSheetState()
    val monitorHeightDp = state.monitorHeightDp.dp
    val coroutineScope = rememberCoroutineScope()
    val openCodeSessionViewModel: SessionListViewModel = hiltViewModel()
    var openCodeWebConfig by remember { mutableStateOf<AideLinkChatViewModel.OpenCodeWebConfig?>(null) }
    var openCodeSessionCreating by remember { mutableStateOf(false) }
    val monitorByTarget = state.monitorByTarget
    val showMonitorPanel = state.monitorActive
    val activeTask = remember(state.tasks, state.activeTaskId) {
        state.activeTaskId?.let { id -> state.tasks.find { it.task_id == id } }
    }

    LaunchedEffect(state.target.key) {
        showTaskList = state.target != AideLinkChatViewModel.Target.AIDELINK && !isOpenCodeWebTarget
        selectedTaskTab = 0
    }

    LaunchedEffect(state.target.key, state.ocWebRunning) {
        openCodeWebConfig = if (isOpenCodeWebTarget) {
            viewModel.resolveOpenCodeWebConfig()
        } else {
            null
        }
    }

    LaunchedEffect(state.toastMessage) {
        val message = state.toastMessage ?: return@LaunchedEffect
        kotlinx.coroutines.delay(3000)
        viewModel.clearToast(message)
    }

    val filteredMessages = remember(state.messages, state.target) {
        state.messages.filter { msg ->
            val t = msg.target?.lowercase()
            if (state.target == AideLinkChatViewModel.Target.AIDELINK) {
                t == null || t == "" || t == "aide" || t == "aidelink" || t == "xiaomengling" || t == "auto" || t == "aide_thinking"
            } else {
                t == state.target.key
            }
        }
    }

    val lifecycle = androidx.lifecycle.compose.LocalLifecycleOwner.current.lifecycle
    val lifecycleState by lifecycle.currentStateAsState()
    DisposableEffect(lifecycleState, viewModel) {
        if (lifecycleState == Lifecycle.State.RESUMED) {
            viewModel.consumePendingCalibrationRequest()
            viewModel.setMonitorScreenVisible(true)
            viewModel.onResumeRefresh()
            if (isOpenCodeWebTarget) {
                openCodeSessionViewModel.loadSessions()
            }
        } else {
            viewModel.setMonitorScreenVisible(false)
        }
        onDispose {
            viewModel.setMonitorScreenVisible(false)
        }
    }

    LaunchedEffect(monitorHeightDp, filteredMessages.size, state.sending) {
        if (filteredMessages.isNotEmpty()) {
            listState.scrollToItem(filteredMessages.lastIndex)
        }
    }

    @OptIn(ExperimentalLayoutApi::class)
    val imeVisible = WindowInsets.isImeVisible
    LaunchedEffect(imeVisible) {
        if (imeVisible && filteredMessages.isNotEmpty()) {
            kotlinx.coroutines.delay(100)
            listState.scrollToItem(filteredMessages.lastIndex)
        }
    }

    // 每次进入 ChatScreen 时刷新 IDE 列表（ViewModel 可能因导航存活而未 init）
    LaunchedEffect(Unit) {
        viewModel.loadProject()
        viewModel.loadTasks()
        viewModel.loadSelectedIdeList()
        viewModel.loadDesktopIdes()
    }

    Scaffold(
        topBar = {
            val bgColor = MaterialTheme.colorScheme.background
            Surface(
                color = bgColor,
                tonalElevation = 0.dp
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(start = 16.dp, end = 4.dp, top = 2.dp, bottom = 2.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    var projectMenuExpanded by remember { mutableStateOf(false) }
                    Box {
                        Row(
                            modifier = Modifier
                                .clickable { projectMenuExpanded = true }
                                .padding(horizontal = 4.dp, vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = state.currentProjectName.ifBlank { if (state.target == AideLinkChatViewModel.Target.AIDELINK) "Aide" else state.target.label },
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Icon(Icons.Default.ArrowDropDown, contentDescription = "切换项目", modifier = Modifier.size(18.dp))
                        }
                        DropdownMenu(
                            expanded = projectMenuExpanded,
                            onDismissRequest = { projectMenuExpanded = false },
                        ) {
                            state.projects.forEach { project ->
                                DropdownMenuItem(
                                    text = { Text(project.name.ifBlank { project.path.substringAfterLast('\\') }) },
                                    onClick = {
                                        projectMenuExpanded = false
                                        viewModel.selectProject(project.path)
                                    },
                                    leadingIcon = if (project.path.equals(state.currentProjectPath, ignoreCase = true)) {
                                        { Icon(Icons.Default.Check, contentDescription = null) }
                                    } else null,
                                )
                            }
                            if (state.projects.isEmpty()) {
                                DropdownMenuItem(text = { Text("请先在设置中添加项目") }, onClick = { projectMenuExpanded = false })
                            }
                        }
                    }

                    Spacer(modifier = Modifier.width(6.dp))

                    if (state.target == AideLinkChatViewModel.Target.AIDELINK) {
                        Box(
                            modifier = Modifier
                                .size(6.dp)
                                .clip(CircleShape)
                                .background(
                                    when {
                                        state.mimoLoading -> Color(0xFFFFA726)
                                        state.mimoRunning -> Color(0xFF4CAF50)
                                        else -> Color(0xFFBDBDBD)
                                    }
                                ),
                        )
                    }

                    Spacer(modifier = Modifier.weight(1f))

                    // 悬浮窗按钮（toggle）
                    val isLocatorRunning = remember { mutableStateOf(false) }
                    LaunchedEffect(Unit) {
                        while (true) {
                            isLocatorRunning.value = isServiceRunning(context, cc.aidelink.app.service.UiLocatorService::class.java)
                            kotlinx.coroutines.delay(2000)
                        }
                    }
                    IconButton(
                        onClick = {
                            if (isLocatorRunning.value) {
                                val intent = android.content.Intent(context, cc.aidelink.app.service.UiLocatorService::class.java)
                                context.stopService(intent)
                            } else {
                                val intent = android.content.Intent(context, cc.aidelink.app.service.UiLocatorService::class.java)
                                context.startForegroundService(intent)
                            }
                        },
                        modifier = Modifier.size(34.dp)
                    ) {
                        Icon(
                            imageVector = if (isLocatorRunning.value) Icons.Default.LocationOn else Icons.Default.LocationOff,
                            contentDescription = "悬浮窗",
                            modifier = Modifier.size(18.dp),
                            tint = if (isLocatorRunning.value) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    // 设置按钮
                    IconButton(onClick = onNavigateToSettings, modifier = Modifier.size(34.dp)) {
                        Icon(
                            imageVector = Icons.Default.Settings,
                            contentDescription = "设置",
                            modifier = Modifier.size(18.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        },

        bottomBar = {
            Column {
                ChatInputBar(
                    input = state.input,
                    sending = state.sending,
                    uploading = state.uploading,
                    currentTarget = state.target,
                    monitorByTarget = monitorByTarget,
                    selectedIdeList = state.selectedIdeList,
                    desktopIdes = state.desktopIdes,
                    ideRunningMap = state.ideRunningMap,
                    quickReplies = state.quickReplies,
                    isPromptMode = state.isPromptMode,
                    onInputChange = viewModel::setInput,
                    onSend = {
                        showTaskList = false
                        viewModel.send(isTaskListMode = false)
                    },
                    onSendToTaskList = {
                        showTaskList = true
                        viewModel.send(isTaskListMode = true)
                    },
                    onCreateOfflineTask = viewModel::createOfflineTaskFromInput,
                    onUploadImage = { path ->
                        viewModel.uploadImage(path)
                    },
                    onTargetChange = { newTarget ->
                        viewModel.setTarget(newTarget)
                        showTaskList = newTarget != AideLinkChatViewModel.Target.AIDELINK &&
                            newTarget.key != AideLinkChatViewModel.Target.OPENCODE_WEB.key
                    },
                    onMonitorToggle = { target ->
                        val current = monitorByTarget[target] == true
                        viewModel.setMonitorEnabledForTarget(target, !current)
                    },
                    onClipboard = {
                        viewModel.loadClipboard()
                        showClipboardSheet = true
                    },
                    onWakeScreen = viewModel::wakeScreen,
                    onRefreshIdeStatus = { viewModel.loadIdeRunningStatus(); viewModel.loadOcWebStatus() },
                    onStartIde = viewModel::startIde,
                    onStopIde = viewModel::stopIde,
                    onQuickReply = { text ->
                        showTaskList = false
                        viewModel.sendQuickReply(text)
                    },
                    onAddQuickReply = { text -> viewModel.addQuickReply(text) },
                    onRemoveQuickReply = { text -> viewModel.removeQuickReply(text) },
                    onShowDesktopIdeDialog = viewModel::openDesktopIdeDialog,
                    projectMapExpanded = state.projectMapExpanded,
                    onToggleProjectMap = viewModel::toggleProjectMap,
                    onRefreshTasks = viewModel::loadTasks,
                    onStartUiLocator = {
                        val intent = android.content.Intent(context, cc.aidelink.app.service.UiLocatorService::class.java)
                        context.startForegroundService(intent)
                    },
                    onCreateNewSession = viewModel::createNewSession,
                    bridgeOnline = state.bridgeOnline,
                    bridgeConnecting = state.bridgeConnecting,
                    showTaskList = showTaskList,
                    offlineTaskMode = showTaskList && selectedTaskTab == 3,
                    taskThreadMode = activeTask != null,
                    taskEditMode = state.editingTaskId != null,
                    onToggleTaskList = { showTaskList = !showTaskList },
                    onEnterTaskList = { showTaskList = true },
                    onSaveTaskEdit = viewModel::saveTaskEdit,
                    onCancelTaskEdit = viewModel::cancelTaskEdit,
                    onOptimizeTaskPrompt = viewModel::optimizeTaskDraft,
                    ocWebRunning = state.ocWebRunning,
                    onOcWebToggle = viewModel::toggleOcWeb,
                    onOpenWeb = {
                        if (onNavigateToOpenCodeWeb != null) {
                            coroutineScope.launch {
                                val cfg = viewModel.resolveOpenCodeWebConfig()
                                if (cfg != null) onNavigateToOpenCodeWeb(cfg.url, cfg.username, cfg.password)
                            }
                        }
                    },
                    openCodeSessionCreating = openCodeSessionCreating,
                    onCreateOpenCodeSession = {
                        val config = openCodeWebConfig
                        val projectPath = state.currentProjectPath
                        when {
                            config == null -> Toast.makeText(context, "OpenCode 连接配置尚未就绪", Toast.LENGTH_SHORT).show()
                            projectPath.isBlank() -> Toast.makeText(context, "请先在左上角选择项目", Toast.LENGTH_SHORT).show()
                            else -> {
                                openCodeSessionCreating = true
                                openCodeSessionViewModel.createNewSession(
                                    directory = projectPath,
                                    initialPrompt = state.input,
                                ) { success ->
                                    openCodeSessionCreating = false
                                    if (success) viewModel.setInput("")
                                }
                            }
                        }
                    },
                )
            }
        }
    ) { padding ->
        val focusManager = LocalFocusManager.current
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(top = padding.calculateTopPadding(), bottom = padding.calculateBottomPadding())
                .pointerInput(Unit) {
                    detectTapGestures(onTap = {
                        focusManager.clearFocus()
                    })
                }
        ) {

            // 项目地图面板（可折叠）
            AnimatedVisibility(
                visible = state.projectMapExpanded,
                enter = expandVertically(),
                exit = shrinkVertically(),
            ) {
                ProjectMapPanel(
                    categories = state.projectMap,
                    loading = state.projectMapLoading,
                    selectedNode = state.selectedNode,
                    promptAction = state.promptAction,
                    promptDescription = state.promptDescription,
                    promptVersion = state.promptVersion,
                    generatedPrompt = state.generatedPrompt,
                    promptCandidates = state.promptCandidates,
                    promptPredictLoading = state.promptPredictLoading,
                    onRescan = viewModel::scanProjectMap,
                    onSelectNode = viewModel::selectNode,
                    onClearSelection = viewModel::clearSelection,
                    onSetAction = viewModel::setPromptAction,
                    onSetDescription = viewModel::setPromptDescription,
                    onPredictPrompts = { query -> viewModel.predictPrompts(query, isTaskMode = false) },
                    onSetVersion = viewModel::setPromptVersion,
                    onGenerate = viewModel::generatePrompt,
                    onUsePrompt = viewModel::useGeneratedPrompt,
                    onLockFeature = viewModel::lockProjectFeature,
                )
            }

            if (showMonitorPanel && !isOpenCodeWebTarget) {
                ScreenMonitorPanel(
                    active = state.monitorActive,
                    windowFound = state.windowFound,
                    targetLabel = state.target.label,
                    sleeping = state.monitorSleeping,
                    image = state.monitorImage,
                    croppedImage = state.monitorImage,
                    originalWidth = state.monitorImage?.width ?: state.monitorOriginalWidth,
                    originalHeight = state.monitorImage?.height ?: state.monitorOriginalHeight,
                    calibWidth = state.calibWidth,
                    calibHeight = state.calibHeight,
                    intervalMs = state.monitorIntervalMs,
                    heightDp = monitorHeightDp,
                    cropLeft = 0,
                    cropRight = 0,
                    cropTop = 0,
                    cropBottom = 0,
                    onHeightChange = {
                        viewModel.setMonitorHeightDp(it.value.toInt())
                        coroutineScope.launch {
                            if (state.messages.isNotEmpty()) {
                                listState.scrollToItem(state.messages.lastIndex)
                            }
                        }
                    },
                    onClose = {
                        viewModel.setMonitorScreenVisible(false)
                    },
                    onDragStart = {
                        viewModel.pauseMonitorPolling()
                    },
                    onDragEnd = {
                        viewModel.resumeMonitorPolling()
                    },
                    onImageClick = {
                        viewModel.focusTargetWindow()
                    },
                    onImageDoubleClick = {
                        viewModel.setShowLiveMonitorDialog(true)
                    },
                    onAutoDetectBlackEdge = { imageW, imageH, containerWidthDp ->
                        viewModel.adjustHeightByImageRatioDp(imageW, imageH, containerWidthDp)
                    },
                    onWake = { viewModel.wakeMonitor() }
                )
                HorizontalDivider()
            }

            Box(modifier = Modifier.fillMaxSize()) {
                if (activeTask != null) {
                    TaskThreadPanel(
                        task = activeTask,
                        messages = state.messages.filter { it.task_id == activeTask.task_id },
                        onBack = {
                            viewModel.closeTaskThread()
                            showTaskList = true
                        },
                        onEdit = { viewModel.startTaskEdit(activeTask.task_id) },
                        modifier = Modifier.fillMaxSize(),
                    )
                } else if (isOpenCodeWebTarget && !showTaskList) {
                    val config = openCodeWebConfig
                    if (config != null) {
                        SessionListScreen(
                            onNavigateToChat = { sessionId, directory ->
                                val projectDirectory = directory.ifBlank { state.currentProjectPath }
                                val sessionUrl = buildOpenCodeWebSessionUrl(config.url, projectDirectory, sessionId)
                                onNavigateToOpenCodeWeb?.invoke(sessionUrl, config.username, config.password)
                            },
                            onNavigateBack = {},
                            serverId = "aidelink-opencode-main",
                            serverUrl = config.url,
                            username = config.username,
                            password = config.password,
                            serverName = "OpenCode 会话",
                            embedded = true,
                            viewModel = openCodeSessionViewModel,
                        )
                    } else {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            OcWebStatusCard(
                                running = state.ocWebRunning,
                                loading = state.ocWebLoading,
                                port = state.ocWebPort,
                                statusMessage = state.ocWebStatusMessage,
                                latestReply = state.ocWebLatestReply,
                                sessionTitle = state.ocWebSessionTitle,
                                onRefreshReply = viewModel::loadOcWebLatestReply,
                            )
                        }
                    }
                } else if (!showTaskList) {
                    // 显示对话气泡
                    when {
                        state.loading && filteredMessages.isEmpty() -> {
                            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                CircularProgressIndicator()
                            }
                        }
                        filteredMessages.isEmpty() -> {
                            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                Text(
                                    "开始与 ${if (state.target == AideLinkChatViewModel.Target.AIDELINK) "Aide" else state.target.label} 对话",
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                        else -> {
                            LazyColumn(
                                state = listState,
                                modifier = Modifier.fillMaxSize(),
                                contentPadding = PaddingValues(12.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                itemsIndexed(filteredMessages) { index, msg ->
                                    MessageBubble(msg, onChoiceClick = { choice ->
                                        showTaskList = false
                                        viewModel.sendDirect(choice)
                                    })
                                    if (index == filteredMessages.lastIndex) {
                                        Spacer(modifier = Modifier.height(8.dp))
                                    }
                                }
                                // Aide 正在思考中指示器
                                if (state.sending && state.target == AideLinkChatViewModel.Target.AIDELINK) {
                                    item {
                                        Row(
                                            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
                                            horizontalArrangement = Arrangement.Start,
                                            verticalAlignment = Alignment.CenterVertically,
                                        ) {
                                            CircularProgressIndicator(
                                                modifier = Modifier.size(14.dp),
                                                strokeWidth = 2.dp,
                                            )
                                            Spacer(modifier = Modifier.width(8.dp))
                                            Text(
                                                "Aide 正在思考中...",
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                } else {
                    // 桌面 IDE：直接展示任务列表
                    TaskListPanel(
                        tasks = state.tasks,
                        loading = state.tasksLoading,
                        batchMode = state.batchMode,
                        selectedTaskIds = state.selectedTaskIds,
                        currentTarget = if (state.target == AideLinkChatViewModel.Target.AIDELINK) "" else state.target.key,
                        onComplete = viewModel::completeTask,
                        onFail = viewModel::failTask,
                        onDelete = viewModel::deleteTask,
                        onLongPress = viewModel::enterBatchMode,
                        onToggleSelect = viewModel::toggleTaskSelection,
                        onSelectTasks = viewModel::selectTasks,
                        onExitBatchMode = viewModel::exitBatchMode,
                        onBatchDelete = viewModel::batchDelete,
                        onBatchComplete = viewModel::batchComplete,
                        onBatchDispatch = {
                            if (state.target != AideLinkChatViewModel.Target.AIDELINK) {
                                viewModel.executeDispatch(state.target.key, state.selectedTaskIds) { success ->
                                    selectedTaskTab = taskTabAfterDispatch(selectedTaskTab, success)
                                }
                            } else {
                                viewModel.showDispatchSelector(state.selectedTaskIds)
                            }
                        },
                        onDispatch = { taskId ->
                            if (state.target != AideLinkChatViewModel.Target.AIDELINK) {
                                viewModel.executeDispatch(state.target.key, setOf(taskId)) { success ->
                                    selectedTaskTab = taskTabAfterDispatch(selectedTaskTab, success)
                                }
                            } else {
                                viewModel.showDispatchSelector(setOf(taskId))
                            }
                        },
                        onSyncOfflineTask = { taskId ->
                            val dispatchTarget = if (state.target != AideLinkChatViewModel.Target.AIDELINK) {
                                state.target.key
                            } else ""
                            if (dispatchTarget.isNotBlank()) {
                                viewModel.executeDispatch(dispatchTarget, setOf(taskId)) { success ->
                                    selectedTaskTab = taskTabAfterDispatch(selectedTaskTab, success)
                                }
                            } else {
                                viewModel.showDispatchSelector(setOf(taskId))
                            }
                        },
                        onOpenTask = { taskId -> viewModel.openTaskThread(taskId) },
                        onEditTask = { taskId -> viewModel.startTaskEdit(taskId) },
                        onConfirm = viewModel::confirmTask,
                        onPromptBuilder = viewModel::showTaskPromptBuilder,
                        selectedTab = selectedTaskTab,
                        onSelectedTabChange = { selectedTaskTab = it },
                        bridgeUrl = viewModel.bridgeApi.baseUrl,
                        modifier = Modifier.fillMaxSize()
                    )
                }

                state.toastMessage?.let { msg ->
                    Surface(
                        color = MaterialTheme.colorScheme.tertiaryContainer,
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .padding(8.dp)
                            .clickable { viewModel.clearToast(msg) },
                    ) {
                        Row(
                            modifier = Modifier.padding(8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text(
                                text = msg,
                                color = MaterialTheme.colorScheme.onTertiaryContainer,
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.weight(1f, fill = false),
                            )
                            Icon(
                                Icons.Default.Close,
                                contentDescription = "关闭提示",
                                modifier = Modifier.size(16.dp),
                                tint = MaterialTheme.colorScheme.onTertiaryContainer,
                            )
                        }
                    }
                }

                state.errorMessage?.let { err ->
                    Surface(
                        color = MaterialTheme.colorScheme.errorContainer,
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .padding(8.dp)
                            .clickable { viewModel.clearError() },
                    ) {
                        Row(
                            modifier = Modifier.padding(8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text(
                                text = "错误: $err",
                                color = MaterialTheme.colorScheme.onErrorContainer,
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.weight(1f, fill = false),
                            )
                            Icon(
                                Icons.Default.Close,
                                contentDescription = "关闭错误",
                                modifier = Modifier.size(16.dp),
                                tint = MaterialTheme.colorScheme.onErrorContainer,
                            )
                        }
                    }
                }
            }

        }
    }

    // 派发目标选择对话框
    if (state.showDispatchDialog) {
        val skipKeys = setOf("aide", "assistant")
        val dispatchTargets = remember(state.desktopIdes) {
            state.desktopIdes
                .map { ide -> AideLinkChatViewModel.Target(ide.key, ide.name, ide.icon, ide.color) }
                .filter { it.key !in skipKeys }
                .sortedBy { it.key }
        }
        var selectedTarget by remember { mutableStateOf(dispatchTargets.firstOrNull()?.key ?: "trae") }
        AlertDialog(
            onDismissRequest = viewModel::hideDispatchSelector,
            title = { Text("选择派发目标 IDE", fontWeight = FontWeight.Bold) },
            text = {
                Column {
                    dispatchTargets.forEach { target ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { selectedTarget = target.key }
                                .padding(vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            RadioButton(
                                selected = selectedTarget == target.key,
                                onClick = { selectedTarget = target.key },
                                colors = RadioButtonDefaults.colors(selectedColor = targetColor(target.key))
                            )
                            Spacer(Modifier.width(8.dp))
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = targetColor(target.key).copy(alpha = 0.15f)
                            ) {
                                Text(
                                    text = " ${target.label} ",
                                    color = targetColor(target.key),
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                )
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    viewModel.executeDispatch(selectedTarget) { success ->
                        selectedTaskTab = taskTabAfterDispatch(selectedTaskTab, success)
                    }
                }) { Text("派发") }
            },
            dismissButton = {
                TextButton(onClick = viewModel::hideDispatchSelector) { Text("取消") }
            }
        )
    }

    if (showClipboardSheet) {
        ModalBottomSheet(
            onDismissRequest = { showClipboardSheet = false },
            sheetState = sheetState
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("剪贴板同步", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = {
                            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                            val clip = clipboard.primaryClip
                            if (clip != null && clip.itemCount > 0) {
                                val text = clip.getItemAt(0).text?.toString() ?: ""
                                if (text.isNotEmpty()) {
                                    viewModel.syncClipboardToPc(text)
                                    Toast.makeText(context, "已发送至电脑", Toast.LENGTH_SHORT).show()
                                } else {
                                    Toast.makeText(context, "手机剪贴板为空", Toast.LENGTH_SHORT).show()
                                }
                            } else {
                                Toast.makeText(context, "手机剪贴板为空", Toast.LENGTH_SHORT).show()
                            }
                        }) {
                            Text("推送手机内容")
                        }
                        TextButton(onClick = { viewModel.clearClipboard() }) {
                            Text("清空")
                        }
                    }
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))

                if (state.clipboardLoading) {
                    Box(modifier = Modifier.fillMaxWidth().height(150.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                } else if (state.clipboardItems.isEmpty()) {
                    Box(modifier = Modifier.fillMaxWidth().height(150.dp), contentAlignment = Alignment.Center) {
                        Text("无电脑剪贴板历史", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxWidth().heightIn(max = 300.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(state.clipboardItems.size) { index ->
                            val item = state.clipboardItems[index]
                            Card(
                                shape = RoundedCornerShape(8.dp),
                                modifier = Modifier.fillMaxWidth(),
                                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
                            ) {
                                Row(
                                    modifier = Modifier.padding(12.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(item.text, style = MaterialTheme.typography.bodyMedium, maxLines = 3)
                                        Spacer(modifier = Modifier.height(4.dp))
                                        Text(
                                            "${item.source} • ${item.time}",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                                        )
                                    }
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Row {
                                        IconButton(onClick = {
                                            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                            val clip = ClipData.newPlainText("AideLink Sync", item.text)
                                            clipboard.setPrimaryClip(clip)
                                            Toast.makeText(context, "已复制到手机", Toast.LENGTH_SHORT).show()
                                        }) {
                                            Icon(Icons.Default.ContentPaste, contentDescription = "复制")
                                        }
                                        IconButton(onClick = {
                                            viewModel.setInput(item.text)
                                            showClipboardSheet = false
                                        }) {
                                            Icon(Icons.Default.Send, contentDescription = "填入")
                                        }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
    if (state.showDesktopIdeDialog) {
        IdeControlDialog(
            currentTarget = state.target,
            ides = state.desktopIdes,
            desktopIdesLoading = state.desktopIdesLoading,
            ideRunningMap = state.ideRunningMap,
            projects = state.projects,
            currentProjectPath = state.currentProjectPath,
            onRefresh = viewModel::loadDesktopIdes,
            onScan = viewModel::scanDesktopIdes,
            onStart = viewModel::startIde,
            onStop = viewModel::stopIde,
            onSwitchProject = viewModel::switchIdeProject,
            onUpdateProfile = viewModel::updateIdeProfile,
            historySessions = state.ideHistorySessions,
            historyLoading = state.ideHistoryLoading,
            onLoadHistory = viewModel::loadIdeHistory,
            onOpenHistory = viewModel::openIdeHistory,
            onInstallMcp = viewModel::installMcp,
            onBindWindow = viewModel::bindIdeWindowAndCalibrate,
            onCalibrate = viewModel::openIdeCalibration,
            ocWebRunning = state.ocWebRunning,
            onOcWebToggle = viewModel::toggleOcWeb,
            onOpenSessions = {
                if (onNavigateToOpenCodeSessions != null) {
                    coroutineScope.launch {
                        val cfg = viewModel.resolveOpenCodeWebConfig()
                        if (cfg != null) onNavigateToOpenCodeSessions(cfg.url, cfg.username, cfg.password)
                    }
                }
            },
            onOpenWeb = {
                if (onNavigateToOpenCodeWeb != null) {
                    coroutineScope.launch {
                        val cfg = viewModel.resolveOpenCodeWebConfig()
                        if (cfg != null) onNavigateToOpenCodeWeb(cfg.url, cfg.username, cfg.password)
                    }
                }
            },
            onDismiss = { viewModel.setShowDesktopIdeDialog(false) }
        )
    }

    val showLiveMonitorDialog = state.showLiveMonitorDialog
    // 只在 dialogUncroppedImage 加载完成后显示对话框，避免从 monitorImage 切换导致的跳动
    if (showLiveMonitorDialog && state.dialogUncroppedImage != null) {
        ZoomableLiveMonitorDialog(
            ideName = state.target.label,
            image = state.dialogUncroppedImage!!,
            isEditing = state.dialogCropSource != null,
            cropSource = state.dialogCropSource,
            onSelectCropSource = viewModel::setDialogCropSource,
            intervalMs = state.monitorIntervalMs,
            cropLeft = state.cropLeft,
            cropRight = state.cropRight,
            cropTop = state.cropTop,
            cropBottom = state.cropBottom,
            originalWidth = state.originalImageWidth,
            originalHeight = state.originalImageHeight,
            dialogPosition = state.dialogPosition,
            focusInputEnabled = state.focusInputEnabled,
            inputPoint = state.inputPoint,
            onInputPointChange = viewModel::setInputPoint,
            onFocusInputEnabledChange = viewModel::setFocusInputEnabled,
            onBindWindow = { viewModel.bindIdeWindowAndCalibrate(state.target.key) },
            onDialogPositionChange = viewModel::setDialogPosition,
            onAdjustInterval = viewModel::adjustMonitorInterval,
            onSetInterval = viewModel::setMonitorInterval,
            onCropChange = viewModel::setCropValue,
            onCropSave = {
                viewModel.applyCropAndRefresh(
                    viewModel.state.value.cropLeft,
                    viewModel.state.value.cropRight,
                    viewModel.state.value.cropTop,
                    viewModel.state.value.cropBottom,
                )
            },
            onCropCapture = { newLeft, newRight, newTop, newBottom ->
                viewModel.applyCropAndRefresh(newLeft, newRight, newTop, newBottom)
            },
            onDismiss = { viewModel.setShowLiveMonitorDialog(false) },
            monitors = state.monitors,
            selectedMonitor = state.selectedMonitor,
            windowFound = state.windowFound,
            onSwitchMonitor = viewModel::switchDialogMonitor
        )
    }
}

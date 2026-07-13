package cc.aidelink.app.ui.screens.idechat

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.google.accompanist.swiperefresh.SwipeRefresh
import com.google.accompanist.swiperefresh.rememberSwipeRefreshState
import androidx.compose.ui.window.DialogProperties
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import cc.aidelink.app.data.repository.ConnectionStatus
import kotlinx.coroutines.launch

/**
 * 独立 IDE 聊天页面（MimoCode / OpenCode）
 * 参考 oc-remote 的 Material 3 风格设计
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun IdeChatScreen(
    onNavigateBack: () -> Unit,
    serverId: String? = null,
    viewModel: IdeChatViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val listState = rememberLazyListState()
    val coroutineScope = rememberCoroutineScope()
    var showSessionList by remember { mutableStateOf(false) }
    var showModelSelector by remember { mutableStateOf(false) }
    var showSettingsDialog by remember { mutableStateOf(false) }

    // 通过 serverId 或上次选中的服务器初始化
    LaunchedEffect(serverId) {
        if (serverId != null) {
            viewModel.initFromServerId(serverId)
        } else {
            viewModel.initFromLastSelected()
        }
    }

    val isAtBottom by remember {
        derivedStateOf {
            val layoutInfo = listState.layoutInfo
            val totalItems = layoutInfo.totalItemsCount
            val lastVisibleItem = layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0
            lastVisibleItem >= totalItems - 2
        }
    }

    LaunchedEffect(state.messages.size) {
        if (state.messages.isNotEmpty() && isAtBottom) {
            listState.animateScrollToItem(state.messages.size - 1)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            // 目标类型 + 服务器名称（只读展示）
                            Surface(
                                shape = RoundedCornerShape(16.dp),
                                color = MaterialTheme.colorScheme.secondaryContainer
                            ) {
                                Row(
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Code,
                                        contentDescription = null,
                                        modifier = Modifier.size(16.dp),
                                        tint = MaterialTheme.colorScheme.onSecondaryContainer
                                    )
                                    Text(
                                        text = state.target.displayName,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 15.sp,
                                        color = MaterialTheme.colorScheme.onSecondaryContainer
                                    )
                                    val serverName = state.currentServerName
                                    if (!serverName.isNullOrBlank()) {
                                        Text(
                                            text = "·",
                                            fontSize = 15.sp,
                                            color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.6f)
                                        )
                                        Text(
                                            text = serverName,
                                            fontSize = 13.sp,
                                            color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.8f),
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis
                                        )
                                    }
                                }
                            }

                            if (state.availableModels.isNotEmpty()) {
                                Box(modifier = Modifier.wrapContentSize()) {
                                    AssistChip(
                                        onClick = { showModelSelector = true },
                                        label = {
                                            Text(
                                                text = state.selectedModel?.substringAfter("/") ?: "选择模型",
                                                fontSize = 13.sp
                                            )
                                        },
                                        leadingIcon = {
                                            Icon(
                                                imageVector = Icons.Default.AutoAwesome,
                                                contentDescription = null,
                                                modifier = Modifier.size(14.dp)
                                            )
                                        },
                                        trailingIcon = {
                                            Icon(
                                                imageVector = Icons.Default.ArrowDropDown,
                                                contentDescription = null,
                                                modifier = Modifier.size(14.dp)
                                            )
                                        }
                                    )

                                    DropdownMenu(
                                        expanded = showModelSelector,
                                        onDismissRequest = { showModelSelector = false }
                                    ) {
                                        state.availableModels.forEach { model ->
                                            DropdownMenuItem(
                                                text = { Text(model) },
                                                onClick = {
                                                    viewModel.selectModel(model)
                                                    showModelSelector = false
                                                },
                                                leadingIcon = {
                                                    if (model == state.selectedModel) {
                                                        Icon(
                                                            imageVector = Icons.Default.Check,
                                                            contentDescription = null,
                                                            modifier = Modifier.size(18.dp)
                                                        )
                                                    }
                                                }
                                            )
                                        }
                                    }
                                }
                            }

                            // 连接状态指示点
                            Box(
                                modifier = Modifier
                                    .size(8.dp)
                                    .clip(CircleShape)
                                    .background(connectionStatusColor(state.connectionStatus))
                            )

                            // 断开时显示重连按钮
                            if (state.connectionStatus == ConnectionStatus.DISCONNECTED && state.currentServerId != null) {
                                TextButton(
                                    onClick = { viewModel.reconnect() },
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)
                                ) {
                                    Text("重连", fontSize = 12.sp)
                                }
                            }
                        }

                        val sessionLabel = state.currentSessionId?.let { "会话 ${it.take(8)}" } ?: "新会话"
                        Text(
                            text = sessionLabel,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "返回")
                    }
                },
                actions = {
                    IconButton(onClick = {
                        android.util.Log.d("IdeChatScreen", "Settings button clicked, selectedIdeList=${state.selectedIdeList}, availableIdes=${state.availableIdes.size}")
                        viewModel.loadSelectedIdeList()
                        viewModel.loadAvailableIdes()
                        showSettingsDialog = true
                    }) {
                        Icon(Icons.Default.Settings, contentDescription = "连接设置")
                    }
                    IconButton(onClick = { viewModel.toggleWebPanel(true) }) {
                        Icon(Icons.Default.Language, contentDescription = "Web 界面")
                    }
                    IconButton(onClick = { showSessionList = true }) {
                        Icon(Icons.Default.ViewList, contentDescription = "会话列表")
                    }
                    IconButton(onClick = { viewModel.loadSessions() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "刷新")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        },
        bottomBar = {
            if (state.target != Target.CLAUDE_CODE) {
                var showPlusMenu by remember { mutableStateOf(false) }
                Surface(tonalElevation = 3.dp, shadowElevation = 8.dp) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .navigationBarsPadding()
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.Bottom,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        // 加号按钮
                        Box(modifier = Modifier.wrapContentSize()) {
                            OutlinedIconButton(
                                onClick = { showPlusMenu = true },
                                modifier = Modifier.size(48.dp)
                            ) {
                                Icon(Icons.Default.Add, contentDescription = "更多")
                            }
                            DropdownMenu(
                                expanded = showPlusMenu,
                                onDismissRequest = { showPlusMenu = false }
                            ) {
                                DropdownMenuItem(
                                    text = { Text("唤醒电脑屏幕") },
                                    leadingIcon = {
                                        Icon(
                                            Icons.Default.Lightbulb,
                                            contentDescription = null,
                                            tint = Color(0xFFFFC107)
                                        )
                                    },
                                    onClick = {
                                        viewModel.wakeScreen()
                                        showPlusMenu = false
                                    }
                                )
                            }
                        }

                        OutlinedTextField(
                            value = state.input,
                            onValueChange = viewModel::updateInput,
                            modifier = Modifier.weight(1f),
                            placeholder = { Text("输入消息...") },
                            maxLines = 4,
                            shape = RoundedCornerShape(24.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = MaterialTheme.colorScheme.primary,
                                unfocusedBorderColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.5f)
                            )
                        )

                        FilledIconButton(
                            onClick = { viewModel.send() },
                            modifier = Modifier.size(48.dp),
                            enabled = state.input.isNotBlank() && !state.sending
                        ) {
                            if (state.sending) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(20.dp),
                                    strokeWidth = 2.dp
                                )
                            } else {
                                Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "发送")
                            }
                        }
                    }
                }
            }
        }
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            AnimatedVisibility(
                visible = state.toastMessage != null,
                enter = fadeIn(),
                exit = fadeOut()
            ) {
                state.toastMessage?.let { msg ->
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.tertiaryContainer
                    ) {
                        Text(
                            text = msg,
                            modifier = Modifier.padding(12.dp),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onTertiaryContainer
                        )
                    }
                }
            }

            AnimatedVisibility(
                visible = state.error != null,
                enter = fadeIn(),
                exit = fadeOut()
            ) {
                state.error?.let { err ->
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.errorContainer
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.Error,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.error,
                                modifier = Modifier.size(20.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = err,
                                modifier = Modifier.weight(1f),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onErrorContainer
                            )
                            TextButton(onClick = { viewModel.clearError() }) {
                                Text("关闭")
                            }
                        }
                    }
                }
            }

            if (state.target == Target.CLAUDE_CODE) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.Terminal,
                        contentDescription = null,
                        modifier = Modifier.size(72.dp),
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.height(20.dp))
                    Text(
                        text = "Claude Code 终端交互",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = "Claude Code 是高度交互式 TTY 终端工具，支持命令行工具调用、文件编辑与确认交互。请点击下方按钮打开 Web 终端控制台开始开发。",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center
                    )
                    Spacer(modifier = Modifier.height(24.dp))
                    Button(
                        onClick = { viewModel.toggleWebPanel(true) },
                        modifier = Modifier.fillMaxWidth(0.8f),
                        shape = RoundedCornerShape(24.dp)
                    ) {
                        Icon(Icons.Default.Language, contentDescription = null)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("打开 Web 控制台", fontSize = 15.sp)
                    }

                    if (state.serverUrl.contains("10.0.2.2")) {
                        Spacer(modifier = Modifier.height(16.dp))
                        Surface(
                            color = MaterialTheme.colorScheme.errorContainer,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.fillMaxWidth(0.9f)
                        ) {
                            Text(
                                text = "⚠️ 当前连接地址为模拟器回环地址 (10.0.2.2)，在平板真机上无法连接电脑。请点击右上角设置，将服务器地址修改为电脑的局域网 IP（例如 http://192.168.3.100:8000）并保存。",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onErrorContainer,
                                modifier = Modifier.padding(12.dp),
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center
                            )
                        }
                    }
                }
            } else if (state.messages.isEmpty() && !state.loading) {
                Column(
                    modifier = Modifier.fillMaxSize(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.ChatBubbleOutline,
                        contentDescription = null,
                        modifier = Modifier.size(64.dp),
                        tint = MaterialTheme.colorScheme.outline
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = "开始新对话",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "发送消息开始与 ${state.target.displayName} 交流",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(state.messages, key = { it.id }) { message ->
                        IdeChatMessageBubble(
                            msg = message.toBubbleItem(),
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                }
            }
        }
    }

    if (showSessionList) {
        SessionListDialog(
            sessions = state.sessions,
            currentSessionId = state.currentSessionId,
            onSessionSelect = { session ->
                viewModel.switchSession(session.id)
                showSessionList = false
            },
            onNewSession = {
                viewModel.newSession()
                showSessionList = false
            },
            onDismiss = { showSessionList = false }
        )
    }

    if (state.showWebPanel) {
        WebPanelDialog(
            url = state.serverUrl,
            navigateUrlFlow = viewModel.navigateUrl,
            onDismiss = { viewModel.toggleWebPanel(false) }
        )
    }

    if (showSettingsDialog) {
        android.util.Log.d("IdeChatScreen", "Showing settings dialog, selectedIdeList=${state.selectedIdeList}, availableIdes=${state.availableIdes.size}, bridgeUrl=${state.bridgeUrl}")
        ConnectionSettingsDialog(
            state = state,
            onSave = { url, user, pass, bridgeUrl ->
                viewModel.saveSettings(url, user, pass, bridgeUrl)
                showSettingsDialog = false
            },
            onStartServer = {
                viewModel.startIdeServer()
            },
            onReconnect = {
                viewModel.reconnect()
            },
            onDismiss = { showSettingsDialog = false },
            autoSkipLock = state.autoSkipLock,
            selectedIdeList = state.selectedIdeList,
            availableIdes = state.availableIdes,
            onAutoSkipLockChange = { viewModel.setAutoSkipLock(it) },
            onStartIde = { viewModel.startIde(it) },
            onStopIde = { viewModel.stopIde(it) }
        )
    }
}

/**
 * 连接状态对应的颜色
 */
@Composable
private fun connectionStatusColor(status: ConnectionStatus): Color {
    return when (status) {
        ConnectionStatus.CONNECTED -> Color(0xFF4CAF50)
        ConnectionStatus.CONNECTING -> Color(0xFFFFC107)
        ConnectionStatus.RECONNECTING -> Color(0xFFFFC107)
        ConnectionStatus.DISCONNECTED -> MaterialTheme.colorScheme.error
    }
}

@Composable
private fun SessionListDialog(
    sessions: List<SessionInfo>,
    currentSessionId: String?,
    onSessionSelect: (SessionInfo) -> Unit,
    onNewSession: () -> Unit,
    onDismiss: () -> Unit
) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth(0.9f)
                .fillMaxHeight(0.7f),
            shape = RoundedCornerShape(16.dp),
            tonalElevation = 6.dp
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "会话列表",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                    TextButton(onClick = onNewSession) {
                        Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("新建会话")
                    }
                }

                HorizontalDivider()

                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(8.dp)
                ) {
                    items(sessions) { session ->
                        Surface(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 2.dp),
                            onClick = { onSessionSelect(session) },
                            shape = RoundedCornerShape(12.dp),
                            color = if (session.id == currentSessionId) {
                                MaterialTheme.colorScheme.primaryContainer
                            } else {
                                MaterialTheme.colorScheme.surface
                            }
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Surface(
                                    modifier = Modifier.size(40.dp),
                                    shape = CircleShape,
                                    color = MaterialTheme.colorScheme.secondaryContainer
                                ) {
                                    Box(contentAlignment = Alignment.Center) {
                                        Icon(
                                            imageVector = Icons.Default.Code,
                                            contentDescription = null,
                                            modifier = Modifier.size(20.dp)
                                        )
                                    }
                                }

                                Spacer(modifier = Modifier.width(12.dp))

                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = session.title.ifEmpty { "未命名会话" },
                                        style = MaterialTheme.typography.bodyLarge,
                                        fontWeight = if (session.id == currentSessionId) FontWeight.Bold else FontWeight.Normal,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                    Text(
                                        text = session.id.take(8),
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }

                                if (session.id == currentSessionId) {
                                    Icon(
                                        imageVector = Icons.Default.Check,
                                        contentDescription = "当前会话",
                                        tint = MaterialTheme.colorScheme.primary,
                                        modifier = Modifier.size(20.dp)
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun IdeChatMessage.toBubbleItem(): IdeChatMessageItem {
    return IdeChatMessageItem(
        id = this.id,
        role = if (this.role == "assistant") IdeChatRole.ASSISTANT else IdeChatRole.USER,
        content = this.content,
        timestamp = "",
        isStreaming = this.isStreaming
    )
}

@Composable
private fun WebPanelDialog(
    url: String,
    onDismiss: () -> Unit,
    navigateUrlFlow: kotlinx.coroutines.flow.SharedFlow<String>? = null
) {
    val coroutineScope = rememberCoroutineScope()
    var isLoading by remember { mutableStateOf(true) }
    var canGoBack by remember { mutableStateOf(false) }
    var currentUrl by remember { mutableStateOf(url) }
    var isRefreshing by remember { mutableStateOf(false) }

    val webViewRef = remember { mutableStateOf<android.webkit.WebView?>(null) }

    // 监听外部 deep-link 导航
    LaunchedEffect(navigateUrlFlow) {
        navigateUrlFlow?.collect { deepUrl ->
            webViewRef.value?.loadUrl(deepUrl)
        }
    }

    // 系统返回键处理
    androidx.activity.compose.BackHandler(enabled = canGoBack) {
        webViewRef.value?.goBack()
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(
            usePlatformDefaultWidth = false,
            dismissOnBackPress = true,
            dismissOnClickOutside = false
        )
    ) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                // 顶部工具栏
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .statusBarsPadding()
                        .padding(horizontal = 16.dp, vertical = 12.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.weight(1f)
                    ) {
                        if (canGoBack) {
                            IconButton(
                                onClick = { webViewRef.value?.goBack() },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(Icons.AutoMirrored.Filled.ArrowBack, "后退", modifier = Modifier.size(20.dp))
                            }
                        }
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Web 界面",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                            Text(
                                text = currentUrl,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }

                    Row {
                        IconButton(onClick = { webViewRef.value?.reload() }) {
                            Icon(Icons.Default.Refresh, "刷新")
                        }
                        IconButton(onClick = onDismiss) {
                            Icon(Icons.Default.Close, "关闭")
                        }
                    }
                }

                // 加载进度条
                if (isLoading) {
                    LinearProgressIndicator(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(2.dp)
                    )
                }

                HorizontalDivider()

                // 下拉刷新 WebView
                SwipeRefresh(
                    state = rememberSwipeRefreshState(isRefreshing),
                    onRefresh = {
                        isRefreshing = true
                        webViewRef.value?.reload()
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .navigationBarsPadding()
                ) {
                    androidx.compose.ui.viewinterop.AndroidView(
                        factory = { context ->
                            android.webkit.WebView(context).apply {
                                layoutParams = android.view.ViewGroup.LayoutParams(
                                    android.view.ViewGroup.LayoutParams.MATCH_PARENT,
                                    android.view.ViewGroup.LayoutParams.MATCH_PARENT
                                )
                                settings.apply {
                                    javaScriptEnabled = true
                                    domStorageEnabled = true
                                    useWideViewPort = true
                                    loadWithOverviewMode = true
                                    databaseEnabled = true
                                    cacheMode = android.webkit.WebSettings.LOAD_DEFAULT
                                    mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                                }
                                webChromeClient = object : android.webkit.WebChromeClient() {
                                    override fun onProgressChanged(view: android.webkit.WebView?, newProgress: Int) {
                                        isLoading = newProgress < 100
                                        if (newProgress >= 100) {
                                            isRefreshing = false
                                        }
                                    }
                                }
                                webViewClient = object : android.webkit.WebViewClient() {
                                    override fun shouldOverrideUrlLoading(
                                        view: android.webkit.WebView?,
                                        request: android.webkit.WebResourceRequest?
                                    ): Boolean {
                                        request?.url?.let { uri ->
                                            currentUrl = uri.toString()
                                        }
                                        return false
                                    }

                                    override fun onPageStarted(view: android.webkit.WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                                        canGoBack = view?.canGoBack() == true
                                    }

                                    override fun onPageFinished(view: android.webkit.WebView?, url: String?) {
                                        canGoBack = view?.canGoBack() == true
                                        isLoading = false
                                        isRefreshing = false
                                    }
                                }
                                loadUrl(url)
                            }.also { webViewRef.value = it }
                        },
                        update = { webView ->
                            // WebView 已通过 factory 创建并缓存
                        },
                        modifier = Modifier.fillMaxSize()
                    )
                }
            }
        }
    }
}

@Composable
private fun ConnectionSettingsDialog(
    state: IdeChatUiState,
    onSave: (url: String, user: String, pass: String, bridgeUrl: String) -> Unit,
    onStartServer: () -> Unit,
    onReconnect: () -> Unit,
    onDismiss: () -> Unit,
    autoSkipLock: Boolean,
    selectedIdeList: List<String>,
    availableIdes: List<cc.aidelink.app.domain.model.bridge.DesktopIde>,
    onAutoSkipLockChange: (Boolean) -> Unit,
    onStartIde: (String) -> Unit,
    onStopIde: (String) -> Unit,
) {
    var url by remember(state.serverUrl) { mutableStateOf(state.serverUrl) }
    var username by remember(state.username) { mutableStateOf(state.username) }
    var password by remember(state.token) { mutableStateOf(state.token) }
    var bridgeUrl by remember(state.bridgeUrl) { mutableStateOf(state.bridgeUrl) }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            tonalElevation = 6.dp,
            modifier = Modifier
                .fillMaxWidth()
                .wrapContentHeight()
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(
                    text = "${state.target.displayName} 连接设置",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 8.dp)
                )

                // 连接状态
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(10.dp)
                            .clip(CircleShape)
                            .background(connectionStatusColor(state.connectionStatus))
                    )
                    Text(
                        text = when (state.connectionStatus) {
                            ConnectionStatus.CONNECTED -> "已连接"
                            ConnectionStatus.CONNECTING -> "连接中..."
                            ConnectionStatus.RECONNECTING -> "重连中..."
                            ConnectionStatus.DISCONNECTED -> "未连接"
                        },
                        style = MaterialTheme.typography.bodyMedium
                    )
                    if (state.connectionStatus != ConnectionStatus.CONNECTED) {
                        TextButton(onClick = onReconnect) {
                            Text("重连", fontSize = 13.sp)
                        }
                    }
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                // 当前服务器信息（只读展示）
                val currentServerName = state.currentServerName
                if (!currentServerName.isNullOrBlank()) {
                    Text(
                        text = "当前服务器",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold
                    )
                    Surface(
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            Text("名称: $currentServerName", fontSize = 13.sp)
                            Text("地址: ${state.serverUrl}", fontSize = 13.sp)
                            Text("用户: ${state.username}", fontSize = 13.sp)
                        }
                    }
                }

                // 可编辑的连接字段
                OutlinedTextField(
                    value = url,
                    onValueChange = { url = it },
                    label = { Text("服务器地址") },
                    placeholder = { Text("例如 http://192.168.1.100:4096") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                OutlinedTextField(
                    value = username,
                    onValueChange = { username = it },
                    label = { Text("用户名 (可选)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text("密码 / Token (可选)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                OutlinedTextField(
                    value = bridgeUrl,
                    onValueChange = { bridgeUrl = it },
                    label = { Text("电脑端桥接地址 (用于远程启动)") },
                    placeholder = { Text("例如 http://192.168.1.100:5000") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))

                // 自动跳过锁屏开关
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            "自动跳过锁屏",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            "唤醒时自动解锁进入桌面",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Switch(
                        checked = autoSkipLock,
                        onCheckedChange = onAutoSkipLockChange
                    )
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))

                // 桌面 IDE 远程启动/停止列表
                if (selectedIdeList.isNotEmpty()) {
                    Text(
                        "桌面 IDE",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )

                    availableIdes
                        .filter { selectedIdeList.contains(it.key) }
                        .forEach { ide ->
                            val isRunning = state.ideRunningMap[ide.key] ?: false
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 6.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(ide.name, fontWeight = FontWeight.Medium)
                                    Text(
                                        if (isRunning) "运行中" else "未运行",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = if (isRunning) Color(0xFF4CAF50) else MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                                Switch(
                                    checked = isRunning,
                                    onCheckedChange = { checked ->
                                        if (checked) onStartIde(ide.key) else onStopIde(ide.key)
                                    }
                                )
                            }
                        }

                    if (availableIdes.none { selectedIdeList.contains(it.key) }) {
                        Text(
                            "请在设置中选择要显示的桌面 IDE",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = onStartServer,
                        enabled = !state.startingServer && bridgeUrl.isNotBlank(),
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.secondary
                        )
                    ) {
                        if (state.startingServer) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                strokeWidth = 2.dp,
                                color = MaterialTheme.colorScheme.onSecondary
                            )
                        } else {
                            Text("启动服务", fontSize = 13.sp)
                        }
                    }

                    Button(
                        onClick = { onSave(url, username, password, bridgeUrl) },
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("保存", fontSize = 13.sp)
                    }
                }

                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.End)
                ) {
                    Text("取消")
                }
            }
        }
    }
}

package cc.aidelink.app.ui.screens.idechat

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import cc.aidelink.app.BuildConfig
import cc.aidelink.app.data.api.PromptPart
import cc.aidelink.app.domain.model.Message
import cc.aidelink.app.domain.model.Part
import cc.aidelink.app.domain.model.ToolState
import cc.aidelink.app.domain.model.SessionStatus
import cc.aidelink.app.ui.theme.AideLinkTheme
import kotlinx.coroutines.launch
import java.io.File

private const val TAG = "OcChatScreen"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OcChatScreen(
    onNavigateBack: () -> Unit,
    onNavigateToSession: (sessionId: String) -> Unit = {},
    viewModel: OcChatViewModel = androidx.hilt.navigation.compose.hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val draftText by viewModel.draftText.collectAsStateWithLifecycle()
    val draftAttachmentUris by viewModel.draftAttachmentUris.collectAsStateWithLifecycle()
    var inputText by remember { mutableStateOf(TextFieldValue("")) }
    var draftTextInitialized by remember { mutableStateOf(false) }
    if (!draftTextInitialized && draftText.isNotEmpty()) {
        inputText = TextFieldValue(draftText, TextRange(draftText.length))
        draftTextInitialized = true
    } else if (!draftTextInitialized) {
        draftTextInitialized = true
    }

    LaunchedEffect(Unit) {
        viewModel.revertedDraftEvent.collect { payload ->
            inputText = TextFieldValue(payload.text, TextRange(payload.text.length))
        }
    }

    val listState = rememberLazyListState()
    val coroutineScope = rememberCoroutineScope()
    val context = LocalContext.current
    val clipboardManager = LocalClipboardManager.current
    var showModelPicker by remember { mutableStateOf(false) }
    var showMenu by remember { mutableStateOf(false) }
    var showSendConfirmDialog by remember { mutableStateOf(false) }
    var pendingSendAction by remember { mutableStateOf<(() -> Unit)?>(null) }
    var inputMode by remember { mutableStateOf("NORMAL") }
    val isShellMode = inputMode == "SHELL"

    val fileSearchResults by viewModel.fileSearchResults.collectAsStateWithLifecycle()
    val confirmedFilePaths by viewModel.confirmedFilePaths.collectAsStateWithLifecycle()

    val attachments = remember { mutableStateListOf<OcImageAttachment>() }

    LaunchedEffect(draftAttachmentUris) {
        val currentUris = attachments.map { it.uri.toString() }.toSet()
        val draftUriSet = draftAttachmentUris.toSet()
        if (currentUris == draftUriSet) return@LaunchedEffect
        val restored = mutableListOf<OcImageAttachment>()
        for (uriStr in draftAttachmentUris) {
            if (uriStr in currentUris) {
                val existing = attachments.first { it.uri.toString() == uriStr }
                restored.add(existing)
                continue
            }
            try {
                val uri = Uri.parse(uriStr)
                restored.add(OcImageAttachment(uri = uri, mime = "image/png", filename = "image.png", dataUrl = uriStr))
            } catch (_: Exception) {
                viewModel.removeDraftAttachment(draftAttachmentUris.indexOf(uriStr))
            }
        }
        attachments.clear()
        attachments.addAll(restored)
    }

    val imagePickerLauncher = rememberLauncherForActivityResult(
        contract = androidx.activity.result.contract.ActivityResultContracts.GetMultipleContents()
    ) { uris: List<Uri> ->
        coroutineScope.launch {
            for (uri in uris) {
                try {
                    try {
                        context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    } catch (_: Exception) {}
                    attachments.add(OcImageAttachment(uri = uri, mime = "image/png", filename = uri.lastPathSegment ?: "image.png", dataUrl = uri.toString()))
                    viewModel.addDraftAttachment(uri.toString())
                } catch (_: Exception) {}
            }
        }
    }

    val exportLauncher = rememberLauncherForActivityResult(
        contract = androidx.activity.result.contract.ActivityResultContracts.CreateDocument("application/json")
    ) { uri: Uri? ->
        if (uri != null) {
            Toast.makeText(context, "Exporting...", Toast.LENGTH_SHORT).show()
        }
    }

    fun performSend() {
        val text = inputText.text
        val imageParts = attachments.map { att ->
            PromptPart(
                type = "image",
                url = att.dataUrl,
                mime = att.mime,
                filename = att.filename
            )
        }
        if (text.isNotBlank() || imageParts.isNotEmpty()) {
            viewModel.sendMessage(text, imageParts)
            inputText = TextFieldValue("")
            attachments.clear()
            viewModel.clearDraft()
            viewModel.clearConfirmedPaths()
            coroutineScope.launch {
                listState.animateScrollToItem(0)
            }
        }
    }

    fun sendShellCommand() {
        val cmd = inputText.text.trim()
        if (cmd.isBlank()) return
        inputText = TextFieldValue("")
        viewModel.runShellCommand(cmd) { ok ->
            coroutineScope.launch {
                if (!ok) {
                    Toast.makeText(context, "Failed to execute command", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = uiState.sessionTitle.ifBlank { "Chat" },
                            style = MaterialTheme.typography.titleMedium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        if (uiState.serverName.isNotBlank()) {
                            Text(
                                text = uiState.serverName,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    Box {
                        IconButton(onClick = { showMenu = true }) {
                            Icon(Icons.Default.MoreVert, contentDescription = "Menu")
                        }
                        DropdownMenu(
                            expanded = showMenu,
                            onDismissRequest = { showMenu = false }
                        ) {
                            DropdownMenuItem(
                                text = { Text("Model: ${uiState.selectedModelId ?: "Auto"}") },
                                onClick = {
                                    showMenu = false
                                    showModelPicker = true
                                }
                            )
                            DropdownMenuItem(
                                text = { Text("New Session") },
                                onClick = {
                                    showMenu = false
                                    viewModel.createNewSession { session ->
                                        if (session != null) {
                                            onNavigateToSession(session.id)
                                        }
                                    }
                                }
                            )
                            DropdownMenuItem(
                                text = { Text("Rename Session") },
                                onClick = { showMenu = false },
                                enabled = false
                            )
                            DropdownMenuItem(
                                text = { Text("Export Session") },
                                onClick = {
                                    showMenu = false
                                    exportLauncher.launch("session_${uiState.sessionTitle}.json")
                                }
                            )
                            DropdownMenuItem(
                                text = { Text("Abort") },
                                onClick = {
                                    showMenu = false
                                    viewModel.abortSession()
                                }
                            )
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        },
        bottomBar = {
            Surface(
                tonalElevation = 3.dp,
                shadowElevation = 8.dp
            ) {
                Column(modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) {
                    if (attachments.isNotEmpty()) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .horizontalScroll(rememberScrollState())
                                .padding(bottom = 4.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            attachments.forEachIndexed { index, att ->
                                Box {
                                    Surface(
                                        shape = RoundedCornerShape(8.dp),
                                        color = MaterialTheme.colorScheme.surfaceVariant
                                    ) {
                                        Row(
                                            modifier = Modifier.padding(4.dp),
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Icon(
                                                Icons.Default.Image,
                                                contentDescription = null,
                                                modifier = Modifier.size(20.dp),
                                                tint = MaterialTheme.colorScheme.primary
                                            )
                                            Spacer(Modifier.width(4.dp))
                                            Text(
                                                att.filename,
                                                style = MaterialTheme.typography.bodySmall,
                                                maxLines = 1
                                            )
                                            IconButton(
                                                onClick = {
                                                    attachments.removeAt(index)
                                                    viewModel.removeDraftAttachment(index)
                                                },
                                                modifier = Modifier.size(24.dp)
                                            ) {
                                                Icon(Icons.Default.Close, contentDescription = "Remove", modifier = Modifier.size(16.dp))
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.Bottom
                    ) {
                        Box(
                            modifier = Modifier
                                .weight(1f)
                                .clip(RoundedCornerShape(24.dp))
                                .background(MaterialTheme.colorScheme.surfaceVariant)
                                .padding(horizontal = 16.dp, vertical = 12.dp)
                        ) {
                            BasicTextField(
                                value = inputText,
                                onValueChange = { newValue ->
                                    inputText = newValue
                                    viewModel.updateDraftText(newValue.text)
                                },
                                textStyle = TextStyle(
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    fontSize = 16.sp
                                ),
                                cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                                keyboardOptions = KeyboardOptions(
                                    capitalization = KeyboardCapitalization.Sentences,
                                    imeAction = ImeAction.Send
                                ),
                                keyboardActions = KeyboardActions(
                                    onSend = {
                                        if (isShellMode) sendShellCommand() else performSend()
                                    }
                                ),
                                decorationBox = { innerTextField ->
                                    Box {
                                        if (inputText.text.isEmpty()) {
                                            Text(
                                                text = if (isShellMode) "Enter shell command..." else "Type a message...",
                                                style = TextStyle(
                                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
                                                    fontSize = 16.sp
                                                )
                                            )
                                        }
                                        innerTextField()
                                    }
                                },
                                modifier = Modifier.fillMaxWidth()
                            )
                        }

                        Spacer(Modifier.width(8.dp))

                        FloatingActionButton(
                            onClick = {
                                if (isShellMode) sendShellCommand() else performSend()
                            },
                            shape = CircleShape,
                            containerColor = MaterialTheme.colorScheme.primary,
                            contentColor = MaterialTheme.colorScheme.onPrimary,
                            modifier = Modifier.size(48.dp)
                        ) {
                            Icon(
                                Icons.AutoMirrored.Filled.Send,
                                contentDescription = "Send",
                                modifier = Modifier.size(24.dp)
                            )
                        }
                    }

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 4.dp),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Row {
                            AssistChip(
                                onClick = { imagePickerLauncher.launch("image/*") },
                                label = { Text("Image", fontSize = 12.sp) },
                                leadingIcon = { Icon(Icons.Default.Image, contentDescription = null, modifier = Modifier.size(16.dp)) },
                                modifier = Modifier.height(32.dp)
                            )
                            Spacer(Modifier.width(4.dp))
                            AssistChip(
                                onClick = {
                                    inputMode = if (isShellMode) "NORMAL" else "SHELL"
                                },
                                label = { Text("Shell", fontSize = 12.sp) },
                                leadingIcon = { Icon(Icons.Default.Terminal, contentDescription = null, modifier = Modifier.size(16.dp)) },
                                modifier = Modifier.height(32.dp)
                            )
                        }

                        Text(
                            text = "${uiState.messages.size} msgs",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
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
            if (uiState.isLoading && uiState.messages.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            } else if (uiState.error != null && uiState.messages.isEmpty()) {
                Column(
                    modifier = Modifier.fillMaxSize(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Icon(
                        Icons.Default.Error,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.error,
                        modifier = Modifier.size(48.dp)
                    )
                    Spacer(Modifier.height(16.dp))
                    Text(
                        text = uiState.error ?: "Unknown error",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.error
                    )
                    Spacer(Modifier.height(16.dp))
                    Button(onClick = { viewModel.loadMessages() }) {
                        Text("Retry")
                    }
                }
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    reverseLayout = true
                ) {
                    items(
                        items = uiState.messages.reversed(),
                        key = { it.message.id }
                    ) { chatMessage ->
                        OcChatMessageItem(
                            message = chatMessage,
                            isUser = chatMessage.isUser,
                            isAssistant = chatMessage.isAssistant
                        )
                    }

                    if (uiState.isLoadingOlder) {
                        item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(16.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                CircularProgressIndicator(modifier = Modifier.size(32.dp))
                            }
                        }
                    }

                    if (uiState.hasOlderMessages) {
                        item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(8.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                TextButton(onClick = { viewModel.loadOlderMessages() }) {
                                    Text("Load older messages")
                                }
                            }
                        }
                    }
                }
            }

            AnimatedVisibility(
                visible = uiState.isSending,
                enter = fadeIn(),
                exit = fadeOut(),
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 16.dp)
            ) {
                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.9f),
                    tonalElevation = 4.dp
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = when (uiState.sessionStatus) {
                                SessionStatus.Busy -> "Generating..."
                                else -> "Processing..."
                            },
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        }
    }

    if (showModelPicker) {
        OcModelPickerDialog(
            providers = uiState.providers,
            selectedProviderId = uiState.selectedProviderId,
            selectedModelId = uiState.selectedModelId,
            onSelect = { providerId, modelId ->
                viewModel.selectModel(providerId, modelId)
                showModelPicker = false
            },
            onDismiss = { showModelPicker = false }
        )
    }
}

@Composable
private fun OcChatMessageItem(
    message: OcChatMessage,
    isUser: Boolean,
    isAssistant: Boolean
) {
    val context = LocalContext.current
    val clipboardManager = LocalClipboardManager.current

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = if (isUser) Alignment.End else Alignment.Start
    ) {
        Surface(
            shape = RoundedCornerShape(
                topStart = 16.dp,
                topEnd = 16.dp,
                bottomStart = if (isUser) 16.dp else 4.dp,
                bottomEnd = if (isUser) 4.dp else 16.dp
            ),
            color = if (isUser) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surfaceVariant
            },
            tonalElevation = 1.dp,
            modifier = Modifier.widthIn(max = 320.dp)
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                message.parts.forEach { part ->
                    when (part) {
                        is Part.Text -> {
                            if (part.text.isNotBlank()) {
                                Text(
                                    text = part.text,
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = if (isUser) {
                                        MaterialTheme.colorScheme.onPrimaryContainer
                                    } else {
                                        MaterialTheme.colorScheme.onSurfaceVariant
                                    }
                                )
                            }
                        }
                        is Part.Reasoning -> {
                            if (part.text.isNotBlank()) {
                                Surface(
                                    shape = RoundedCornerShape(8.dp),
                                    color = MaterialTheme.colorScheme.tertiaryContainer.copy(alpha = 0.5f),
                                    modifier = Modifier.padding(top = 4.dp)
                                ) {
                                    Text(
                                        text = part.text,
                                        style = MaterialTheme.typography.bodySmall.copy(
                                            fontStyle = FontStyle.Italic
                                        ),
                                        color = MaterialTheme.colorScheme.onTertiaryContainer,
                                        modifier = Modifier.padding(8.dp)
                                    )
                                }
                            }
                        }
                        is Part.File -> {
                            val isImage = part.mime.startsWith("image/")
                            if (isImage) {
                                Surface(
                                    shape = RoundedCornerShape(8.dp),
                                    color = MaterialTheme.colorScheme.secondaryContainer,
                                    modifier = Modifier.padding(top = 4.dp)
                                ) {
                                    Row(
                                        modifier = Modifier.padding(8.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Icon(
                                            Icons.Default.Image,
                                            contentDescription = null,
                                            tint = MaterialTheme.colorScheme.onSecondaryContainer,
                                            modifier = Modifier.size(20.dp)
                                        )
                                        Spacer(Modifier.width(8.dp))
                                        Text(
                                            text = part.filename ?: "Image",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSecondaryContainer
                                        )
                                    }
                                }
                            } else if (part.url?.startsWith("file://") == true) {
                                Surface(
                                    shape = RoundedCornerShape(8.dp),
                                    color = MaterialTheme.colorScheme.secondaryContainer,
                                    modifier = Modifier
                                        .padding(top = 4.dp)
                                        .clickable {
                                            val filePath = part.url.removePrefix("file://")
                                            try {
                                                val file = File(filePath)
                                                if (file.exists()) {
                                                    val uri = FileProvider.getUriForFile(
                                                        context,
                                                        "${context.packageName}.fileprovider",
                                                        file
                                                    )
                                                    val intent = Intent(Intent.ACTION_VIEW).apply {
                                                        setDataAndType(uri, part.mime)
                                                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                                    }
                                                    context.startActivity(intent)
                                                }
                                            } catch (_: Exception) {}
                                        }
                                ) {
                                    Row(
                                        modifier = Modifier.padding(8.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Icon(
                                            Icons.Default.InsertDriveFile,
                                            contentDescription = null,
                                            tint = MaterialTheme.colorScheme.onSecondaryContainer,
                                            modifier = Modifier.size(20.dp)
                                        )
                                        Spacer(Modifier.width(8.dp))
                                        Text(
                                            text = part.filename ?: "File",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSecondaryContainer
                                        )
                                    }
                                }
                            }
                        }
                        is Part.Tool -> {
                            val inputMap = when (val s = part.state) {
                                is ToolState.Pending -> s.input
                                is ToolState.Running -> s.input
                                is ToolState.Completed -> s.input
                                is ToolState.Error -> s.input
                            }
                            Surface(
                                shape = RoundedCornerShape(8.dp),
                                color = MaterialTheme.colorScheme.tertiaryContainer.copy(alpha = 0.3f),
                                modifier = Modifier.padding(top = 4.dp)
                            ) {
                                Column(modifier = Modifier.padding(8.dp)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Icon(
                                            Icons.Default.Build,
                                            contentDescription = null,
                                            tint = MaterialTheme.colorScheme.onTertiaryContainer,
                                            modifier = Modifier.size(16.dp)
                                        )
                                        Spacer(Modifier.width(4.dp))
                                        Text(
                                            text = part.tool,
                                            style = MaterialTheme.typography.labelMedium,
                                            fontWeight = FontWeight.SemiBold,
                                            color = MaterialTheme.colorScheme.onTertiaryContainer
                                        )
                                    }
                                    if (inputMap.isNotEmpty()) {
                                        Text(
                                            text = inputMap.entries.joinToString("\n") { (k, v) -> "$k=$v" }.take(200),
                                            style = MaterialTheme.typography.bodySmall,
                                            fontFamily = FontFamily.Monospace,
                                            color = MaterialTheme.colorScheme.onTertiaryContainer.copy(alpha = 0.8f),
                                            modifier = Modifier.padding(top = 4.dp)
                                        )
                                    }
                                }
                            }
                        }
                        is Part.StepStart -> {}
                        is Part.StepFinish -> {}
                        is Part.Snapshot -> {}
                        is Part.Patch -> {}
                        is Part.Subtask -> {}
                        is Part.Compaction -> {}
                        is Part.Retry -> {}
                        is Part.Agent -> {}
                        is Part.Permission -> {}
                        is Part.Question -> {}
                        is Part.Abort -> {}
                        is Part.SessionTurn -> {}
                        is Part.Unknown -> {}
                    }
                }
            }
        }

        if (isAssistant) {
            Row(
                modifier = Modifier.padding(top = 2.dp, start = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                IconButton(
                    onClick = {
                        val text = message.parts.filterIsInstance<Part.Text>().joinToString("") { it.text }
                        clipboardManager.setText(AnnotatedString(text))
                        Toast.makeText(context, "Copied", Toast.LENGTH_SHORT).show()
                    },
                    modifier = Modifier.size(28.dp)
                ) {
                    Icon(
                        Icons.Default.ContentCopy,
                        contentDescription = "Copy",
                        modifier = Modifier.size(14.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                    )
                }
            }
        }
    }
}

@Composable
private fun OcModelPickerDialog(
    providers: List<cc.aidelink.app.data.api.ProviderInfo>,
    selectedProviderId: String?,
    selectedModelId: String?,
    onSelect: (String, String) -> Unit,
    onDismiss: () -> Unit
) {
    var selectedProvider by remember { mutableStateOf(selectedProviderId) }
    var selectedModel by remember { mutableStateOf(selectedModelId) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Select Model") },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 400.dp)
            ) {
                providers.forEach { provider ->
                    Text(
                        text = provider.name,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
                    )
                    provider.models.forEach { (modelId, model) ->
                        val isSelected = selectedProvider == provider.id && selectedModel == modelId
                        Surface(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    selectedProvider = provider.id
                                    selectedModel = modelId
                                },
                            shape = RoundedCornerShape(8.dp),
                            color = if (isSelected) {
                                MaterialTheme.colorScheme.primaryContainer
                            } else {
                                Color.Transparent
                            }
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(12.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = model.name,
                                        style = MaterialTheme.typography.bodyMedium
                                    )
                                    if (!model.family.isNullOrBlank()) {
                                        Text(
                                            text = model.family,
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                                if (isSelected) {
                                    Icon(
                                        Icons.Default.Check,
                                        contentDescription = "Selected",
                                        tint = MaterialTheme.colorScheme.primary
                                    )
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (selectedProvider != null && selectedModel != null) {
                        onSelect(selectedProvider!!, selectedModel!!)
                    }
                },
                enabled = selectedProvider != null && selectedModel != null
            ) {
                Text("Select")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

private data class OcImageAttachment(
    val uri: Uri,
    val mime: String,
    val filename: String,
    val dataUrl: String
)

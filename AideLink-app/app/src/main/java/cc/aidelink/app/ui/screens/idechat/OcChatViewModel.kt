package cc.aidelink.app.ui.screens.idechat

import android.util.Log
import cc.aidelink.app.BuildConfig
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import cc.aidelink.app.data.api.OpenCodeApi
import cc.aidelink.app.data.api.PromptPart
import cc.aidelink.app.data.api.ServerConnection
import cc.aidelink.app.data.repository.DraftRepository
import cc.aidelink.app.data.repository.EventReducer
import cc.aidelink.app.data.repository.SettingsRepository
import cc.aidelink.app.domain.model.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.net.URLDecoder
import javax.inject.Inject

private const val TAG = "OcChatViewModel"

data class OcChatUiState(
    val sessionTitle: String = "",
    val serverName: String = "",
    val messages: List<OcChatMessage> = emptyList(),
    val revert: Session.Revert? = null,
    val sessionStatus: SessionStatus = SessionStatus.Idle,
    val pendingPermissions: List<SseEvent.PermissionAsked> = emptyList(),
    val pendingQuestions: List<SseEvent.QuestionAsked> = emptyList(),
    val isLoading: Boolean = true,
    val error: String? = null,
    val isSending: Boolean = false,
    val providers: List<cc.aidelink.app.data.api.ProviderInfo> = emptyList(),
    val hasServerModelCatalog: Boolean = false,
    val defaultModels: Map<String, String> = emptyMap(),
    val selectedProviderId: String? = null,
    val selectedModelId: String? = null,
    val totalCost: Double = 0.0,
    val totalInputTokens: Int = 0,
    val totalOutputTokens: Int = 0,
    val agents: List<cc.aidelink.app.data.api.AgentInfo> = emptyList(),
    val selectedAgent: String = "build",
    val variantNames: List<String> = emptyList(),
    val selectedVariant: String? = null,
    val commands: List<cc.aidelink.app.data.api.CommandInfo> = emptyList(),
    val hasOlderMessages: Boolean = false,
    val isLoadingOlder: Boolean = false,
    val shareUrl: String? = null,
    val contextWindow: Int = 0,
    val lastContextTokens: Int = 0
)

data class OcRevertedDraftPayload(
    val text: String,
    val attachmentUris: List<String> = emptyList(),
)

data class OcChatMessage(
    val message: Message,
    val parts: List<Part>
) {
    val isUser: Boolean get() = message is Message.User
    val isAssistant: Boolean get() = message is Message.Assistant
}

@HiltViewModel
class OcChatViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val eventReducer: EventReducer,
    private val api: OpenCodeApi,
    private val draftRepository: DraftRepository,
    private val settingsRepository: SettingsRepository
) : ViewModel() {

    private val serverUrl: String = runCatching {
        URLDecoder.decode(savedStateHandle.get<String>("serverUrl") ?: "", "UTF-8")
    }.getOrDefault("")
    private val username: String = runCatching {
        URLDecoder.decode(savedStateHandle.get<String>("username") ?: "", "UTF-8")
    }.getOrDefault("")
    private val password: String = runCatching {
        URLDecoder.decode(savedStateHandle.get<String>("password") ?: "", "UTF-8")
    }.getOrDefault("")
    val serverName: String = runCatching {
        URLDecoder.decode(savedStateHandle.get<String>("serverName") ?: "", "UTF-8")
    }.getOrDefault("")
    private val serverId: String = runCatching {
        URLDecoder.decode(savedStateHandle.get<String>("serverId") ?: "", "UTF-8")
    }.getOrDefault("")
    val sessionId: String = runCatching {
        URLDecoder.decode(savedStateHandle.get<String>("sessionId") ?: "", "UTF-8")
    }.getOrDefault("")

    private val conn: ServerConnection = if (serverUrl.isNotBlank()) {
        ServerConnection.from(serverUrl, username, password.ifEmpty { null })
    } else {
        ServerConnection("", null)
    }

    private val _isLoading = MutableStateFlow(true)
    private val _error = MutableStateFlow<String?>(null)
    private val _isSending = MutableStateFlow(false)
    private val _allProviders = MutableStateFlow<List<cc.aidelink.app.data.api.ProviderInfo>>(emptyList())
    private val _providers = MutableStateFlow<List<cc.aidelink.app.data.api.ProviderInfo>>(emptyList())
    private val _defaultModels = MutableStateFlow<Map<String, String>>(emptyMap())
    private val _selectedProviderId = MutableStateFlow<String?>(null)
    private val _selectedModelId = MutableStateFlow<String?>(null)
    private var isModelExplicitlySelected = false
    private var sessionDirectory: String? = null
    private val sessionLoaded = CompletableDeferred<Unit>()
    private val _agents = MutableStateFlow<List<cc.aidelink.app.data.api.AgentInfo>>(emptyList())
    private val _selectedAgent = MutableStateFlow("build" to false)
    private val _selectedVariant = MutableStateFlow<String?>(null)
    private val _commands = MutableStateFlow<List<cc.aidelink.app.data.api.CommandInfo>>(emptyList())
    private val _hasOlderMessages = MutableStateFlow(false)
    private val _isLoadingOlder = MutableStateFlow(false)

    private val _draftText = MutableStateFlow("")
    val draftText: StateFlow<String> = _draftText

    private val _revertedDraftEvent = MutableSharedFlow<OcRevertedDraftPayload>(extraBufferCapacity = 1)
    val revertedDraftEvent: SharedFlow<OcRevertedDraftPayload> = _revertedDraftEvent

    private val _draftAttachmentUris = MutableStateFlow<List<String>>(emptyList())
    val draftAttachmentUris: StateFlow<List<String>> = _draftAttachmentUris

    private val _confirmedFilePaths = MutableStateFlow<Set<String>>(emptySet())
    val confirmedFilePaths: StateFlow<Set<String>> = _confirmedFilePaths

    private val _fileSearchResults = MutableStateFlow<List<String>>(emptyList())
    val fileSearchResults: StateFlow<List<String>> = _fileSearchResults

    var currentMessageLimit = 50

    val uiState: StateFlow<OcChatUiState> = combine(
        eventReducer.sessions,
        eventReducer.messages,
        eventReducer.parts,
        eventReducer.sessionStatuses,
        eventReducer.permissions,
        eventReducer.questions,
        _isLoading,
        _error,
        _isSending,
        _selectedProviderId,
        _selectedModelId,
        _allProviders,
        _providers,
        _defaultModels,
        _agents,
        _selectedAgent,
        _selectedVariant,
        _commands,
        _hasOlderMessages,
        _isLoadingOlder
    ) { args ->
        @Suppress("UNCHECKED_CAST")
        val allSessions = args[0] as List<Session>
        val allMessages = args[1] as Map<String, List<Message>>
        val allParts = args[2] as Map<String, List<Part>>
        val statuses = args[3] as Map<String, SessionStatus>
        val permissions = args[4] as Map<String, List<SseEvent.PermissionAsked>>
        val questions = args[5] as Map<String, List<SseEvent.QuestionAsked>>
        val loading = args[6] as Boolean
        val error = args[7] as String?
        val sending = args[8] as Boolean
        val selProviderId = args[9] as String?
        val selModelId = args[10] as String?
        val allProviders = args[11] as List<cc.aidelink.app.data.api.ProviderInfo>
        val providers = args[12] as List<cc.aidelink.app.data.api.ProviderInfo>
        val defaultModels = args[13] as Map<String, String>
        val agents = args[14] as List<cc.aidelink.app.data.api.AgentInfo>
        @Suppress("UNCHECKED_CAST")
        val agentSelection = args[15] as Pair<String, Boolean>
        val selectedAgent = agentSelection.first
        val isAgentExplicitlySelected = agentSelection.second
        val selectedVariant = args[16] as String?
        val commands = args[17] as List<cc.aidelink.app.data.api.CommandInfo>
        val hasOlderMessages = args[18] as Boolean
        val isLoadingOlder = args[19] as Boolean

        val session = allSessions.find { it.id == sessionId }
        val sessionMessages = allMessages[sessionId] ?: emptyList()
        val revertState = session?.revert

        val chatMessages = if (loading && sessionMessages.size < 3) {
            emptyList()
        } else {
            val sorted = sessionMessages.sortedBy { it.time.created }
            val visible = if (revertState != null) {
                sorted.filter { it.id < revertState.messageId }
            } else {
                sorted
            }
            visible.map { msg ->
                OcChatMessage(
                    message = msg,
                    parts = allParts[msg.id] ?: emptyList()
                )
            }
        }

        var effectiveProviderId = selProviderId
        var effectiveModelId = selModelId

        if (!isModelExplicitlySelected) {
            val lastUserWithModel = sessionMessages
                .filterIsInstance<Message.User>()
                .lastOrNull { it.model != null }
            if (lastUserWithModel?.model != null) {
                effectiveProviderId = lastUserWithModel.model.providerId
                effectiveModelId = lastUserWithModel.model.modelId
            } else if (effectiveModelId == null && defaultModels.isNotEmpty()) {
                val entry = defaultModels.entries.first()
                effectiveProviderId = entry.key
                effectiveModelId = entry.value
            }
        }

        val effectiveAgent = if (!isAgentExplicitlySelected) {
            val lastUserAgent = sessionMessages
                .filterIsInstance<Message.User>()
                .lastOrNull { it.agent != null }
                ?.agent
            lastUserAgent ?: selectedAgent
        } else {
            selectedAgent
        }

        if (effectiveAgent != selectedAgent && !isAgentExplicitlySelected) {
            _selectedAgent.value = effectiveAgent to false
        }

        val assistantMessages = sessionMessages.filterIsInstance<Message.Assistant>()
        val totalCost = assistantMessages.sumOf { it.cost ?: 0.0 }
        val totalInputTokens = assistantMessages.sumOf { it.tokens?.input ?: 0 }
        val totalOutputTokens = assistantMessages.sumOf { it.tokens?.output ?: 0 }
        val lastWithOutput = assistantMessages.lastOrNull { (it.tokens?.output ?: 0) > 0 }
        val lastContextTokens = lastWithOutput?.tokens?.let { t ->
            t.input + t.output + t.reasoning + t.cache.read + t.cache.write
        } ?: 0

        var currentModel = if (effectiveProviderId != null && effectiveModelId != null) {
            providers.find { it.id == effectiveProviderId }
                ?.models?.get(effectiveModelId)
        } else null
        if (currentModel == null) {
            val firstProvider = providers.firstOrNull()
            val firstModel = firstProvider?.models?.values?.firstOrNull()
            if (firstProvider != null && firstModel != null) {
                effectiveProviderId = firstProvider.id
                effectiveModelId = firstModel.id
                currentModel = firstModel
            }
        }
        val availableVariants = currentModel?.variants?.keys?.toList()?.sorted() ?: emptyList()

        OcChatUiState(
            sessionTitle = session?.title ?: "Chat",
            serverName = serverName,
            messages = chatMessages,
            revert = revertState,
            sessionStatus = statuses[sessionId] ?: SessionStatus.Idle,
            pendingPermissions = permissions[sessionId] ?: emptyList(),
            pendingQuestions = questions[sessionId] ?: emptyList(),
            isLoading = loading,
            error = error,
            isSending = sending,
            providers = providers,
            hasServerModelCatalog = allProviders.any { it.models.isNotEmpty() },
            defaultModels = defaultModels,
            selectedProviderId = effectiveProviderId,
            selectedModelId = effectiveModelId,
            totalCost = totalCost,
            totalInputTokens = totalInputTokens,
            totalOutputTokens = totalOutputTokens,
            agents = agents.filter { it.mode != "subagent" && !it.hidden },
            selectedAgent = effectiveAgent,
            variantNames = availableVariants,
            selectedVariant = if (selectedVariant != null && selectedVariant in availableVariants) selectedVariant else null,
            commands = commands,
            hasOlderMessages = hasOlderMessages,
            isLoadingOlder = isLoadingOlder,
            shareUrl = session?.share?.url,
            contextWindow = currentModel?.limit?.context ?: 0,
            lastContextTokens = lastContextTokens
        )
    }.stateIn(
        viewModelScope,
        SharingStarted.WhileSubscribed(5000),
        OcChatUiState()
    )

    init {
        val draft = draftRepository.getDraft(sessionId)
        if (draft != null) {
            _draftText.value = draft.text
            _draftAttachmentUris.value = draft.imageUris
            if (draft.confirmedFilePaths.isNotEmpty()) {
                _confirmedFilePaths.value = draft.confirmedFilePaths.toSet()
            }
            if (!draft.selectedAgent.isNullOrBlank()) {
                _selectedAgent.value = draft.selectedAgent to true
            }
            if (!draft.selectedVariant.isNullOrBlank()) {
                _selectedVariant.value = draft.selectedVariant
            }
        }

        if (serverUrl.isNotBlank()) {
            viewModelScope.launch {
                loadSession()
                loadMessages()
                loadPendingQuestions()
            }
            loadProviders()
            loadAgents()
            loadCommands()
        } else {
            _isLoading.value = false
            _error.value = "服务器地址为空，请返回重新选择"
        }
    }

    private suspend fun loadSession() {
        try {
            val session = api.getSession(conn, sessionId)
            if (session.directory.isNotBlank()) {
                sessionDirectory = session.directory
                if (BuildConfig.DEBUG) Log.d(TAG, "Session directory: ${session.directory}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to load session info", e)
        } finally {
            sessionLoaded.complete(Unit)
        }
    }

    fun loadMessages() {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                val messages = api.listMessages(conn, sessionId, limit = currentMessageLimit)
                eventReducer.setMessages(sessionId, messages)
                _hasOlderMessages.value = messages.size >= currentMessageLimit
                if (BuildConfig.DEBUG) Log.d(TAG, "Loaded ${messages.size} messages for session $sessionId (limit=$currentMessageLimit, hasOlder=${_hasOlderMessages.value})")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to load messages", e)
                if (e is OutOfMemoryError || (e.cause is OutOfMemoryError)) {
                    Log.w(TAG, "OOM loading messages, retrying with smaller limit")
                    currentMessageLimit = (currentMessageLimit / 2).coerceAtLeast(10)
                    try {
                        val messages = api.listMessages(conn, sessionId, limit = currentMessageLimit)
                        eventReducer.setMessages(sessionId, messages)
                        _hasOlderMessages.value = messages.size >= currentMessageLimit
                    } catch (retryEx: Exception) {
                        Log.e(TAG, "Retry also failed", retryEx)
                        _error.value = retryEx.message ?: "Failed to load messages"
                    }
                } else {
                    _error.value = e.message ?: "Failed to load messages"
                }
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun loadOlderMessages() {
        viewModelScope.launch {
            _isLoadingOlder.value = true
            currentMessageLimit *= 2
            try {
                val messages = api.listMessages(conn, sessionId, limit = currentMessageLimit)
                eventReducer.setMessages(sessionId, messages)
                _hasOlderMessages.value = messages.size >= currentMessageLimit
            } catch (e: Exception) {
                Log.e(TAG, "Failed to load older messages", e)
                currentMessageLimit /= 2
            } finally {
                _isLoadingOlder.value = false
            }
        }
    }

    private suspend fun loadPendingQuestions() {
        try {
            val allQuestions = api.listPendingQuestions(conn, directory = sessionDirectory)
            val sessionQuestions = allQuestions
                .filter { it.sessionId == sessionId }
                .map { req ->
                    SseEvent.QuestionAsked(
                        id = req.id,
                        sessionId = req.sessionId,
                        questions = req.questions.map { q ->
                            SseEvent.QuestionAsked.Question(
                                header = q.header,
                                question = q.question,
                                multiple = q.multiple,
                                custom = q.custom,
                                options = q.options.map { o ->
                                    SseEvent.QuestionAsked.Option(
                                        label = o.label,
                                        description = o.description
                                    )
                                }
                            )
                        },
                        tool = req.tool
                    )
                }
            if (sessionQuestions.isNotEmpty()) {
                eventReducer.setQuestions(sessionId, sessionQuestions)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to load pending questions: ${e.javaClass.simpleName}: ${e.message}", e)
        }
    }

    private fun loadProviders() {
        viewModelScope.launch {
            try {
                val response = api.getProviders(conn)
                _allProviders.value = response.providers
                _providers.value = response.providers
                _defaultModels.value = response.default
                if (BuildConfig.DEBUG) Log.d(TAG, "Loaded ${response.providers.size} providers, defaults: ${response.default}")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to load providers", e)
            }
        }
    }

    private fun loadAgents() {
        viewModelScope.launch {
            try {
                val agents = api.listAgents(conn)
                _agents.value = agents
                if (BuildConfig.DEBUG) Log.d(TAG, "Loaded ${agents.size} agents: ${agents.map { it.name }}")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to load agents", e)
            }
        }
    }

    fun selectAgent(name: String) {
        _selectedAgent.value = name to true
    }

    private fun loadCommands() {
        viewModelScope.launch {
            try {
                val commands = api.listCommands(conn)
                _commands.value = commands
                if (BuildConfig.DEBUG) Log.d(TAG, "Loaded ${commands.size} commands: ${commands.map { it.name }}")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to load commands", e)
            }
        }
    }

    fun cycleVariant() {
        val state = uiState.value
        val variants = state.variantNames
        if (variants.isEmpty()) return
        val current = _selectedVariant.value
        if (current == null || current !in variants) {
            _selectedVariant.value = variants.first()
        } else {
            val idx = variants.indexOf(current)
            _selectedVariant.value = if (idx == variants.lastIndex) null else variants[idx + 1]
        }
    }

    fun selectModel(providerId: String, modelId: String) {
        _selectedProviderId.value = providerId
        _selectedModelId.value = modelId
        isModelExplicitlySelected = true
    }

    private var fileSearchJob: Job? = null

    fun searchFilesForMention(query: String) {
        fileSearchJob?.cancel()
        if (query.isEmpty()) {
            fileSearchJob = viewModelScope.launch {
                try {
                    val results = api.findFiles(
                        conn = conn,
                        query = "",
                        dirs = "true",
                        directory = sessionDirectory,
                        limit = 15
                    )
                    _fileSearchResults.value = results
                } catch (e: Exception) {
                    Log.e(TAG, "File search failed", e)
                    _fileSearchResults.value = emptyList()
                }
            }
            return
        }
        fileSearchJob = viewModelScope.launch {
            delay(150)
            try {
                val results = api.findFiles(
                    conn = conn,
                    query = query,
                    dirs = "true",
                    directory = sessionDirectory,
                    limit = 15
                )
                _fileSearchResults.value = results
            } catch (e: Exception) {
                Log.e(TAG, "File search failed for query '$query'", e)
                _fileSearchResults.value = emptyList()
            }
        }
    }

    fun confirmFilePath(path: String) {
        _confirmedFilePaths.value = _confirmedFilePaths.value + path
    }

    fun removeFilePath(path: String) {
        _confirmedFilePaths.value = _confirmedFilePaths.value - path
    }

    fun clearFileSearch() {
        fileSearchJob?.cancel()
        _fileSearchResults.value = emptyList()
    }

    fun clearConfirmedPaths() {
        _confirmedFilePaths.value = emptySet()
    }

    fun updateDraftText(text: String) {
        _draftText.value = text
    }

    fun addDraftAttachment(uri: String) {
        _draftAttachmentUris.value = _draftAttachmentUris.value + uri
    }

    fun removeDraftAttachment(index: Int) {
        val current = _draftAttachmentUris.value.toMutableList()
        if (index in current.indices) {
            current.removeAt(index)
            _draftAttachmentUris.value = current
        }
    }

    fun clearDraft() {
        _draftText.value = ""
        _draftAttachmentUris.value = emptyList()
        draftRepository.clearDraft(sessionId)
    }

    private fun saveDraft() {
        val agentPair = _selectedAgent.value
        val draft = cc.aidelink.app.data.repository.OcDraft(
            text = _draftText.value,
            imageUris = _draftAttachmentUris.value,
            confirmedFilePaths = _confirmedFilePaths.value.toList(),
            selectedAgent = agentPair.first.takeIf { agentPair.second },
            selectedVariant = _selectedVariant.value
        )
        draftRepository.saveDraft(sessionId, draft)
    }

    override fun onCleared() {
        super.onCleared()
        saveDraft()
    }

    fun getSessionDirectory(): String? = sessionDirectory

    fun sendMessage(text: String, attachments: List<PromptPart> = emptyList()) {
        if (text.isBlank() && attachments.isEmpty()) return
        val parts = mutableListOf<PromptPart>()
        if (text.isNotBlank()) {
            parts.add(PromptPart(type = "text", text = text))
        }
        parts.addAll(attachments)
        sendParts(parts)
    }

    fun sendMessage(promptParts: List<PromptPart>, attachments: List<PromptPart>) {
        val parts = promptParts + attachments
        if (parts.isEmpty()) return
        sendParts(parts)
    }

    private fun sendParts(parts: List<PromptPart>) {
        viewModelScope.launch {
            _isSending.value = true
            try {
                val model = if (_selectedProviderId.value != null && _selectedModelId.value != null) {
                    cc.aidelink.app.data.api.ModelSelection(
                        providerId = _selectedProviderId.value!!,
                        modelId = _selectedModelId.value!!
                    )
                } else null

                api.promptAsync(
                    conn = conn,
                    sessionId = sessionId,
                    parts = parts,
                    model = model,
                    agent = uiState.value.selectedAgent,
                    variant = _selectedVariant.value,
                    directory = sessionDirectory
                )
                if (BuildConfig.DEBUG) Log.d(TAG, "Sent prompt to session $sessionId (${parts.size} parts)")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send message", e)
                _error.value = e.message ?: "Failed to send message"
            } finally {
                _isSending.value = false
            }
        }
    }

    fun replyToPermission(requestId: String, reply: String) {
        viewModelScope.launch {
            try {
                api.replyToPermission(
                    conn = conn,
                    requestId = requestId,
                    reply = reply,
                    directory = sessionDirectory
                )
            } catch (e: Exception) {
                Log.e(TAG, "Failed to reply to permission", e)
            }
        }
    }

    fun abortSession() {
        viewModelScope.launch {
            try {
                api.abortSession(conn, sessionId, directory = sessionDirectory)
                eventReducer.updateSessionStatus(sessionId, SessionStatus.Idle)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to abort session", e)
            }
        }
    }

    fun replyToQuestion(requestId: String, answers: List<List<String>>) {
        viewModelScope.launch {
            try {
                val success = api.replyToQuestion(
                    conn = conn,
                    requestId = requestId,
                    answers = answers,
                    directory = sessionDirectory
                )
                if (success) {
                    eventReducer.removeQuestion(requestId)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to reply to question $requestId: ${e.javaClass.simpleName}: ${e.message}", e)
            }
        }
    }

    fun rejectQuestion(requestId: String) {
        viewModelScope.launch {
            try {
                val success = api.rejectQuestion(conn = conn, requestId = requestId, directory = sessionDirectory)
                if (success) {
                    eventReducer.removeQuestion(requestId)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to reject question $requestId: ${e.javaClass.simpleName}: ${e.message}", e)
            }
        }
    }

    fun shareSession(onResult: (String?) -> Unit) {
        viewModelScope.launch {
            try {
                val session = api.shareSession(conn, sessionId)
                onResult(session.share?.url)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to share session", e)
                onResult(null)
            }
        }
    }

    fun unshareSession(onResult: (Boolean) -> Unit) {
        viewModelScope.launch {
            try {
                api.unshareSession(conn, sessionId)
                onResult(true)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to unshare session", e)
                onResult(false)
            }
        }
    }

    fun compactSession(onResult: (Boolean) -> Unit) {
        viewModelScope.launch {
            try {
                val state = uiState.value
                val providerId = state.selectedProviderId
                val modelId = state.selectedModelId
                if (providerId == null || modelId == null) {
                    onResult(false)
                    return@launch
                }
                api.summarizeSession(conn, sessionId, providerId, modelId)
                onResult(true)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to compact session", e)
                onResult(false)
            }
        }
    }

    fun undoMessage(onResult: (Boolean) -> Unit) {
        viewModelScope.launch {
            try {
                val messages = uiState.value.messages
                val lastUser = messages.lastOrNull { it.isUser }
                if (lastUser == null) {
                    onResult(false)
                    return@launch
                }
                api.revertSession(conn, sessionId, lastUser.message.id)
                restoreRevertedDraft(extractRevertedDraft(lastUser))
                onResult(true)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to revert session", e)
                onResult(false)
            }
        }
    }

    fun revertMessage(messageId: String, revertedText: String? = null, onResult: (Boolean) -> Unit) {
        viewModelScope.launch {
            try {
                api.revertSession(conn, sessionId, messageId)
                val targetMessage = uiState.value.messages
                    .lastOrNull { it.message.id == messageId && it.isUser }
                val fallbackPayload = OcRevertedDraftPayload(text = revertedText.orEmpty())
                restoreRevertedDraft(targetMessage?.let { extractRevertedDraft(it) } ?: fallbackPayload)
                onResult(true)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to revert to message $messageId", e)
                onResult(false)
            }
        }
    }

    private fun extractRevertedDraft(message: OcChatMessage): OcRevertedDraftPayload {
        val revertedText = message.parts
            .filterIsInstance<Part.Text>()
            .joinToString("\n") { it.text }

        val imageUris = message.parts
            .filterIsInstance<Part.File>()
            .mapNotNull { part ->
                val mime = part.mime.lowercase()
                if (mime.startsWith("image/") && !part.url.isNullOrBlank()) part.url else null
            }

        return OcRevertedDraftPayload(
            text = revertedText,
            attachmentUris = imageUris,
        )
    }

    private fun restoreRevertedDraft(payload: OcRevertedDraftPayload) {
        _draftText.value = payload.text
        _draftAttachmentUris.value = payload.attachmentUris
        _confirmedFilePaths.value = emptySet()
        _revertedDraftEvent.tryEmit(payload)
    }

    fun redoMessage(onResult: (Boolean) -> Unit) {
        viewModelScope.launch {
            try {
                api.unrevertSession(conn, sessionId)
                onResult(true)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to unrevert session", e)
                onResult(false)
            }
        }
    }

    fun forkSession(onResult: (Session?) -> Unit) {
        viewModelScope.launch {
            try {
                val session = api.forkSession(conn, sessionId)
                onResult(session)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to fork session", e)
                onResult(null)
            }
        }
    }

    fun renameSession(title: String, onResult: (Boolean) -> Unit) {
        viewModelScope.launch {
            try {
                api.updateSession(conn, sessionId, title)
                onResult(true)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to rename session", e)
                onResult(false)
            }
        }
    }

    fun executeCommand(command: String, arguments: String = "", onResult: (Boolean) -> Unit) {
        viewModelScope.launch {
            try {
                if (!sessionLoaded.isCompleted) {
                    sessionLoaded.await()
                }
                if (sessionDirectory.isNullOrBlank()) {
                    loadSession()
                }

                val normalizedCommand = command.removePrefix("/").trim()
                val effectiveDirectory = sessionDirectory
                    ?: eventReducer.sessions.value
                        .firstOrNull { it.id == sessionId }
                        ?.directory
                        ?.takeIf { it.isNotBlank() }
                val effectiveArguments = if (
                    normalizedCommand.equals("init", ignoreCase = true) && arguments.isBlank()
                ) {
                    ""
                } else {
                    arguments
                }

                val ok = api.executeCommand(
                    conn = conn,
                    sessionId = sessionId,
                    command = normalizedCommand,
                    arguments = effectiveArguments,
                    directory = effectiveDirectory
                )
                onResult(ok)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to execute command /$command", e)
                onResult(false)
            }
        }
    }

    fun runShellCommand(command: String, onResult: (Boolean) -> Unit) {
        val trimmed = command.trim()
        if (trimmed.isBlank()) {
            onResult(false)
            return
        }
        viewModelScope.launch {
            try {
                val model = if (_selectedProviderId.value != null && _selectedModelId.value != null) {
                    cc.aidelink.app.data.api.ModelSelection(
                        providerId = _selectedProviderId.value!!,
                        modelId = _selectedModelId.value!!
                    )
                } else null
                val ok = api.runShellCommand(
                    conn = conn,
                    sessionId = sessionId,
                    command = trimmed,
                    agent = uiState.value.selectedAgent,
                    model = model,
                    directory = sessionDirectory
                )
                onResult(ok)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to execute shell command", e)
                onResult(false)
            }
        }
    }

    fun createNewSession(onResult: (Session?) -> Unit) {
        viewModelScope.launch {
            try {
                val session = api.createSession(conn, directory = sessionDirectory)
                eventReducer.setSessions(serverId, listOf(session))
                onResult(session)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to create session", e)
                onResult(null)
            }
        }
    }

    fun getConnectionParams(): OcConnectionParams = OcConnectionParams(
        serverUrl = serverUrl,
        username = username,
        password = password,
        serverName = serverName,
        serverId = serverId
    )

    fun getLastAssistantText(): String? {
        val msgs = uiState.value.messages
        val last = msgs.lastOrNull { it.isAssistant } ?: return null
        return last.parts
            .filterIsInstance<Part.Text>()
            .joinToString("") { it.text }
            .ifBlank { null }
    }
}

data class OcConnectionParams(
    val serverUrl: String,
    val username: String,
    val password: String,
    val serverName: String,
    val serverId: String
)

package cc.aidelink.app.ui.screens.sessions

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import cc.aidelink.app.data.api.FileNode
import cc.aidelink.app.data.api.OpenCodeApi
import cc.aidelink.app.data.api.ServerConnection
import cc.aidelink.app.data.repository.ServerConfigRepository
import cc.aidelink.app.domain.model.Project
import cc.aidelink.app.domain.model.ServerConfig
import cc.aidelink.app.domain.model.Session
import cc.aidelink.app.domain.model.SessionStatus
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import javax.inject.Inject

private const val TAG = "SessionListViewModel"

data class SessionListUiState(
    val sessionGroups: List<ProjectSessionGroup> = emptyList(),
    val projects: List<Project> = emptyList(),
    val serverName: String = "",
    val isLoading: Boolean = true,
    val error: String? = null,
    val selectedIds: Set<String> = emptySet(),
    val isSelectionMode: Boolean = false,
)

data class ProjectSessionGroup(
    val projectId: String,
    val projectName: String,
    val directory: String,
    val sessions: List<SessionItem>,
    val sessionDirLabels: Map<String, String> = emptyMap()
)

data class SessionItem(
    val session: Session,
    val status: SessionStatus = SessionStatus.Idle
)

@HiltViewModel
class SessionListViewModel @Inject constructor(
    private val openCodeApi: OpenCodeApi,
    private val serverRepository: ServerConfigRepository
) : ViewModel() {

    private val _serverId = MutableStateFlow("")
    private val _server = MutableStateFlow<ServerConfig?>(null)
    private val _conn = MutableStateFlow<ServerConnection?>(null)

    private val _isLoading = MutableStateFlow(true)
    private val _error = MutableStateFlow<String?>(null)
    private val _projects = MutableStateFlow<List<Project>>(emptyList())
    private val _homeDir = MutableStateFlow<String?>(null)
    private val _selectedIds = MutableStateFlow<Set<String>>(emptySet())
    private val _allSessions = MutableStateFlow<List<Session>>(emptyList())
    private val _sessionStatuses = MutableStateFlow<Map<String, SessionStatus>>(emptyMap())

    private data class SessionDirInfo(val name: String, val tildePath: String)

    val uiState: StateFlow<SessionListUiState> = combine(
        _allSessions,
        _sessionStatuses,
        _isLoading,
        _error,
        _projects,
        _homeDir,
        _selectedIds,
        _server,
    ) { values ->
        val allSessions = values[0] as List<Session>
        val statuses = values[1] as Map<String, SessionStatus>
        val loading = values[2] as Boolean
        val error = values[3] as String?
        val projects = values[4] as List<Project>
        val homeDir = values[5] as String?
        val selectedIds = values[6] as Set<String>
        val server = values[7] as ServerConfig?

        val sessions = allSessions
            .filter { !it.isArchived && it.parentId == null }
            .sortedByDescending { it.time.updated }
            .map { session ->
                SessionItem(
                    session = session,
                    status = statuses[session.id] ?: SessionStatus.Idle
                )
            }

        val allItems = sessions.map { item ->
            val dir = item.session.directory.trimEnd('/').ifEmpty { "/" }
            val tildePath = if (homeDir != null && dir.startsWith(homeDir)) {
                "~" + dir.removePrefix(homeDir)
            } else {
                dir
            }
            val dirName = dir.substringAfterLast('/').ifEmpty { "/" }
            item to SessionDirInfo(dirName, tildePath)
        }

        val nonRootProjects = projects.filter { it.worktree.trimEnd('/').isNotEmpty() && it.worktree.trimEnd('/') != "/" }
        val groups = if (nonRootProjects.isNotEmpty()) {
            val assignedSessionIds = mutableSetOf<String>()
            val sortedProjects = nonRootProjects.sortedByDescending { it.worktree.trimEnd('/').length }
            sortedProjects.map { project ->
                val projectSessions = allItems.filter { item ->
                    val sid = item.first.session.id
                    sid !in assignedSessionIds &&
                        item.first.session.directory.trimEnd('/').startsWith(project.worktree.trimEnd('/'))
                }
                assignedSessionIds.addAll(projectSessions.map { it.first.session.id })
                ProjectSessionGroup(
                    projectId = project.id,
                    projectName = project.displayName,
                    directory = project.worktree,
                    sessions = projectSessions.map { it.first },
                    sessionDirLabels = projectSessions.associate { it.first.session.id to it.second.tildePath }
                )
            }.filter { it.sessions.isNotEmpty() }
        } else {
            listOf(
                ProjectSessionGroup(
                    projectId = "",
                    projectName = "",
                    directory = "",
                    sessions = allItems.map { it.first },
                    sessionDirLabels = allItems.associate { it.first.session.id to it.second.tildePath }
                )
            )
        }

        val visibleSessionIds = allItems.map { it.first.session.id }.toSet()
        val validSelectedIds = selectedIds.intersect(visibleSessionIds)

        SessionListUiState(
            sessionGroups = groups,
            projects = projects,
            serverName = server?.displayName ?: "",
            isLoading = loading,
            error = error,
            selectedIds = validSelectedIds,
            isSelectionMode = validSelectedIds.isNotEmpty(),
        )
    }.stateIn(
        viewModelScope,
        SharingStarted.WhileSubscribed(5000),
        SessionListUiState()
    )

    var navigateToSession: ((String) -> Unit)? = null

    fun setServerId(serverId: String, fallbackUrl: String = "", fallbackUsername: String = "", fallbackPassword: String = "") {
        _serverId.value = serverId
        viewModelScope.launch {
            val servers = serverRepository.getServers()
            Log.d(TAG, "setServerId: serverId=$serverId, servers=${servers.map { it.id to it.url }}")
            val server = servers.find { it.id == serverId }
            if (server != null) {
                _server.value = server
                _conn.value = ServerConnection.from(server.url, server.username, server.password)
                _serverName.value = server.displayName
                loadHomeDir()
                loadSessions()
            } else if (fallbackUrl.isNotBlank()) {
                Log.d(TAG, "setServerId: server not found in repo, using fallback: $fallbackUrl")
                val fallbackServer = ServerConfig(
                    id = serverId,
                    url = fallbackUrl,
                    username = fallbackUsername.ifBlank { "opencode" },
                    password = fallbackPassword.ifBlank { null },
                    name = "本地电脑"
                )
                _server.value = fallbackServer
                _conn.value = ServerConnection.from(fallbackUrl, fallbackUsername.ifBlank { "opencode" }, fallbackPassword.ifBlank { null })
                _serverName.value = "本地电脑"
                loadHomeDir()
                loadSessions()
            } else {
                Log.e(TAG, "setServerId: server not found, no fallback. serverId=$serverId")
                _error.value = "服务器未找到"
                _isLoading.value = false
            }
        }
    }

    private val _serverName = MutableStateFlow("")

    fun loadSessions() {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            val conn = _conn.value ?: run {
                _error.value = "未连接到服务器"
                _isLoading.value = false
                return@launch
            }
            try {
                val projects = openCodeApi.listProjects(conn)
                _projects.value = projects

                if (projects.isEmpty()) {
                    val sessions = openCodeApi.listSessions(conn)
                    _allSessions.value = sessions
                    Log.d(TAG, "Loaded ${sessions.size} sessions (no projects)")
                } else {
                    var totalSessions = 0
                    val allSessions = mutableListOf<Session>()
                    for (project in projects) {
                        try {
                            val sessions = openCodeApi.listSessions(conn, directory = project.worktree)
                            allSessions.addAll(sessions)
                            totalSessions += sessions.size
                            Log.d(TAG, "Loaded ${sessions.size} sessions for project ${project.displayName}")
                        } catch (e: Exception) {
                            Log.w(TAG, "Failed to load sessions for project ${project.displayName}: ${e.message}")
                        }
                    }
                    _allSessions.value = allSessions.distinctBy { it.id }
                    Log.d(TAG, "Total: loaded ${allSessions.size} sessions (${_allSessions.value.size} unique) across ${projects.size} projects")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to load sessions", e)
                _error.value = e.message ?: "加载会话失败"
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun createNewSession(directory: String? = null) {
        viewModelScope.launch {
            val conn = _conn.value ?: return@launch
            try {
                val session = openCodeApi.createSession(conn, directory = directory)
                _allSessions.value = _allSessions.value + session
                Log.d(TAG, "Created new session: ${session.id}")
                navigateToSession?.invoke(session.id)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to create session", e)
                _error.value = e.message ?: "创建会话失败"
            }
        }
    }

    fun deleteSession(sessionId: String) {
        viewModelScope.launch {
            val conn = _conn.value ?: return@launch
            try {
                val success = openCodeApi.deleteSession(conn, sessionId)
                if (success) {
                    _allSessions.value = _allSessions.value.filter { it.id != sessionId }
                    Log.d(TAG, "Deleted session $sessionId")
                } else {
                    _error.value = "删除会话失败"
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to delete session", e)
                _error.value = e.message ?: "删除会话失败"
            }
        }
    }

    fun toggleSelection(sessionId: String) {
        _selectedIds.update { selected ->
            if (sessionId in selected) selected - sessionId else selected + sessionId
        }
    }

    fun clearSelection() {
        _selectedIds.value = emptySet()
    }

    fun selectAll() {
        val allIds = uiState.value.sessionGroups
            .flatMap { group -> group.sessions.map { it.session.id } }
            .toSet()
        _selectedIds.value = allIds
    }

    fun deleteSelected() {
        viewModelScope.launch {
            val ids = _selectedIds.value
            if (ids.isEmpty()) return@launch
            val conn = _conn.value ?: return@launch
            try {
                val results = coroutineScope {
                    ids.map { id ->
                        async {
                            id to openCodeApi.deleteSession(conn, id)
                        }
                    }.awaitAll()
                }
                val failed = results.filterNot { it.second }
                if (failed.isNotEmpty()) {
                    _error.value = "删除 ${failed.size} 个会话失败"
                }
                _allSessions.value = _allSessions.value.filter { it.id !in ids }
                clearSelection()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to delete selected sessions", e)
                _error.value = e.message ?: "删除选中会话失败"
            }
        }
    }

    fun renameSession(sessionId: String, newTitle: String) {
        viewModelScope.launch {
            val conn = _conn.value ?: return@launch
            try {
                openCodeApi.updateSession(conn, sessionId, newTitle)
                Log.d(TAG, "Renamed session $sessionId to '$newTitle'")
                _allSessions.value = _allSessions.value.map { session ->
                    if (session.id == sessionId) session.copy(title = newTitle) else session
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to rename session", e)
                _error.value = e.message ?: "重命名会话失败"
            }
        }
    }

    private fun loadHomeDir() {
        viewModelScope.launch {
            getHomeDirectory()
        }
    }

    suspend fun getHomeDirectory(): String {
        _homeDir.value?.let { return it }
        val conn = _conn.value ?: return "/"
        return try {
            val paths = openCodeApi.getServerPaths(conn)
            val home = paths.home
            _homeDir.value = home
            Log.d(TAG, "Server home directory: $home")
            home
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get server paths", e)
            "/"
        }
    }

    suspend fun listDirectories(directory: String): List<FileNode> {
        val conn = _conn.value ?: return emptyList()
        return try {
            val nodes = openCodeApi.listDirectory(conn, path = "", directory = directory)
            nodes.filter { it.type == "directory" }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to list directory: $directory", e)
            emptyList()
        }
    }

    suspend fun searchDirectories(query: String, directory: String): List<String> {
        val conn = _conn.value ?: return emptyList()
        return try {
            openCodeApi.findFiles(conn, query = query, type = "directory", directory = directory, limit = 50)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to search directories", e)
            emptyList()
        }
    }

    suspend fun createDirectory(parentDirectory: String, folderName: String): Result<String> {
        val sanitized = folderName.trim().trim('/').replace(Regex("/+"), "/")
        if (sanitized.isBlank() || sanitized == "." || sanitized == "..") {
            return Result.failure(IllegalArgumentException("无效的文件夹名称"))
        }
        val conn = _conn.value ?: return Result.failure(IllegalStateException("未连接到服务器"))

        return runCatching {
            val targetDirectory = if (parentDirectory == "/") {
                "/$sanitized"
            } else {
                "${parentDirectory.trimEnd('/')}/$sanitized"
            }

            val tempSession = openCodeApi.createSession(
                conn = conn,
                title = "mkdir",
                directory = parentDirectory,
            )

            try {
                val escaped = sanitized.replace("'", "'\"'\"'")
                val command = "mkdir -p -- '$escaped'"

                val runShellOk = runCatching {
                    openCodeApi.runShellCommand(
                        conn = conn,
                        sessionId = tempSession.id,
                        command = command,
                        agent = "build",
                        directory = parentDirectory,
                    )
                }.getOrElse { false }

                if (!runShellOk) {
                    val executeOk = openCodeApi.executeCommand(
                        conn = conn,
                        sessionId = tempSession.id,
                        command = "bash",
                        arguments = "-lc \"$command\"",
                        directory = parentDirectory,
                    )
                    if (!executeOk) {
                        throw IllegalStateException("创建目录失败")
                    }
                }
            } finally {
                runCatching { openCodeApi.deleteSession(conn, tempSession.id) }
            }

            repeat(6) {
                if (directoryExists(targetDirectory)) {
                    return@runCatching targetDirectory
                }
                delay(200)
            }

            throw IllegalStateException("目录未被创建")
        }
    }

    private suspend fun directoryExists(directory: String): Boolean {
        val conn = _conn.value ?: return false
        return try {
            openCodeApi.listDirectory(conn, path = "", directory = directory)
            true
        } catch (_: Exception) {
            false
        }
    }
}

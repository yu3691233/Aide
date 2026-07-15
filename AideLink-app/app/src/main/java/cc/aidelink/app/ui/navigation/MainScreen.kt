package cc.aidelink.app.ui.navigation

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Cloud
import androidx.compose.material.icons.filled.Computer
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.LinkedCamera
import androidx.compose.material.icons.filled.OpenInBrowser
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.collectAsState
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.FloatingActionButtonDefaults
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.IntOffset
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.activity.ComponentActivity
import kotlin.math.roundToInt
import cc.aidelink.app.ui.screens.chat.AideLinkChatScreen
import cc.aidelink.app.ui.screens.idechat.OcChatScreen
import android.widget.Toast
import cc.aidelink.app.ui.screens.sessions.SessionListScreen
import cc.aidelink.app.ui.screens.sessions.buildOpenCodeWebSessionUrl
import cc.aidelink.app.ui.screens.settings.AideLinkSettingsScreen
import cc.aidelink.app.ui.screens.webview.WebViewScreen

sealed class BottomNavItem(val route: String, val icon: ImageVector, val label: String) {
    data object AideLink : BottomNavItem("tab_aidelink", Icons.Default.SmartToy, "Aide")
    data object DesktopIde : BottomNavItem("tab_desktop_ide", Icons.Default.Computer, "桌面IDE")
    data object Settings : BottomNavItem("tab_settings", Icons.Default.Settings, "设置")
}

/** 判断当前路由是否应该显示底部导航栏 */
private fun shouldShowBottomBar(route: String?): Boolean {
    // 在 IdeChatScreen / MiMoCode WebView 中隐藏底部导航栏
    return route != null && !route.startsWith("ide_chat") && !route.startsWith("session_list")
        && route != Screen.Chat.route && route != Screen.SessionList.route
        && !route.startsWith("mimo_webview")
}

@Composable
fun MainScreen(
    onWakeOnLan: (String) -> Unit,
) {
    val navController = rememberNavController()
    val currentBackStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = currentBackStackEntry?.destination
    val currentRoute = currentDestination?.route
    val context = LocalContext.current

    val activity = context as? ComponentActivity
    val viewModel: MainViewModel = if (activity != null) {
        hiltViewModel(activity)
    } else {
        hiltViewModel()
    }

    val bottomNavItems = listOf(
        BottomNavItem.AideLink,
        BottomNavItem.DesktopIde,
        BottomNavItem.Settings,
    )


    Box(modifier = Modifier.fillMaxSize()) {
        Scaffold { innerPadding ->
            NavHost(
                navController = navController,
                startDestination = BottomNavItem.DesktopIde.route,
                modifier = Modifier.padding(innerPadding)
            ) {
                // Tab 1: Aide（已合并，这里保留路由或者重定向，我们直接加载 AideLinkChatScreen，并且 initialTarget 传 aidelink 或 null）
                composable(BottomNavItem.AideLink.route) {
                    AideLinkChatScreen(
                        onNavigateBack = {},
                        onNavigateToSettings = { navController.navigate(BottomNavItem.Settings.route) },
                        onNavigateToOpenCodeWeb = { url, username, pwd ->
                            val encodedUrl = java.net.URLEncoder.encode(url, "UTF-8")
                            val encodedUser = java.net.URLEncoder.encode(username, "UTF-8")
                            val encodedPwd = java.net.URLEncoder.encode(pwd, "UTF-8")
                            navController.navigate("opencode_webview?url=$encodedUrl&user=$encodedUser&pwd=$encodedPwd")
                        },
                        onNavigateToOpenCodeSessions = { url, username, pwd ->
                            navController.navigate(Screen.SessionList.createRoute(url, username, pwd, "OpenCode", "aidelink-opencode"))
                        },
                        initialTarget = "aide",
                    )
                }

                // Tab 2: 桌面 IDE（注入式 IDE 对话与任务列表，合并后的主界面）
                composable(BottomNavItem.DesktopIde.route) {
                    AideLinkChatScreen(
                        onNavigateBack = {},
                        onNavigateToSettings = { navController.navigate(BottomNavItem.Settings.route) },
                        onNavigateToOpenCodeWeb = { url, username, pwd ->
                            val encodedUrl = java.net.URLEncoder.encode(url, "UTF-8")
                            val encodedUser = java.net.URLEncoder.encode(username, "UTF-8")
                            val encodedPwd = java.net.URLEncoder.encode(pwd, "UTF-8")
                            navController.navigate("opencode_webview?url=$encodedUrl&user=$encodedUser&pwd=$encodedPwd")
                        },
                        onNavigateToOpenCodeSessions = { url, username, pwd ->
                            navController.navigate(Screen.SessionList.createRoute(url, username, pwd, "OpenCode", "aidelink-opencode"))
                        },
                        initialTarget = null,
                    )
                }

                // 服务器 Tab → 会话列表（层级导航，隐藏底部栏）
                composable(
                    route = Screen.SessionList.route + "?serverUrl={serverUrl}&username={username}&password={password}&serverName={serverName}&serverId={serverId}",
                    arguments = listOf(
                        androidx.navigation.navArgument("serverUrl") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("username") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("password") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("serverName") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("serverId") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                    )
                ) { backStackEntry ->
                    val serverUrl = backStackEntry.arguments?.getString("serverUrl") ?: ""
                    val username = backStackEntry.arguments?.getString("username") ?: ""
                    val password = backStackEntry.arguments?.getString("password") ?: ""
                    val serverName = backStackEntry.arguments?.getString("serverName") ?: ""
                    val serverId = backStackEntry.arguments?.getString("serverId") ?: ""
                    SessionListScreen(
                        onNavigateToChat = { sessionId, directory ->
                            val sessionUrl = buildOpenCodeWebSessionUrl(serverUrl, directory, sessionId)
                            val encodedUrl = java.net.URLEncoder.encode(sessionUrl, "UTF-8")
                            val encodedUser = java.net.URLEncoder.encode(username, "UTF-8")
                            val encodedPwd = java.net.URLEncoder.encode(password, "UTF-8")
                            navController.navigate("opencode_webview?url=$encodedUrl&user=$encodedUser&pwd=$encodedPwd")
                        },
                        onNavigateBack = { navController.popBackStack() },
                        serverId = serverId,
                        serverUrl = serverUrl,
                        username = username,
                        password = password,
                        serverName = serverName,
                    )
                }

                // 会话列表 → 聊天（层级导航，隐藏底部栏）
                composable(
                    route = Screen.Chat.route + "?serverUrl={serverUrl}&username={username}&password={password}&serverName={serverName}&serverId={serverId}&sessionId={sessionId}&openTerminal={openTerminal}",
                    arguments = listOf(
                        androidx.navigation.navArgument("serverUrl") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("username") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("password") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("serverName") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("serverId") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("sessionId") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("openTerminal") { type = androidx.navigation.NavType.BoolType; defaultValue = false },
                    )
                ) { backStackEntry ->
                    val serverUrl = backStackEntry.arguments?.getString("serverUrl") ?: ""
                    val username = backStackEntry.arguments?.getString("username") ?: ""
                    val password = backStackEntry.arguments?.getString("password") ?: ""
                    val serverName = backStackEntry.arguments?.getString("serverName") ?: ""
                    val serverId = backStackEntry.arguments?.getString("serverId") ?: ""
                    val sessionId = backStackEntry.arguments?.getString("sessionId") ?: ""
                    OcChatScreen(
                        onNavigateBack = { navController.popBackStack() },
                        onNavigateToSession = { newSessionId ->
                            navController.navigate(
                                Screen.Chat.createRoute(serverUrl, username, password, serverName, serverId, newSessionId)
                            ) {
                                popUpTo(Screen.Chat.route) { inclusive = true }
                            }
                        },
                    )
                }



                // Tab 5: 设置
                composable(BottomNavItem.Settings.route) {
                    AideLinkSettingsScreen(onNavigateBack = { navController.navigate(BottomNavItem.DesktopIde.route) { launchSingleTop = true } })
                }

                // MiMoCode WebView（从 Aide 页面右上角进入，直接进入对应会话）
                composable(
                    route = "mimo_webview?url={url}",
                    arguments = listOf(
                        androidx.navigation.navArgument("url") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                    )
                ) { backStackEntry ->
                    val encodedUrl = backStackEntry.arguments?.getString("url") ?: ""
                    val serverUrl = java.net.URLDecoder.decode(encodedUrl, "UTF-8")
                    WebViewScreen(
                        serverUrl = serverUrl,
                        username = "",
                        password = "",
                        serverName = "MiMoCode",
                        onNavigateBack = { navController.popBackStack() },
                    )
                }

                // OpenCode WebView（从 Aide 界面右上角进入 OpenCode Web UI）
                composable(
                    route = "opencode_webview?url={url}&user={user}&pwd={pwd}",
                    arguments = listOf(
                        androidx.navigation.navArgument("url") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("user") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                        androidx.navigation.navArgument("pwd") { type = androidx.navigation.NavType.StringType; defaultValue = "" },
                    )
                ) { backStackEntry ->
                    val encodedUrl = backStackEntry.arguments?.getString("url") ?: ""
                    val encodedUser = backStackEntry.arguments?.getString("user") ?: ""
                    val encodedPwd = backStackEntry.arguments?.getString("pwd") ?: ""
                    val serverUrl = java.net.URLDecoder.decode(encodedUrl, "UTF-8")
                    val username = java.net.URLDecoder.decode(encodedUser, "UTF-8")
                    val password = java.net.URLDecoder.decode(encodedPwd, "UTF-8")
                    WebViewScreen(
                        serverUrl = serverUrl,
                        username = username,
                        password = password,
                        serverName = "OpenCode",
                        onNavigateBack = { navController.popBackStack() },
                    )
                }
            }
        }
    }
}

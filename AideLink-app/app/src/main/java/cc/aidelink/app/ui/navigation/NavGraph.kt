package cc.aidelink.app.ui.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import java.net.URLEncoder
import cc.aidelink.app.ui.screens.chat.AideLinkChatScreen
import cc.aidelink.app.ui.screens.home.AideLinkHomeScreen
import cc.aidelink.app.ui.screens.idechat.IdeChatScreen
import cc.aidelink.app.ui.screens.sessions.SessionListScreen
import cc.aidelink.app.ui.screens.settings.AideLinkSettingsScreen

object AideLinkRoutes {
    const val HOME = "home"
    const val CHAT = "chat"
    const val SESSIONS = "sessions"
    const val AIDELINK = "aide"
    const val SETTINGS = "settings"
    const val IDE_CHAT = "ide_chat"

    fun ideChatRoute(serverId: String): String = "$IDE_CHAT?serverId=${URLEncoder.encode(serverId, "UTF-8")}"
}

@Composable
fun AideLinkNavGraph(
    onWakeOnLan: (String) -> Unit,
    onOpenHappyConsole: (url: String?) -> Unit,
) {
    val nav = rememberNavController()
    NavHost(navController = nav, startDestination = AideLinkRoutes.HOME) {
        composable(AideLinkRoutes.HOME) {
            AideLinkHomeScreen(
                onNavigateToChat = { nav.navigate(AideLinkRoutes.CHAT) },
                onNavigateToSessions = { nav.navigate(AideLinkRoutes.SESSIONS) },
                onNavigateToAideLink = { nav.navigate(AideLinkRoutes.AIDELINK) },
                onNavigateToSettings = { nav.navigate(AideLinkRoutes.SETTINGS) },
                onNavigateToIdeChat = { serverId -> nav.navigate(AideLinkRoutes.ideChatRoute(serverId)) },
                onOpenHappyConsole = onOpenHappyConsole,
                onWakeOnLan = onWakeOnLan,
            )
        }
        composable(
            route = "${AideLinkRoutes.CHAT}?target={target}",
            arguments = listOf(
                navArgument("target") {
                    type = NavType.StringType
                    nullable = true
                    defaultValue = null
                }
            )
        ) { backStackEntry ->
            val target = backStackEntry.arguments?.getString("target")
            AideLinkChatScreen(
                onNavigateBack = { nav.popBackStack() },
                onNavigateToSettings = { nav.navigate(AideLinkRoutes.SETTINGS) },
                initialTarget = target
            )
        }
        composable(AideLinkRoutes.SESSIONS) {
            SessionListScreen(
                onNavigateBack = { nav.popBackStack() },
                onNavigateToChat = { sessionId, _ ->
                    nav.navigate("${AideLinkRoutes.CHAT}?target=$sessionId")
                },
            )
        }
        composable(AideLinkRoutes.AIDELINK) {
            AideLinkChatScreen(
                onNavigateBack = { nav.popBackStack() },
                onNavigateToSettings = { nav.navigate(AideLinkRoutes.SETTINGS) },
                initialTarget = "aidelink"
            )
        }
        composable(AideLinkRoutes.SETTINGS) {
            AideLinkSettingsScreen(onNavigateBack = { nav.popBackStack() })
        }

        composable(
            route = "${AideLinkRoutes.IDE_CHAT}?serverId={serverId}",
            arguments = listOf(
                navArgument("serverId") {
                    type = NavType.StringType
                    nullable = true
                    defaultValue = null
                }
            )
        ) { backStackEntry ->
            val serverId = backStackEntry.arguments?.getString("serverId")
            IdeChatScreen(
                onNavigateBack = { nav.popBackStack() },
                serverId = serverId,
            )
        }
    }
}
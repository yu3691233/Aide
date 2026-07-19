package cc.aidelink.app

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.util.Log
import android.view.View
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import cc.aidelink.app.service.ConnectionService
import cc.aidelink.app.service.UiLocatorService
import cc.aidelink.app.ui.navigation.MainScreen
import cc.aidelink.app.ui.theme.AideLinkTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var settingsRepository: cc.aidelink.app.data.repository.SettingsRepository


    private var connectionService: ConnectionService? = null
    private var serviceBound = false

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, service: IBinder?) {
            val binder = service as ConnectionService.LocalBinder
            connectionService = binder.getService()
            serviceBound = true
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            connectionService = null
            serviceBound = false
        }
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { /* 用户决定 */ }

    @Suppress("DEPRECATION")
    private val mediaProjectionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val data = result.data
        if (result.resultCode == RESULT_OK && data != null) {
            UiLocatorService.onMediaProjectionResult?.invoke(result.resultCode, data)
        } else {
            Log.w("MainActivity", "MediaProjection permission denied")
            UiLocatorService.onMediaProjectionResult?.invoke(null, null)
        }
        UiLocatorService.onMediaProjectionResult = null
        // 授权完成后立即退回后台，让用户回到原 App
        moveTaskToBack(true)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 锁屏上显示 + 点亮屏幕（Android 10+ 原生 API）
        // 仅在从 fullScreenIntent（任务完成/失败通知）拉起时启用，避免无条件设置
        // 干扰 MIUI 方向锁定磁贴状态（setShowWhenLocked 会触发系统重置方向）。
        val fromNotification = intent?.getBooleanExtra("from_notification", false) == true
        if (fromNotification) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
                setShowWhenLocked(true)
                setTurnScreenOn(true)
            } else {
                @Suppress("DEPRECATION")
                window.addFlags(
                    android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                        android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                        android.view.WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD or
                        android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                )
            }
        }

        // 传统方式：状态栏白色，导航栏正常显示
        window.statusBarColor = android.graphics.Color.WHITE
        window.navigationBarColor = android.graphics.Color.WHITE
        val flags = window.decorView.systemUiVisibility or
            android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or
            android.view.View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        window.decorView.systemUiVisibility = flags

        requestRuntimePermissions()
        startAndBindService()

        lifecycleScope.launch {
            val enabled = settingsRepository.globalLocatorEnabled.first()
            if (enabled) {
                // 检查服务是否实际运行，如果没运行则更新设置状态
                val isRunning = isServiceRunning(cc.aidelink.app.service.UiLocatorService::class.java)
                if (isRunning && android.provider.Settings.canDrawOverlays(this@MainActivity)) {
                    val locatorIntent = Intent(this@MainActivity, cc.aidelink.app.service.UiLocatorService::class.java)
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        startForegroundService(locatorIntent)
                    } else {
                        startService(locatorIntent)
                    }
                } else if (!isRunning) {
                    // 服务未运行，同步设置状态
                    settingsRepository.setGlobalLocatorEnabled(false)
                }
            }
        }


        // 处理通知点击触发的更新
        handleUpdateIntent(intent)

        // 处理 MediaProjection 请求
        handleMediaProjectionRequest(intent)

        setContent {
            AideLinkTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    MainScreen(
                        onWakeOnLan = { mac ->
                            if (serviceBound && connectionService != null) {
                                connectionService?.sendWakeOnLan(mac)
                                Toast.makeText(this, "已发送唤醒信号", Toast.LENGTH_SHORT).show()
                            } else {
                                Toast.makeText(this, "后台服务未启动", Toast.LENGTH_SHORT).show()
                            }
                        },
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // 兜底：App 从后台恢复时检查 ConnectionService 是否存活，不存活则重启
        try {
            val manager = getSystemService(Context.ACTIVITY_SERVICE) as android.app.ActivityManager
            @Suppress("DEPRECATION")
            val running = manager.getRunningServices(Integer.MAX_VALUE)
                ?.any { it.service.className == "cc.aidelink.app.service.ConnectionService" } == true
            if (!running) {
                startAndBindService()
            }
        } catch (_: Exception) {
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (serviceBound) {
            unbindService(serviceConnection)
            serviceBound = false
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleUpdateIntent(intent)
        handleMediaProjectionRequest(intent)
    }

    private fun handleMediaProjectionRequest(intent: Intent?) {
        if (intent?.getBooleanExtra("request_media_projection", false) == true) {
            val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            @Suppress("DEPRECATION")
            mediaProjectionLauncher.launch(mpm.createScreenCaptureIntent())
        }
    }

    private fun handleUpdateIntent(intent: Intent?) {
        if (intent?.getBooleanExtra("trigger_update", false) == true) {
            val versionName = intent.getStringExtra("update_version_name") ?: ""
            Toast.makeText(this, "正在下载更新 v$versionName ...", Toast.LENGTH_LONG).show()
            // 通过 Hilt 获取 SettingsViewModel 触发更新
            // 延迟执行，确保 Compose 已加载
            window.decorView.postDelayed({
                val event = android.content.Intent("cc.aidelink.app.TRIGGER_UPDATE")
                sendBroadcast(event)
            }, 500)
        }
    }

    private fun requestRuntimePermissions() {
        val needed = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) needed.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        if (needed.isNotEmpty()) requestPermissionLauncher.launch(needed.toTypedArray())
    }

    private fun startAndBindService() {
        val intent = Intent(this, ConnectionService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE)
    }

    private var terminalKeyInterceptor: ((android.view.KeyEvent) -> Boolean)? = null

    fun setTerminalKeyInterceptor(interceptor: ((android.view.KeyEvent) -> Boolean)?) {
        terminalKeyInterceptor = interceptor
    }

    override fun dispatchKeyEvent(event: android.view.KeyEvent): Boolean {
        terminalKeyInterceptor?.let { interceptor ->
            if (interceptor(event)) return true
        }
        return super.dispatchKeyEvent(event)
    }

    private fun isServiceRunning(serviceClass: Class<*>): Boolean {
        val manager = getSystemService(Context.ACTIVITY_SERVICE) as android.app.ActivityManager
        @Suppress("DEPRECATION")
        for (service in manager.getRunningServices(Int.MAX_VALUE)) {
            if (serviceClass.name == service.service.className) {
                return true
            }
        }
        return false
    }
}

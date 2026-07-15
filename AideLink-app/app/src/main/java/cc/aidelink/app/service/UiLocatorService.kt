package cc.aidelink.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.net.Uri
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Paint
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.util.DisplayMetrics
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Toast
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.app.NotificationCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import cc.aidelink.app.data.api.BridgeApi
import cc.aidelink.app.R
import cc.aidelink.app.data.repository.SettingsRepository
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import javax.inject.Inject

@Composable
private fun AdaptiveScreenshotLayout(
    modifier: Modifier = Modifier,
    controlsExpanded: Boolean,
    preview: @Composable ColumnScope.() -> Unit,
    controls: @Composable ColumnScope.() -> Unit,
) {
    Column(modifier) {
        Column(Modifier.weight(if (controlsExpanded) 0.64f else 0.90f).fillMaxWidth(), content = preview)
        Spacer(Modifier.height(8.dp))
        Column(
            Modifier
                .weight(if (controlsExpanded) 0.36f else 0.10f)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(end = 4.dp),
            content = controls,
        )
    }
}

@AndroidEntryPoint
class UiLocatorService : Service() {

    @Inject
    lateinit var bridgeApi: BridgeApi

    @Inject
    lateinit var settingsRepository: SettingsRepository

    private lateinit var windowManager: WindowManager
    private var floatView: View? = null
    private var interceptView: View? = null
    private var menuView: View? = null

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private val CHANNEL_ID = "ui_locator_service_channel"
    private val NOTIFICATION_ID = 9923

    private var mediaProjection: MediaProjection? = null
    private var captureVirtualDisplay: VirtualDisplay? = null
    private var captureImageReader: ImageReader? = null
    private var pendingCaptureAction: (suspend () -> Unit)? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        startForegroundServiceNotification()
        if (Settings.canDrawOverlays(this)) {
            showFloatingBubble()
        } else {
            serviceScope.launch { prepareOverlayPermissionAndStart() }
        }
    }

    private suspend fun prepareOverlayPermissionAndStart() {
        Toast.makeText(this, "正在通过 ADB / Root 授予悬浮窗权限…", Toast.LENGTH_SHORT).show()
        val status = WirelessAdbManager.detectStatus(this)
        if (status.deviceIp.isNotBlank()) {
            bridgeApi.deviceIp = status.deviceIp
            bridgeApi.grantOverlayPermission(status.deviceIp, status.adbPort)
            delay(250)
        }
        if (!Settings.canDrawOverlays(this) && status.adbPort > 0) {
            WirelessAdbManager.grantOverlayPermissionViaLocalAdb(this, status.adbPort)
            delay(250)
        }
        if (!Settings.canDrawOverlays(this)) {
            WirelessAdbManager.grantOverlayPermissionAsRoot()
            delay(250)
        }
        if (Settings.canDrawOverlays(this)) {
            showFloatingBubble()
            return
        }
        Toast.makeText(this, "自动授权失败，请手动开启悬浮窗权限", Toast.LENGTH_LONG).show()
        startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        })
        stopSelf()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    private fun ensureMediaProjection(onReady: suspend () -> Unit) {
        // 手机已通过无线 ADB 连接电脑，截图由 PC 端直接执行 adb screencap。
        serviceScope.launch { onReady() }
        return

        if (mediaProjection != null) {
            serviceScope.launch { onReady() }
            return
        }
        pendingCaptureAction = onReady
        onMediaProjectionResult = { resultCode, data ->
            if (resultCode != null && data != null) {
                try {
                    // Android 14+ 要求先升级前台服务类型，才能 getMediaProjection
                    if (Build.VERSION.SDK_INT >= 34) {
                        val notification = NotificationCompat.Builder(this@UiLocatorService, CHANNEL_ID)
                            .setContentTitle("截图服务就绪")
                            .setSmallIcon(android.R.drawable.ic_menu_compass)
                            .setPriority(NotificationCompat.PRIORITY_LOW)
                            .build()
                        try {
                            startForeground(
                                NOTIFICATION_ID, notification,
                                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC or
                                    android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
                            )
                            Log.d(TAG, "Foreground service upgraded to mediaProjection")
                        } catch (e: Exception) {
                            Log.e(TAG, "Failed to upgrade foreground service type", e)
                            // 升级失败，尝试不升级直接 getMediaProjection
                        }
                    }
                    val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
                    mediaProjection = mpm.getMediaProjection(resultCode, data)
                    Log.d(TAG, "MediaProjection obtained: $mediaProjection")
                    pendingCaptureAction?.let { action ->
                        pendingCaptureAction = null
                        serviceScope.launch { action() }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to get MediaProjection", e)
                    pendingCaptureAction = null
                    serviceScope.launch {
                        Toast.makeText(this@UiLocatorService, "截图初始化失败: ${e.javaClass.simpleName}: ${e.message}", Toast.LENGTH_LONG).show()
                        showFloatingBubble()
                    }
                }
            } else {
                Log.w(TAG, "MediaProjection permission denied")
                pendingCaptureAction = null
                serviceScope.launch {
                    Toast.makeText(this@UiLocatorService, "需要授权屏幕录制才能截图", Toast.LENGTH_SHORT).show()
                    showFloatingBubble()
                }
            }
        }
        // 使用独立透明 Activity 请求授权，完成后直接回到用户当前查看的应用
        val intent = Intent(this, cc.aidelink.app.MediaProjectionPermissionActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        startActivity(intent)
    }

    private fun startForegroundServiceNotification() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "UI组件定位器服务",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
        }

        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("全局组件定位器已启用")
            .setContentText("点击屏幕边缘的悬浮球可在任意应用中定位组件")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        // 明确指定 dataSync 类型启动，避免 Android 14 因 mediaProjection 权限未授予而崩溃
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIFICATION_ID, notification,
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun showFloatingBubble() {
        if (floatView != null) return

        val composeView = ComposeView(this)

        val lifecycleOwner = ServiceLifecycleOwner()
        composeView.setViewTreeLifecycleOwner(lifecycleOwner)
        composeView.setViewTreeSavedStateRegistryOwner(lifecycleOwner)

        val viewModelStore = ViewModelStore()
        val viewModelStoreOwner = object : ViewModelStoreOwner {
            override val viewModelStore: ViewModelStore = viewModelStore
        }
        composeView.setViewTreeViewModelStoreOwner(viewModelStoreOwner)

        val layoutParams = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            },
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or WindowManager.LayoutParams.FLAG_SECURE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            val prefs = getSharedPreferences("ui_locator", Context.MODE_PRIVATE)
            x = prefs.getInt("ball_x", 100)
            y = prefs.getInt("ball_y", 500)
        }

        var posX = layoutParams.x
        var posY = layoutParams.y

        fun savePosition() {
            getSharedPreferences("ui_locator", Context.MODE_PRIVATE).edit()
                .putInt("ball_x", posX)
                .putInt("ball_y", posY)
                .apply()
        }

        fun removeMenu() {
            menuView?.let {
                try { windowManager.removeView(it) } catch (_: Exception) {}
                menuView = null
            }
        }

        fun showMenuWindow() {
            removeMenu()
            val menuCompose = ComposeView(this)
            val lifecycleOwner2 = ServiceLifecycleOwner()
            menuCompose.setViewTreeLifecycleOwner(lifecycleOwner2)
            menuCompose.setViewTreeSavedStateRegistryOwner(lifecycleOwner2)
            val vmStore2 = ViewModelStore()
            menuCompose.setViewTreeViewModelStoreOwner(object : ViewModelStoreOwner {
                override val viewModelStore: ViewModelStore = vmStore2
            })

            val dm = resources.displayMetrics
            val ballSizePx = (56 * dm.density).toInt()
            val menuWidthPx = (244 * dm.density).toInt()
            val menuHeightPx = (190 * dm.density).toInt()
            val screenW = dm.widthPixels
            val screenH = dm.heightPixels
            val menuX = if (posX + ballSizePx / 2 + menuWidthPx > screenW) {
                posX - menuWidthPx
            } else {
                posX + ballSizePx
            }
            val menuY = if (posY + ballSizePx + menuHeightPx > screenH) {
                posY - menuHeightPx
            } else {
                posY + ballSizePx
            }

            val menuParams = WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                } else {
                    @Suppress("DEPRECATION")
                    WindowManager.LayoutParams.TYPE_PHONE
                },
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or WindowManager.LayoutParams.FLAG_SECURE,
                PixelFormat.TRANSLUCENT
            ).apply {
                gravity = Gravity.TOP or Gravity.START
                x = menuX
                y = menuY
            }

            menuCompose.setContent {
                Box(
                    modifier = Modifier
                        .width(244.dp)
                        .shadow(18.dp, RoundedCornerShape(22.dp))
                        .background(Color(0xFFF8FAFC), shape = RoundedCornerShape(22.dp))
                        .border(1.dp, Color.White.copy(alpha = 0.9f), RoundedCornerShape(22.dp))
                        .padding(14.dp)
                ) {
                    Column(modifier = Modifier.fillMaxWidth()) {
                        Text("AideLink 工具", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Color(0xFF0F172A))
                        Text("截图标注、组件识别与提示词", fontSize = 11.sp, color = Color(0xFF64748B))
                        Spacer(modifier = Modifier.height(12.dp))

                        fun actionModifier(color: Color, onClick: () -> Unit) = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(14.dp))
                            .background(color)
                            .clickable(onClick = onClick)
                            .padding(horizontal = 12.dp, vertical = 10.dp)

                        Row(
                            modifier = actionModifier(Color(0xFFEFF6FF)) { removeMenu(); takeScreenshotAndShowDialog {} },
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text("▣", fontSize = 22.sp, color = Color(0xFF2563EB))
                            Spacer(Modifier.width(12.dp))
                            Column {
                                Text("截图反馈", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF1E3A8A))
                                Text("标注组件并生成准确提示词", fontSize = 10.sp, color = Color(0xFF64748B))
                            }
                        }
                        HorizontalDivider(modifier = Modifier.padding(vertical = 10.dp), color = Color(0xFFE2E8F0))
                        Text(
                            "退出悬浮窗",
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Medium,
                            color = Color(0xFFDC2626),
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(10.dp))
                                .clickable { removeMenu(); serviceScope.launch { settingsRepository.setGlobalLocatorEnabled(false) }; stopSelf() }
                                .padding(horizontal = 10.dp, vertical = 8.dp),
                        )
                    }
                }
            }

            windowManager.addView(menuCompose, menuParams)
            menuView = menuCompose
        }

        var showGlow = true

        composeView.setContent {
            Box(
                modifier = Modifier.size(56.dp),
                contentAlignment = Alignment.Center
            ) {
                if (showGlow) {
                    Box(modifier = Modifier.size(56.dp).clip(CircleShape).background(Color(0xFF4CAF50).copy(alpha = 0.25f)))
                }
                Box(
                    modifier = Modifier
                        .size(48.dp)
                        .clip(CircleShape)
                        .pointerInput(Unit) {
                            detectTapGestures(
                                onTap = {
                                    showGlow = true
                                    if (menuView != null) removeMenu() else showMenuWindow()
                                }
                            )
                        }
                        .pointerInput(Unit) {
                            detectDragGesturesAfterLongPress(
                                onDragStart = { showGlow = true; removeMenu() },
                                onDrag = { change, dragAmount ->
                                    change.consume()
                                    posX += dragAmount.x.toInt()
                                    posY += dragAmount.y.toInt()
                                    layoutParams.x = posX
                                    layoutParams.y = posY
                                    windowManager.updateViewLayout(composeView, layoutParams)
                                },
                                onDragEnd = { savePosition() }
                            )
                        },
                    contentAlignment = Alignment.Center
                ) {
                    Image(
                        painter = painterResource(id = R.drawable.ic_launcher_foreground),
                        contentDescription = "AideLink",
                        modifier = Modifier.size(48.dp).clip(CircleShape),
                        contentScale = ContentScale.Fit
                    )
                }
            }
        }

        floatView = composeView
        windowManager.addView(composeView, layoutParams)
    }

    /**
     * 使用 MediaProjection 在手机本地截图，返回 PNG ByteArray。
     * 保持 VirtualDisplay 存活复用，避免 Android 14 禁止重复 createVirtualDisplay。
     */
    private suspend fun capturePhoneScreen(): ByteArray? = withContext(Dispatchers.IO) {
        bridgeApi.capturePhoneScreenshot()?.let { return@withContext it }
        WirelessAdbManager.captureRootScreenshot(this@UiLocatorService)?.let {
            return@withContext it
        }
        val mp = mediaProjection ?: return@withContext null

        // 首次使用时初始化 VirtualDisplay 和 ImageReader
        if (captureVirtualDisplay == null || captureImageReader == null) {
            val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
            val metrics = DisplayMetrics()
            @Suppress("DEPRECATION")
            wm.defaultDisplay.getRealMetrics(metrics)
            val width = metrics.widthPixels
            val height = metrics.heightPixels
            val dpi = metrics.densityDpi

            val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
            captureImageReader = reader

            if (Build.VERSION.SDK_INT >= 34) {
                mp.registerCallback(object : android.media.projection.MediaProjection.Callback() {
                    override fun onStop() {
                        captureVirtualDisplay?.release()
                        captureVirtualDisplay = null
                        captureImageReader?.close()
                        captureImageReader = null
                    }
                }, null)
            }

            captureVirtualDisplay = mp.createVirtualDisplay(
                "AideLinkCapture",
                width, height, dpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader.surface, null, null
            )
        }

        val reader = captureImageReader ?: return@withContext null
        try {
            delay(200)
            val image = reader.acquireLatestImage() ?: return@withContext null
            val plane = image.planes[0]
            val rowStride = plane.rowStride
            val pixelStride = plane.pixelStride
            val width = image.width
            val height = image.height
            val rowPadding = rowStride - pixelStride * width
            val bmp = Bitmap.createBitmap(width + rowPadding / pixelStride, height, Bitmap.Config.ARGB_8888)
            bmp.copyPixelsFromBuffer(plane.buffer)
            image.close()
            val cropped = Bitmap.createBitmap(bmp, 0, 0, width, height)
            if (cropped !== bmp) bmp.recycle()
            val out = java.io.ByteArrayOutputStream()
            cropped.compress(Bitmap.CompressFormat.PNG, 100, out)
            cropped.recycle()
            out.toByteArray()
        } catch (e: Exception) {
            Log.e(TAG, "capturePhoneScreen failed", e)
            null
        }
    }

    private fun captureAndLocate(onComplete: () -> Unit) {
        serviceScope.launch {
            try {
                val resp = withContext(Dispatchers.IO) { bridgeApi.captureUiLocator() }
                if (resp.ok) {
                    showInterceptOverlay(onComplete)
                } else {
                    Toast.makeText(this@UiLocatorService, "同步失败: ${resp.error}", Toast.LENGTH_SHORT).show()
                    onComplete()
                }
            } catch (e: Exception) {
                Toast.makeText(this@UiLocatorService, "网络错误: ${e.message}", Toast.LENGTH_SHORT).show()
                onComplete()
            }
        }
    }

    private fun takeScreenshotAndShowDialog(onComplete: () -> Unit) {
        hideFloatingBubble()
        ensureMediaProjection {
            try {
                // 等用户回到原 App（Activity 已 moveTaskToBack）
                delay(800)
                val pngData = capturePhoneScreen()
                if (pngData == null) {
                    Toast.makeText(this@UiLocatorService, "截图失败", Toast.LENGTH_SHORT).show()
                    showFloatingBubble()
                    onComplete()
                    return@ensureMediaProjection
                }
                // 在弹窗出现前尽力转储 UI 结构，后续按标注中心点补充组件信息。
                // 失败不阻断截图反馈，仍可由 Aide 直接理解截图。
                val locatorReady = withContext(Dispatchers.IO) {
                    runCatching { bridgeApi.captureUiLocator(bridgeApi.deviceIp).ok }.getOrDefault(false)
                }
                // 复用 IDE 管理页的数据源；运行状态只用于决定默认选中项。
                val ideData: Pair<List<Pair<String, String>>, Set<String>> = withContext(Dispatchers.IO) {
                    try {
                        val configured = bridgeApi.getDesktopIdes()
                            .filter { it.key.isNotBlank() && it.key != "oc_web" }
                        val runningKeys = bridgeApi.getIdeProcesses()
                            .filter { it.running }
                            .map { it.key }
                            .toSet()
                        val options = configured
                            .distinctBy { it.key }
                            .map { ide ->
                                val name = ide.name.ifBlank { ide.key }
                                ide.key to if (ide.key in runningKeys) "● $name" else name
                            }
                        options to runningKeys
                    } catch (_: Exception) {
                        emptyList<Pair<String, String>>() to emptySet()
                    }
                }
                val (ideOptions, runningKeys) = ideData
                val defaultIde = ideOptions.firstOrNull { it.first in runningKeys }?.first
                    ?: ideOptions.firstOrNull()?.first.orEmpty()
                showScreenshotDialog(
                    pngData,
                    null,
                    onComplete,
                    ideOptions = ideOptions,
                    defaultIde = defaultIde,
                    locatorReady = locatorReady,
                )
            } catch (e: Exception) {
                Toast.makeText(this@UiLocatorService, "截图错误: ${e.message}", Toast.LENGTH_SHORT).show()
                showFloatingBubble()
                onComplete()
            }
        }
    }

    private fun showScreenshotDialog(
        screenshotData: ByteArray,
        imageUrl: String?,
        onComplete: () -> Unit,
        ideOptions: List<Pair<String, String>> = emptyList(),
        defaultIde: String = "",
        locatorReady: Boolean = false,
        autoInjected: Boolean = false,
    ) {
        val composeView = ComposeView(this)
        val lifecycleOwner = ServiceLifecycleOwner()
        composeView.setViewTreeLifecycleOwner(lifecycleOwner)
        composeView.setViewTreeSavedStateRegistryOwner(lifecycleOwner)
        
        val viewModelStore = ViewModelStore()
        val viewModelStoreOwner = object : ViewModelStoreOwner {
            override val viewModelStore: ViewModelStore = viewModelStore
        }
        composeView.setViewTreeViewModelStoreOwner(viewModelStoreOwner)

        val layoutParams = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            },
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        )

        interceptView = composeView

        composeView.setContent {
            var inputText by remember { mutableStateOf("") }
            var isSending by remember { mutableStateOf(false) }
            var isGeneratingPrompt by remember { mutableStateOf(false) }
            var generatedPrompt by remember { mutableStateOf("") }
            var recognitionSummary by remember { mutableStateOf("") }
            var controlsExpanded by remember { mutableStateOf(false) }
            var pasteScreenshot by remember { mutableStateOf(true) }
            var selectedIde by remember { mutableStateOf(defaultIde) }
            var selections by remember { mutableStateOf(emptyList<Pair<Offset, Offset>>()) }
            var cropSelection by remember { mutableStateOf<Pair<Offset, Offset>?>(null) }
            var toolMode by remember { mutableStateOf("box") }
            var activeStart by remember { mutableStateOf<Offset?>(null) }
            var activeEnd by remember { mutableStateOf<Offset?>(null) }
            val screenshotBitmap = remember(screenshotData) {
                BitmapFactory.decodeByteArray(screenshotData, 0, screenshotData.size)?.asImageBitmap()
            }
            val previewBitmap = remember(screenshotData, cropSelection) {
                val source = BitmapFactory.decodeByteArray(screenshotData, 0, screenshotData.size)
                if (source == null) null else {
                    val cropped = cropSelection?.let { (start, end) ->
                        val left = (minOf(start.x, end.x) * source.width).toInt().coerceIn(0, source.width - 1)
                        val top = (minOf(start.y, end.y) * source.height).toInt().coerceIn(0, source.height - 1)
                        val right = (maxOf(start.x, end.x) * source.width).toInt().coerceIn(left + 1, source.width)
                        val bottom = (maxOf(start.y, end.y) * source.height).toInt().coerceIn(top + 1, source.height)
                        Bitmap.createBitmap(source, left, top, right - left, bottom - top).also { source.recycle() }
                    } ?: source
                    cropped.asImageBitmap()
                }
            }

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color(0xFF0F172A).copy(alpha = 0.58f))
                    .clickable { /* 阻止点击穿透 */ },
                contentAlignment = Alignment.Center
            ) {
                Column(
                    modifier = Modifier
                        .padding(horizontal = 12.dp, vertical = 8.dp)
                        .fillMaxWidth()
                        .fillMaxHeight(0.98f)
                        .shadow(20.dp, RoundedCornerShape(24.dp))
                        .background(Color(0xFFF8FAFC), shape = RoundedCornerShape(24.dp))
                        .padding(14.dp)
                ) {
                    AdaptiveScreenshotLayout(
                        modifier = Modifier.fillMaxWidth().weight(1f),
                        controlsExpanded = controlsExpanded,
                        preview = {
                    Row(Modifier.fillMaxSize()) {
                        Column(
                            modifier = Modifier
                                .width(68.dp)
                                .fillMaxHeight()
                                .padding(vertical = 8.dp)
                                .background(Color.White, RoundedCornerShape(18.dp))
                                .border(1.dp, Color(0xFFE2E8F0), RoundedCornerShape(18.dp))
                                .padding(7.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterVertically),
                            horizontalAlignment = Alignment.CenterHorizontally,
                        ) {
                            Text(
                                text = if (toolMode == "box") "框选\n使用中" else "框选",
                                fontSize = if (toolMode == "box") 11.sp else 12.sp,
                                lineHeight = 14.sp,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                fontWeight = FontWeight.SemiBold,
                                color = if (toolMode == "box") Color.White else Color(0xFF334155),
                                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
                                    .background(if (toolMode == "box") Color(0xFF2563EB) else Color(0xFFF1F5F9))
                                    .clickable(enabled = !isSending) { toolMode = "box" }
                                    .padding(vertical = if (toolMode == "box") 8.dp else 14.dp),
                            )
                            Text(
                                text = if (toolMode == "crop") "裁剪\n使用中" else "裁剪",
                                fontSize = if (toolMode == "crop") 11.sp else 12.sp,
                                lineHeight = 14.sp,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                fontWeight = FontWeight.SemiBold,
                                color = if (toolMode == "crop") Color.White else Color(0xFF166534),
                                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
                                    .background(if (toolMode == "crop") Color(0xFF16A34A) else Color(0xFFF0FDF4))
                                    .clickable(enabled = !isSending) { toolMode = "crop" }
                                    .padding(vertical = if (toolMode == "crop") 8.dp else 14.dp),
                            )
                            val canUndo = selections.isNotEmpty() && !isSending
                            Text(
                                "撤销",
                                fontSize = 12.sp,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                color = if (canUndo) Color(0xFF475569) else Color(0xFFCBD5E1),
                                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
                                    .background(Color(0xFFF8FAFC))
                                    .clickable(enabled = canUndo) { selections = selections.dropLast(1) }
                                    .padding(vertical = 14.dp),
                            )
                            val canReset = (selections.isNotEmpty() || cropSelection != null) && !isSending
                            Text(
                                "重置",
                                fontSize = 12.sp,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                color = if (canReset) Color(0xFFDC2626) else Color(0xFFFECACA),
                                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
                                    .background(if (canReset) Color(0xFFFEF2F2) else Color(0xFFFFFBFB))
                                    .clickable(enabled = canReset) { selections = emptyList(); cropSelection = null }
                                    .padding(vertical = 14.dp),
                            )
                        }
                        Spacer(Modifier.width(6.dp))
                    Box(
                        modifier = Modifier.weight(1f).fillMaxHeight(),
                        contentAlignment = Alignment.Center,
                    ) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .pointerInput(previewBitmap) {
                                fun normalizedPoint(point: Offset): Offset {
                                    val bitmap = previewBitmap ?: return Offset.Zero
                                    val scale = minOf(
                                        size.width / bitmap.width.toFloat(),
                                        size.height / bitmap.height.toFloat(),
                                    )
                                    val shownWidth = bitmap.width * scale
                                    val shownHeight = bitmap.height * scale
                                    val offsetX = (size.width - shownWidth) / 2f
                                    val offsetY = (size.height - shownHeight) / 2f
                                    return Offset(
                                        ((point.x - offsetX) / shownWidth).coerceIn(0f, 1f),
                                        ((point.y - offsetY) / shownHeight).coerceIn(0f, 1f),
                                    )
                                }
                                detectDragGestures(
                                    onDragStart = { point ->
                                        activeStart = normalizedPoint(point)
                                        activeEnd = activeStart
                                    },
                                    onDrag = { change, _ ->
                                        activeEnd = normalizedPoint(change.position)
                                    },
                                    onDragEnd = {
                                        val start = activeStart
                                        val end = activeEnd
                                        if (start != null && end != null &&
                                            (kotlin.math.abs(start.x - end.x) > 0.01f ||
                                                kotlin.math.abs(start.y - end.y) > 0.01f)
                                        ) {
                                            if (toolMode == "crop") {
                                                val baseLeft = cropSelection?.let { minOf(it.first.x, it.second.x) } ?: 0f
                                                val baseTop = cropSelection?.let { minOf(it.first.y, it.second.y) } ?: 0f
                                                val baseRight = cropSelection?.let { maxOf(it.first.x, it.second.x) } ?: 1f
                                                val baseBottom = cropSelection?.let { maxOf(it.first.y, it.second.y) } ?: 1f
                                                val baseWidth = baseRight - baseLeft
                                                val baseHeight = baseBottom - baseTop
                                                cropSelection = Offset(
                                                    baseLeft + minOf(start.x, end.x) * baseWidth,
                                                    baseTop + minOf(start.y, end.y) * baseHeight,
                                                ) to Offset(
                                                    baseLeft + maxOf(start.x, end.x) * baseWidth,
                                                    baseTop + maxOf(start.y, end.y) * baseHeight,
                                                )
                                                selections = emptyList()
                                                toolMode = "box"
                                            } else {
                                                selections = selections + (start to end)
                                            }
                                        }
                                        activeStart = null
                                        activeEnd = null
                                    },
                                    onDragCancel = {
                                        activeStart = null
                                        activeEnd = null
                                    },
                                )
                            },
                    ) {
                        previewBitmap?.let { bitmap ->
                            Image(
                                bitmap = bitmap,
                                contentDescription = "待标注截图",
                                modifier = Modifier.fillMaxSize(),
                                contentScale = ContentScale.Fit,
                            )
                        }
                        androidx.compose.foundation.Canvas(Modifier.fillMaxSize()) {
                            val bitmap = previewBitmap ?: return@Canvas
                            val scale = minOf(
                                size.width / bitmap.width.toFloat(),
                                size.height / bitmap.height.toFloat(),
                            )
                            val shownWidth = bitmap.width * scale
                            val shownHeight = bitmap.height * scale
                            val offsetX = (size.width - shownWidth) / 2f
                            val offsetY = (size.height - shownHeight) / 2f
                            val activeBox = activeStart?.let { start -> activeEnd?.let { end -> start to end } }
                            val boxes = selections + if (toolMode == "box") listOfNotNull(activeBox) else emptyList()
                            boxes.forEachIndexed { index, (start, end) ->
                                val left = offsetX + minOf(start.x, end.x) * shownWidth
                                val top = offsetY + minOf(start.y, end.y) * shownHeight
                                val right = offsetX + maxOf(start.x, end.x) * shownWidth
                                val bottom = offsetY + maxOf(start.y, end.y) * shownHeight
                                drawRect(
                                    color = Color.Red.copy(alpha = 0.12f),
                                    topLeft = Offset(left, top),
                                    size = androidx.compose.ui.geometry.Size(right - left, bottom - top),
                                )
                                drawRect(
                                    color = Color.Red,
                                    topLeft = Offset(left, top),
                                    size = androidx.compose.ui.geometry.Size(right - left, bottom - top),
                                    style = Stroke(width = 4.dp.toPx()),
                                )
                                drawCircle(
                                    color = Color.Red,
                                    radius = 11.dp.toPx(),
                                    center = Offset(left + 11.dp.toPx(), top + 11.dp.toPx()),
                                )
                                drawContext.canvas.nativeCanvas.drawText(
                                    "${index + 1}",
                                    left + 11.dp.toPx(),
                                    top + 15.dp.toPx(),
                                    Paint(Paint.ANTI_ALIAS_FLAG).apply {
                                        color = android.graphics.Color.WHITE
                                        textAlign = Paint.Align.CENTER
                                        textSize = 12.dp.toPx()
                                        typeface = android.graphics.Typeface.DEFAULT_BOLD
                                    },
                                )
                            }
                            val crop = if (toolMode == "crop") activeBox else null
                            crop?.let { (start, end) ->
                                val left = offsetX + minOf(start.x, end.x) * shownWidth
                                val top = offsetY + minOf(start.y, end.y) * shownHeight
                                val right = offsetX + maxOf(start.x, end.x) * shownWidth
                                val bottom = offsetY + maxOf(start.y, end.y) * shownHeight
                                drawRect(Color.Black.copy(alpha = 0.38f), Offset(offsetX, offsetY), androidx.compose.ui.geometry.Size(shownWidth, top - offsetY))
                                drawRect(Color.Black.copy(alpha = 0.38f), Offset(offsetX, bottom), androidx.compose.ui.geometry.Size(shownWidth, offsetY + shownHeight - bottom))
                                drawRect(Color.Black.copy(alpha = 0.38f), Offset(offsetX, top), androidx.compose.ui.geometry.Size(left - offsetX, bottom - top))
                                drawRect(Color.Black.copy(alpha = 0.38f), Offset(right, top), androidx.compose.ui.geometry.Size(offsetX + shownWidth - right, bottom - top))
                                drawRect(
                                    color = Color(0xFF22C55E),
                                    topLeft = Offset(left, top),
                                    size = androidx.compose.ui.geometry.Size(right - left, bottom - top),
                                    style = Stroke(width = 3.dp.toPx()),
                                )
                            }
                        }
                    }
                    }
                    }

                        },
                        controls = {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .clickable(enabled = !isSending) { controlsExpanded = !controlsExpanded }
                            .padding(horizontal = 8.dp, vertical = 5.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(
                            if (generatedPrompt.isNotBlank()) "提示词与说明 · 已生成" else if (inputText.isNotBlank()) "提示词与说明 · 已填写" else "提示词与说明",
                            fontSize = 11.sp,
                            color = Color(0xFF64748B),
                        )
                        Text(if (controlsExpanded) "⌄" else "⌃", fontSize = 13.sp, color = Color(0xFF64748B))
                    }
                    HorizontalDivider(color = Color(0xFFE2E8F0))
                    if (controlsExpanded) {

                    Text(
                        text = "发送目标",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = Color(0xFF334155)
                    )
                    Spacer(modifier = Modifier.height(7.dp))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .horizontalScroll(rememberScrollState())
                    ) {
                        ideOptions.forEach { (key, label) ->
                            val isSelected = selectedIde == key
                            Text(
                                text = label,
                                fontSize = 12.sp,
                                color = if (isSelected) Color.White else Color(0xFF1976D2),
                                modifier = Modifier
                                    .clip(RoundedCornerShape(50.dp))
                                    .background(if (isSelected) Color(0xFF2563EB) else Color.White)
                                    .border(
                                        1.dp,
                                        if (isSelected) Color(0xFF2563EB) else Color(0xFFBFDBFE),
                                        RoundedCornerShape(50.dp),
                                    )
                                    .padding(horizontal = 12.dp, vertical = 8.dp)
                                    .clickable {
                                        selectedIde = key
                                    }
                            )
                        }
                    }
                    if (ideOptions.isEmpty()) {
                        Text(
                            text = "暂无可用 IDE，请先在设置中添加或扫描 IDE",
                            fontSize = 12.sp,
                            color = Color(0xFFD32F2F),
                        )
                    }
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth().clickable { pasteScreenshot = !pasteScreenshot },
                    ) {
                        androidx.compose.material3.Checkbox(
                            checked = pasteScreenshot,
                            onCheckedChange = { pasteScreenshot = it },
                        )
                        Column {
                            Text("粘贴截图", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF334155))
                            Text("发送前先粘贴标注截图，再发送提示词", fontSize = 10.sp, color = Color(0xFF64748B))
                        }
                    }

                    Spacer(modifier = Modifier.height(14.dp))

                    Text(
                        text = "补充说明（可选）",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = Color(0xFF334155)
                    )
                    Spacer(modifier = Modifier.height(7.dp))

                    androidx.compose.material3.OutlinedTextField(
                        value = inputText,
                        onValueChange = { inputText = it },
                        placeholder = { Text("例如：点击这里没有反应") },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(72.dp),
                        textStyle = androidx.compose.ui.text.TextStyle(fontSize = 14.sp)
                    )
                    }

                    Spacer(modifier = Modifier.height(8.dp))
                    val generatePromptAction: () -> Unit = {
                            if (!isGeneratingPrompt) {
                                isGeneratingPrompt = true
                                serviceScope.launch {
                                    try {
                                        val finalImage = createAnnotatedScreenshot(screenshotData, selections, cropSelection)
                                        val tempFile = File(cacheDir, "prompt_${System.currentTimeMillis()}.png")
                                        tempFile.writeBytes(finalImage)
                                        val upload = try {
                                            withContext(Dispatchers.IO) {
                                                bridgeApi.uploadImage(tempFile.absolutePath, tempFile.name, toClipboard = false)
                                            }
                                        } finally {
                                            tempFile.delete()
                                        }
                                        if (!upload.ok) throw IllegalStateException(upload.raw.ifBlank { "截图上传失败" })

                                        val located = if (locatorReady && selections.isNotEmpty()) {
                                            withContext(Dispatchers.IO) {
                                                selections.mapIndexedNotNull { index, (start, end) ->
                                                    val cropLeft = cropSelection?.let { minOf(it.first.x, it.second.x) } ?: 0f
                                                    val cropTop = cropSelection?.let { minOf(it.first.y, it.second.y) } ?: 0f
                                                    val cropWidth = cropSelection?.let { kotlin.math.abs(it.first.x - it.second.x) } ?: 1f
                                                    val cropHeight = cropSelection?.let { kotlin.math.abs(it.first.y - it.second.y) } ?: 1f
                                                    val centerX = ((cropLeft + (start.x + end.x) / 2f * cropWidth) * (screenshotBitmap?.width ?: 1)).toInt()
                                                    val centerY = ((cropTop + (start.y + end.y) / 2f * cropHeight) * (screenshotBitmap?.height ?: 1)).toInt()
                                                    val result = bridgeApi.locateUiElement(
                                                        centerX,
                                                        centerY,
                                                        screenshotBitmap?.width ?: 1,
                                                        screenshotBitmap?.height ?: 1,
                                                    )
                                                    if (!result.ok || result.element == null) null else {
                                                        val element = result.element
                                                        val identity = listOf(
                                                            element.text.takeIf { it.isNotBlank() }?.let { "文本=$it" },
                                                            element.content_desc.takeIf { it.isNotBlank() }?.let { "描述=$it" },
                                                            element.resource_id.takeIf { it.isNotBlank() }?.let { "ID=${it.substringAfterLast('/')}" },
                                                            element.`class`.takeIf { it.isNotBlank() }?.let { "类型=${it.substringAfterLast('.')}" },
                                                        ).filterNotNull().joinToString("，")
                                                        val code = result.matched_code?.file?.substringAfterLast('/')
                                                        "红框 ${index + 1}: ${identity.ifBlank { "未命名组件" }}" +
                                                            (code?.let { "，候选代码=$it" } ?: "")
                                                    }
                                                }
                                            }
                                        } else emptyList()
                                        recognitionSummary = if (located.isEmpty()) {
                                            "未取得可靠的结构化组件信息，将以截图和标注意图为准"
                                        } else located.joinToString("\n")
                                        val result = withContext(Dispatchers.IO) {
                                            bridgeApi.composePrompt(
                                                platform = "Android App",
                                                componentName = located.joinToString("；"),
                                                userText = inputText.ifBlank {
                                                    "【用户未描述具体需求】请只识别截图红框中的页面、组件和当前可见状态，不要推断用户想如何修改；在提示词中明确列出需要用户确认的问题。"
                                                },
                                                taskType = "auto",
                                                location = recognitionSummary,
                                                image = upload.url ?: upload.path,
                                            )
                                        }
                                        if (!result.ok) throw IllegalStateException(result.message ?: "提示词生成失败")
                                        generatedPrompt = result.prompt
                                        controlsExpanded = true
                                    } catch (e: Exception) {
                                        Toast.makeText(this@UiLocatorService, "生成失败: ${e.message}", Toast.LENGTH_SHORT).show()
                                    }
                                    isGeneratingPrompt = false
                                }
                            }
                    }
                    if (controlsExpanded && generatedPrompt.isNotBlank()) {
                        Text(recognitionSummary, fontSize = 10.sp, color = Color(0xFF64748B), maxLines = 2)
                        androidx.compose.material3.OutlinedTextField(
                            value = generatedPrompt,
                            onValueChange = { generatedPrompt = it },
                            label = { Text("发送前请确认 IDE 对页面和组件的理解") },
                            modifier = Modifier.fillMaxWidth().height(112.dp),
                            textStyle = androidx.compose.ui.text.TextStyle(fontSize = 12.sp),
                        )
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        androidx.compose.material3.OutlinedButton(
                            onClick = {
                                removeInterceptOverlay()
                                showFloatingBubble()
                                onComplete()
                            },
                            modifier = Modifier.weight(1f),
                            enabled = !isSending,
                        ) {
                            Text("关闭", fontWeight = FontWeight.Medium)
                        }
                        androidx.compose.material3.OutlinedButton(
                            onClick = generatePromptAction,
                            modifier = Modifier.weight(1f),
                            enabled = !isGeneratingPrompt && !isSending,
                        ) {
                            Text(if (isGeneratingPrompt) "识别中" else "AI识别", fontWeight = FontWeight.Medium)
                        }
                        androidx.compose.material3.OutlinedButton(
                            onClick = {
                                if (!isSending) {
                                    isSending = true
                                    serviceScope.launch {
                                        try {
                                            val finalImage = createAnnotatedScreenshot(
                                                screenshotData,
                                                selections,
                                                cropSelection,
                                            )
                                            val tempFile = File(cacheDir, "annotated_${System.currentTimeMillis()}.png")
                                            tempFile.writeBytes(finalImage)
                                            val upload = try {
                                                withContext(Dispatchers.IO) {
                                                    bridgeApi.uploadImage(
                                                        tempFile.absolutePath,
                                                        tempFile.name,
                                                        toClipboard = true,
                                                    )
                                                }
                                            } finally {
                                                tempFile.delete()
                                            }
                                            if (!upload.ok) {
                                                throw IllegalStateException(upload.raw.ifBlank { "复制截图失败" })
                                            }
                                            Toast.makeText(
                                                this@UiLocatorService,
                                                "标注截图已复制到电脑剪切板",
                                                Toast.LENGTH_SHORT,
                                            ).show()
                                        } catch (e: Exception) {
                                            Toast.makeText(
                                                this@UiLocatorService,
                                                "复制失败: ${e.message}",
                                                Toast.LENGTH_SHORT,
                                            ).show()
                                        }
                                        isSending = false
                                    }
                                }
                            },
                            modifier = Modifier.weight(1f),
                            enabled = !isSending,
                        ) {
                            Text(if (isSending) "处理中" else "仅复制", fontWeight = FontWeight.Medium)
                        }
                        androidx.compose.material3.Button(
                            onClick = {
                                if (!isSending) {
                                    isSending = true
                                    serviceScope.launch {
                                        try {
                                            if (pasteScreenshot) {
                                                val finalImage = createAnnotatedScreenshot(
                                                    screenshotData,
                                                    selections,
                                                    cropSelection,
                                                )
                                                val tempFile = File(cacheDir, "annotated_${System.currentTimeMillis()}.png")
                                                tempFile.writeBytes(finalImage)
                                                val upload = try {
                                                    withContext(Dispatchers.IO) {
                                                        bridgeApi.uploadImage(tempFile.absolutePath, tempFile.name, toClipboard = true)
                                                    }
                                                } finally {
                                                    tempFile.delete()
                                                }
                                                if (!upload.ok) throw IllegalStateException(upload.raw.ifBlank { "截图上传失败" })
                                                val injected = withContext(Dispatchers.IO) { bridgeApi.injectClipboard(selectedIde) }
                                                if (!injected) throw IllegalStateException("截图粘贴到 IDE 失败")
                                                delay(350)
                                            }
                                            val regionText = selections.mapIndexed { index, (start, end) ->
                                                    val left = (minOf(start.x, end.x) * 100).toInt().coerceIn(0, 100)
                                                    val top = (minOf(start.y, end.y) * 100).toInt().coerceIn(0, 100)
                                                    val right = (maxOf(start.x, end.x) * 100).toInt().coerceIn(0, 100)
                                                    val bottom = (maxOf(start.y, end.y) * 100).toInt().coerceIn(0, 100)
                                                    "\n【红框 ${index + 1}】左上 ${left}%,${top}%；右下 ${right}%,${bottom}%"
                                            }.joinToString("")
                                            val message = if (generatedPrompt.isNotBlank()) {
                                                "【截图反馈 · AI 生成提示词】\n$generatedPrompt$regionText"
                                            } else if (inputText.isNotBlank()) {
                                                "【截图说明】\n${inputText}$regionText"
                                            } else {
                                                "【截图】$regionText"
                                            }
                                            withContext(Dispatchers.IO) {
                                                bridgeApi.send(message, selectedIde)
                                            }
                                            Toast.makeText(this@UiLocatorService, "截图已发送到 ${selectedIde.uppercase()}", Toast.LENGTH_SHORT).show()
                                        } catch (e: Exception) {
                                            Toast.makeText(this@UiLocatorService, "发送失败: ${e.message}", Toast.LENGTH_SHORT).show()
                                        }
                                        removeInterceptOverlay()
                                        showFloatingBubble()
                                        onComplete()
                                    }
                                }
                            },
                            modifier = Modifier.weight(1f),
                            enabled = !isSending && selectedIde.isNotBlank()
                        ) {
                            Text(if (isSending) "发送中" else "发送", fontWeight = FontWeight.SemiBold)
                        }
                    }
                        },
                    )
                }
            }
        }

        windowManager.addView(composeView, layoutParams)
    }

    private fun createAnnotatedScreenshot(
        screenshotData: ByteArray,
        selections: List<Pair<Offset, Offset>>,
        cropSelection: Pair<Offset, Offset>? = null,
    ): ByteArray {
        if (selections.isEmpty() && cropSelection == null) return screenshotData
        val source = BitmapFactory.decodeByteArray(screenshotData, 0, screenshotData.size)
            ?: return screenshotData
        val croppedSource = cropSelection?.let { (start, end) ->
            val left = (minOf(start.x, end.x) * source.width).toInt().coerceIn(0, source.width - 1)
            val top = (minOf(start.y, end.y) * source.height).toInt().coerceIn(0, source.height - 1)
            val right = (maxOf(start.x, end.x) * source.width).toInt().coerceIn(left + 1, source.width)
            val bottom = (maxOf(start.y, end.y) * source.height).toInt().coerceIn(top + 1, source.height)
            Bitmap.createBitmap(source, left, top, right - left, bottom - top).also { source.recycle() }
        } ?: source
        val bitmap = croppedSource.copy(Bitmap.Config.ARGB_8888, true)
        croppedSource.recycle()
        val canvas = android.graphics.Canvas(bitmap)
        val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.argb(35, 255, 0, 0)
            style = Paint.Style.FILL
        }
        val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.RED
            style = Paint.Style.STROKE
            strokeWidth = (bitmap.width / 180f).coerceAtLeast(6f)
        }
        val numberPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.WHITE
            textAlign = Paint.Align.CENTER
            textSize = (bitmap.width / 55f).coerceAtLeast(24f)
            typeface = android.graphics.Typeface.DEFAULT_BOLD
        }
        selections.forEachIndexed { index, (start, end) ->
            val left = minOf(start.x, end.x) * bitmap.width
            val top = minOf(start.y, end.y) * bitmap.height
            val right = maxOf(start.x, end.x) * bitmap.width
            val bottom = maxOf(start.y, end.y) * bitmap.height
            canvas.drawRect(left, top, right, bottom, fill)
            canvas.drawRect(left, top, right, bottom, stroke)
            val radius = (bitmap.width / 45f).coerceAtLeast(22f)
            canvas.drawCircle(left + radius, top + radius, radius, Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = android.graphics.Color.RED
            })
            canvas.drawText("${index + 1}", left + radius, top + radius + numberPaint.textSize * 0.35f, numberPaint)
        }
        val output = java.io.ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
        bitmap.recycle()
        return output.toByteArray()
    }

    private fun takeScreenshotForPrompt(onComplete: () -> Unit) {
        hideFloatingBubble()
        ensureMediaProjection {
            try {
                delay(500)
                val pngData = capturePhoneScreen()
                var imageUrl: String? = null
                if (pngData != null) {
                    val tempFile = File(cacheDir, "prompt_screen_${System.currentTimeMillis()}.png")
                    tempFile.writeBytes(pngData)
                    val upload = withContext(Dispatchers.IO) {
                        bridgeApi.uploadImage(tempFile.absolutePath, tempFile.name, toClipboard = false)
                    }
                    tempFile.delete()
                    if (upload.ok) imageUrl = upload.url ?: upload.path
                }
                showPromptComposerDialog(onComplete, imageUrl)
            } catch (e: Exception) {
                Toast.makeText(this@UiLocatorService, "截图失败，将使用文字生成: ${e.message}", Toast.LENGTH_SHORT).show()
                showPromptComposerDialog(onComplete, null)
            }
        }
    }

    private fun showPromptComposerDialog(onComplete: () -> Unit, imageUrl: String? = null) {
        hideFloatingBubble()
        val composeView = ComposeView(this)
        val lifecycleOwner = ServiceLifecycleOwner()
        composeView.setViewTreeLifecycleOwner(lifecycleOwner)
        composeView.setViewTreeSavedStateRegistryOwner(lifecycleOwner)
        val viewModelStore = ViewModelStore()
        composeView.setViewTreeViewModelStoreOwner(object : ViewModelStoreOwner {
            override val viewModelStore: ViewModelStore = viewModelStore
        })

        val layoutParams = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT,
        )
        interceptView = composeView

        composeView.setContent {
            var componentName by remember { mutableStateOf("") }
            var userText by remember { mutableStateOf("") }
            var taskType by remember { mutableStateOf("auto") }
            var loading by remember { mutableStateOf(false) }
            var generatedPrompt by remember { mutableStateOf("") }
            var resultLabel by remember { mutableStateOf("") }
            val typeOptions = listOf(
                "auto" to "自动判断",
                "bug_fix" to "问题修复",
                "feature_change" to "功能调整",
                "test_plan" to "测试与计划",
            )

            Box(
                modifier = Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.72f)).clickable { },
                contentAlignment = Alignment.Center,
            ) {
                Column(
                    modifier = Modifier
                        .padding(20.dp)
                        .fillMaxWidth()
                        .heightIn(max = 620.dp)
                        .background(Color.White, RoundedCornerShape(14.dp))
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text("✨ AI 提示词", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = Color.Black)
                    Text(
                        if (imageUrl != null) "已附当前屏幕截图，Aide 会结合画面识别组件。"
                        else "未取得截图，请填写组件名称。",
                        fontSize = 12.sp,
                        color = if (imageUrl != null) Color(0xFF00695C) else Color.DarkGray,
                    )
                    androidx.compose.material3.OutlinedTextField(
                        value = componentName,
                        onValueChange = { componentName = it },
                        label = { Text(if (imageUrl != null) "组件名称（可选）" else "组件名称") },
                        placeholder = { Text(if (imageUrl != null) "可留空，让 Aide 结合截图识别" else "例如：聊天页面的消息输入框") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                    )
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                        typeOptions.forEach { (key, label) ->
                            val selected = taskType == key
                            Text(
                                label,
                                fontSize = 11.sp,
                                color = if (selected) Color.White else Color(0xFF00695C),
                                modifier = Modifier
                                    .weight(1f)
                                    .clip(RoundedCornerShape(7.dp))
                                    .background(if (selected) Color(0xFF00796B) else Color(0xFFE0F2F1))
                                    .clickable { taskType = key }
                                    .padding(vertical = 8.dp),
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                            )
                        }
                    }
                    androidx.compose.material3.OutlinedTextField(
                        value = userText,
                        onValueChange = { userText = it },
                        label = { Text("问题或需求") },
                        placeholder = { Text("例如：一段时间后会变红") },
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 2,
                        maxLines = 4,
                    )
                    if (generatedPrompt.isNotBlank()) {
                        Text(resultLabel, fontSize = 12.sp, color = Color(0xFF00695C), fontWeight = FontWeight.SemiBold)
                        Text(
                            generatedPrompt,
                            fontSize = 13.sp,
                            color = Color.Black,
                            modifier = Modifier.fillMaxWidth().background(Color(0xFFF5F5F5), RoundedCornerShape(8.dp)).padding(10.dp),
                        )
                    }
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        androidx.compose.material3.OutlinedButton(
                            onClick = {
                                removeInterceptOverlay()
                                showFloatingBubble()
                                onComplete()
                            },
                            modifier = Modifier.weight(1f),
                        ) { Text("关闭") }
                        if (generatedPrompt.isBlank()) {
                            androidx.compose.material3.Button(
                                onClick = {
                                    if (!loading && userText.isNotBlank() && (componentName.isNotBlank() || imageUrl != null)) {
                                        loading = true
                                        serviceScope.launch {
                                            val result = withContext(Dispatchers.IO) {
                                                bridgeApi.composePrompt(
                                                    platform = "Android App",
                                                    componentName = componentName,
                                                    userText = userText,
                                                    taskType = taskType,
                                                    image = imageUrl,
                                                )
                                            }
                                            loading = false
                                            if (result.ok) {
                                                generatedPrompt = result.prompt
                                                resultLabel = buildString {
                                                    append("${result.task_type_label} · ${result.difficulty_label}")
                                                    if (result.component_name.isNotBlank()) append(" · ${result.component_name}")
                                                    append(if (result.image_used) " · 已识图" else if (result.used_ai) " · Aide 已优化" else " · 基础模板")
                                                }
                                            } else {
                                                Toast.makeText(this@UiLocatorService, result.message ?: "生成失败", Toast.LENGTH_SHORT).show()
                                            }
                                        }
                                    }
                                },
                                enabled = !loading && userText.isNotBlank() && (componentName.isNotBlank() || imageUrl != null),
                                modifier = Modifier.weight(1f),
                            ) { Text(if (loading) "生成中…" else "生成") }
                        } else {
                            androidx.compose.material3.Button(
                                onClick = {
                                    val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                    clipboard.setPrimaryClip(ClipData.newPlainText("AideLink prompt", generatedPrompt))
                                    Toast.makeText(this@UiLocatorService, "提示词已复制", Toast.LENGTH_SHORT).show()
                                },
                                modifier = Modifier.weight(1f),
                            ) { Text("复制提示词") }
                        }
                    }
                }
            }
        }
        windowManager.addView(composeView, layoutParams)
    }

    private fun showInterceptOverlay(onComplete: () -> Unit) {
        val composeView = ComposeView(this)
        val lifecycleOwner = ServiceLifecycleOwner()
        composeView.setViewTreeLifecycleOwner(lifecycleOwner)
        composeView.setViewTreeSavedStateRegistryOwner(lifecycleOwner)
        
        val viewModelStore = ViewModelStore()
        val viewModelStoreOwner = object : ViewModelStoreOwner {
            override val viewModelStore: ViewModelStore = viewModelStore
        }
        composeView.setViewTreeViewModelStoreOwner(viewModelStoreOwner)

        val layoutParams = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            },
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        )

        composeView.setContent {
            var locateResult by remember { mutableStateOf<String?>(null) }
            var resultNode by remember { mutableStateOf<cc.aidelink.app.domain.model.bridge.ProjectNode?>(null) }

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.15f))
                    .pointerInput(Unit) {
                        detectTapGestures { offset ->
                            if (locateResult == null) {
                                val x = offset.x.toInt()
                                val y = offset.y.toInt()
                                serviceScope.launch {
                                    Toast.makeText(this@UiLocatorService, "定位中...", Toast.LENGTH_SHORT).show()
                                    val locateResp = withContext(Dispatchers.IO) {
                                        val displayMetrics = resources.displayMetrics
                                        bridgeApi.locateUiElement(x, y, displayMetrics.widthPixels, displayMetrics.heightPixels)
                                    }
                                    if (locateResp.ok && locateResp.matched_code != null) {
                                        resultNode = locateResp.matched_code
                                        val element = locateResp.element
                                        locateResult = "组件: ${element?.`class`?.substringAfterLast('.') ?: ""}\nID: ${element?.resource_id?.substringAfterLast('/') ?: ""}\n文件: ${resultNode?.file?.substringAfterLast('/') ?: ""}"
                                    } else {
                                        Toast.makeText(this@UiLocatorService, locateResp.error ?: "未匹配到代码组件", Toast.LENGTH_SHORT).show()
                                        removeInterceptOverlay()
                                        onComplete()
                                    }
                                }
                            }
                        }
                    }
            ) {
                if (locateResult != null) {
                    Box(
                        modifier = Modifier
                            .align(Alignment.Center)
                            .padding(24.dp)
                            .background(Color.White, shape = RoundedCornerShape(12.dp))
                            .padding(16.dp)
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("📍 定位成功", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = Color.Black)
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(locateResult!!, fontSize = 14.sp, color = Color.DarkGray)
                            Spacer(modifier = Modifier.height(16.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                androidx.compose.material3.Button(onClick = {
                                    val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                                    val prefix = "【代码定位：${resultNode?.file?.substringAfterLast('/') ?: resultNode?.name ?: ""}】"
                                    val clip = android.content.ClipData.newPlainText("ui_locator_prefix", prefix)
                                    clipboard.setPrimaryClip(clip)
                                    Toast.makeText(this@UiLocatorService, "已复制路径到剪贴板", Toast.LENGTH_SHORT).show()
                                    removeInterceptOverlay()
                                    onComplete()
                                }) {
                                    Text("复制")
                                }
                                androidx.compose.material3.Button(onClick = {
                                    val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                                    val prefix = "【代码定位：${resultNode?.file?.substringAfterLast('/') ?: resultNode?.name ?: ""}】"
                                    val clip = android.content.ClipData.newPlainText("ui_locator_prefix", prefix)
                                    clipboard.setPrimaryClip(clip)
                                    Toast.makeText(this@UiLocatorService, "已复制到剪贴板，返回 App 后自动填充", Toast.LENGTH_SHORT).show()
                                    removeInterceptOverlay()
                                    onComplete()
                                }) {
                                    Text("注入")
                                }
                                androidx.compose.material3.OutlinedButton(onClick = {
                                    removeInterceptOverlay()
                                    onComplete()
                                }) {
                                    Text("取消")
                                }
                            }
                        }
                    }
                }
            }
        }

        interceptView = composeView
        windowManager.addView(composeView, layoutParams)
    }

    private fun removeInterceptOverlay() {
        interceptView?.let {
            try {
                windowManager.removeView(it)
            } catch (e: Exception) {}
            interceptView = null
        }
    }

    private fun hideFloatingBubble() {
        menuView?.let {
            try {
                windowManager.removeView(it)
            } catch (e: Exception) {}
            menuView = null
        }
        floatView?.let {
            try {
                windowManager.removeView(it)
            } catch (e: Exception) {}
            floatView = null
        }
    }

    override fun onDestroy() {
        serviceScope.cancel()
        super.onDestroy()
        hideFloatingBubble()
        removeInterceptOverlay()
        captureVirtualDisplay?.release()
        captureVirtualDisplay = null
        captureImageReader?.close()
        captureImageReader = null
        mediaProjection?.stop()
        mediaProjection = null
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private class ServiceLifecycleOwner : androidx.lifecycle.LifecycleOwner, androidx.savedstate.SavedStateRegistryOwner {
        private val lifecycleRegistry = androidx.lifecycle.LifecycleRegistry(this)
        private val savedStateRegistryController = androidx.savedstate.SavedStateRegistryController.create(this)

        init {
            savedStateRegistryController.performRestore(null)
            lifecycleRegistry.currentState = androidx.lifecycle.Lifecycle.State.CREATED
            lifecycleRegistry.currentState = androidx.lifecycle.Lifecycle.State.STARTED
            lifecycleRegistry.currentState = androidx.lifecycle.Lifecycle.State.RESUMED
        }

        override val lifecycle: Lifecycle
            get() = lifecycleRegistry

        override val savedStateRegistry: androidx.savedstate.SavedStateRegistry
            get() = savedStateRegistryController.savedStateRegistry
    }

    companion object {
        private const val TAG = "UiLocatorService"

        @Volatile
        var onMediaProjectionResult: ((Int?, Intent?) -> Unit)? = null
    }
}

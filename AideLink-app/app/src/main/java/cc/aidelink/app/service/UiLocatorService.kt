package cc.aidelink.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.util.DisplayMetrics
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Toast
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
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
        showFloatingBubble()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    private fun ensureMediaProjection(onReady: suspend () -> Unit) {
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
        // 通过 MainActivity 请求 MediaProjection 权限
        val intent = Intent(this, cc.aidelink.app.MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            putExtra("request_media_projection", true)
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
            val menuWidthPx = (170 * dm.density).toInt()
            val menuHeightPx = (230 * dm.density).toInt()
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
                        .width(170.dp)
                        .background(Color.White, shape = RoundedCornerShape(12.dp))
                        .shadow(8.dp, RoundedCornerShape(12.dp))
                        .padding(10.dp)
                ) {
                    Column(modifier = Modifier.fillMaxWidth()) {
                        Text("📸 截图发送", fontSize = 14.sp, color = Color(0xFF1976D2),
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
                                .background(Color(0xFFE3F2FD)).padding(horizontal = 12.dp, vertical = 10.dp)
                                .clickable { removeMenu(); takeScreenshotAndShowDialog {} })
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("🎯 定位组件", fontSize = 14.sp, color = Color(0xFF7B1FA2),
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
                                .background(Color(0xFFF3E5F5)).padding(horizontal = 12.dp, vertical = 10.dp)
                                .clickable { removeMenu(); captureAndLocate {} })
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("✨ 生成提示词", fontSize = 14.sp, color = Color(0xFF00695C),
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
                                .background(Color(0xFFE0F2F1)).padding(horizontal = 12.dp, vertical = 10.dp)
                                .clickable { removeMenu(); takeScreenshotForPrompt {} })
                        Spacer(modifier = Modifier.height(4.dp))
                        HorizontalDivider(modifier = Modifier.padding(vertical = 3.dp))
                        Text("🚫 退出悬浮窗", fontSize = 13.sp, color = Color(0xFFF44336),
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
                                .background(Color(0xFFFFEBEE)).padding(horizontal = 12.dp, vertical = 10.dp)
                                .clickable { removeMenu(); serviceScope.launch { settingsRepository.setGlobalLocatorEnabled(false) }; stopSelf() })
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
                val tempFile = File(cacheDir, "screenshot_${System.currentTimeMillis()}.png")
                tempFile.writeBytes(pngData)
                val uploadResp = withContext(Dispatchers.IO) {
                    bridgeApi.uploadImage(tempFile.absolutePath, tempFile.name, toClipboard = true)
                }
                tempFile.delete()
                val imageUrl = if (uploadResp.ok) uploadResp.url else null

                // 查询正在运行的 IDE 列表
                val runningIdes = withContext(Dispatchers.IO) {
                    try {
                        bridgeApi.getIdeProcesses().filter { it.running && it.key != "oc_web" }
                    } catch (_: Exception) {
                        emptyList()
                    }
                }

                if (runningIdes.size == 1) {
                    // 只有一个 IDE，直接粘贴图片，不弹选择
                    val ide = runningIdes[0].key
                    withContext(Dispatchers.IO) { bridgeApi.injectClipboard(ide) }
                    showScreenshotDialog(pngData, imageUrl, onComplete, defaultIde = ide, autoInjected = true)
                } else {
                    // 多个 IDE，弹选择框
                    showScreenshotDialog(pngData, imageUrl, onComplete)
                }
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
        defaultIde: String = "mimo",
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
            var selectedIde by remember { mutableStateOf(defaultIde) }
            var imageInjected by remember { mutableStateOf(autoInjected) }

            val ideList = listOf(
                "mimo" to "🤖 MiMo",
                "trae" to "⚡ Trae",
                "antigravity_ide" to "🚀 Antigravity IDE",
                "oc" to "📂 OC"
            )

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.7f))
                    .clickable { /* 阻止点击穿透 */ },
                contentAlignment = Alignment.Center
            ) {
                Column(
                    modifier = Modifier
                        .padding(24.dp)
                        .background(Color.White, shape = RoundedCornerShape(12.dp))
                        .padding(16.dp)
                ) {
                    Text(
                        text = "📸 发送截图",
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                        color = Color.Black
                    )
                    Spacer(modifier = Modifier.height(12.dp))

                    Text(
                        text = "发送到:",
                        fontSize = 13.sp,
                        color = Color.DarkGray
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        ideList.forEach { (key, label) ->
                            val isSelected = selectedIde == key
                            Text(
                                text = label,
                                fontSize = 12.sp,
                                color = if (isSelected) Color.White else Color(0xFF1976D2),
                                modifier = Modifier
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(if (isSelected) Color(0xFF1976D2) else Color(0xFFE3F2FD))
                                    .padding(horizontal = 8.dp, vertical = 6.dp)
                                    .clickable {
                                        selectedIde = key
                                        // 选 IDE 时立即把图片粘贴到 IDE（图片已在剪贴板）
                                        if (!imageInjected) {
                                            imageInjected = true
                                            serviceScope.launch {
                                                withContext(Dispatchers.IO) {
                                                    bridgeApi.injectClipboard(key)
                                                }
                                            }
                                        }
                                    }
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    Text(
                        text = "添加说明文字（可选）:",
                        fontSize = 13.sp,
                        color = Color.DarkGray
                    )
                    Spacer(modifier = Modifier.height(4.dp))

                    androidx.compose.material3.OutlinedTextField(
                        value = inputText,
                        onValueChange = { inputText = it },
                        placeholder = { Text("输入要一起发送的内容...") },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(80.dp),
                        textStyle = androidx.compose.ui.text.TextStyle(fontSize = 14.sp)
                    )

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
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("取消")
                        }
                        androidx.compose.material3.Button(
                            onClick = {
                                if (!isSending) {
                                    isSending = true
                                    serviceScope.launch {
                                        try {
                                            val message = if (inputText.isNotBlank()) {
                                                "【截图说明】\n${inputText}"
                                            } else {
                                                "【截图】"
                                            }
                                            // 文字注入到 IDE（图片已在选 IDE 时注入）
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
                            enabled = !isSending
                        ) {
                            Text(if (isSending) "发送中..." else "📤 发送")
                        }
                    }
                }
            }
        }

        windowManager.addView(composeView, layoutParams)
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

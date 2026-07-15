package cc.aidelink.app.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import androidx.core.app.NotificationCompat
import cc.aidelink.app.MainActivity
import cc.aidelink.app.R
import cc.aidelink.app.data.api.BridgeEventClient
import cc.aidelink.app.data.repository.SettingsRepository
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 任务通知处理器
 *
 * 消费 BridgeEventClient 的 SSE 事件，在 IDE 任务完成时：
 * 1. 发送系统通知（带声音和震动）
 * 2. 播放提示音
 * 3. 震动反馈
 *
 * 通知渠道：
 * - aidelink_tasks（高优先级，带声音）
 * - aidelink_tasks_silent（低优先级，静音）
 */
@Singleton
class TaskNotificationHandler @Inject constructor(
    @ApplicationContext private val context: Context,
    private val bridgeEventClient: BridgeEventClient,
    private val settings: SettingsRepository,
    private val bridgeApi: cc.aidelink.app.data.api.BridgeApi,
) {
    companion object {
        private const val TAG = "TaskNotification"
        private const val CHANNEL_TASKS = "aidelink_tasks_channel_v4"
        private const val CHANNEL_TASKS_SILENT = "aidelink_tasks_silent_channel_v4"
        private const val NOTIFICATION_ID_BASE = 2000
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var collectJob: Job? = null

    fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = context.getSystemService(NotificationManager::class.java)

        // 清理旧版本及缓存的通道
        nm.deleteNotificationChannel("aidelink_tasks_channel")
        nm.deleteNotificationChannel("aidelink_tasks_silent_channel")
        nm.deleteNotificationChannel("aidelink_tasks_channel_v1")
        nm.deleteNotificationChannel("aidelink_tasks_silent_channel_v1")
        nm.deleteNotificationChannel("aidelink_tasks_channel_v2")
        nm.deleteNotificationChannel("aidelink_tasks_silent_channel_v2")
        nm.deleteNotificationChannel("aidelink_tasks_channel_v3")
        nm.deleteNotificationChannel("aidelink_tasks_silent_channel_v3")

        // v4 渠道已存在则不重建（保留用户后续修改的设置）
        if (nm.getNotificationChannel(CHANNEL_TASKS) != null) return

        // 高优先级通知渠道（带声音和震动）
        val soundUri = Uri.parse("android.resource://${context.packageName}/${R.raw.final_done}")
        val attrs = AudioAttributes.Builder()
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .setUsage(AudioAttributes.USAGE_NOTIFICATION)
            .build()

        val channelTasks = NotificationChannel(
            CHANNEL_TASKS,
            context.getString(R.string.notification_channel_tasks),
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = context.getString(R.string.notification_channel_tasks_desc)
            enableLights(true)
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 300, 200, 300)
            setSound(soundUri, attrs)
            setShowBadge(true)
            lockscreenVisibility = NotificationCompat.VISIBILITY_PUBLIC
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                setBypassDnd(true)
            }
        }
        nm.createNotificationChannel(channelTasks)

        // 静音通知渠道
        val channelSilent = NotificationChannel(
            CHANNEL_TASKS_SILENT,
            context.getString(R.string.notification_channel_tasks_silent),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = context.getString(R.string.notification_channel_tasks_silent_desc)
            setSound(null, null)
            enableVibration(false)
            setShowBadge(true)
        }
        nm.createNotificationChannel(channelSilent)
    }

    /**
     * 开始监听桥接服务器事件
     */
    fun startListening() {
        if (collectJob?.isActive == true) return
        collectJob = scope.launch {
            bridgeEventClient.events.collect { event ->
                handleEvent(event)
            }
        }
    }

    fun stopListening() {
        collectJob?.cancel()
        collectJob = null
    }

    private suspend fun handleEvent(event: BridgeEventClient.BridgeEvent) {
        when (event.type) {
            "ide.notification" -> {
                val isTaskDoneObj = event.data["is_task_done"]
                val isTaskDone = when (isTaskDoneObj) {
                    is Boolean -> isTaskDoneObj
                    is String -> isTaskDoneObj.equals("true", ignoreCase = true)
                    else -> true
                }
                if (isTaskDone) {
                    val ide = event.data["ide"] as? String ?: ""
                    val title = event.data["title"] as? String ?: ""
                    val body = event.data["body"] as? String ?: ""
                    showTaskDoneNotification(ide, title, body, true)
                }
            }
            "task.feedback" -> {
                val ide = (event.data["ide"] ?: event.data["target_ide"]) as? String ?: ""
                val title = event.data["title"] as? String ?: ""
                val body = event.data["body"] as? String ?: ""
                val feedback = event.data["feedback"] as? String ?: ""
                showTaskFeedbackNotification(ide, title, body.ifBlank { feedback })
            }
            "app.update_available" -> {
                val versionName = event.data["version_name"] as? String ?: ""
                val versionCode = (event.data["version_code"] as? String)?.toIntOrNull() ?: 0
                if (versionCode > cc.aidelink.app.BuildConfig.VERSION_CODE) {
                    showUpdateNotification(versionName, versionCode)
                }
            }
            "app.command" -> {
                val command = event.data["command"] as? String ?: ""
                if (command == "enable_wireless_adb") {
                    val targetIp = event.data["target_ip"] as? String ?: ""
                    val requestId = event.data["request_id"] as? String ?: ""
                    handleEnableWirelessAdb(targetIp, requestId)
                }
            }
        }
    }

    private fun handleEnableWirelessAdb(targetIp: String, requestId: String) {
        scope.launch {
            try {
                Log.i(TAG, "收到服务器命令: 开启无线调试 (target=$targetIp)")
                val result = WirelessAdbManager.enableWirelessAdb(context)
                if (result.isSuccess) {
                    val cr = result.getOrNull()!!
                    Log.i(TAG, "无线调试已开启: ${cr.connectCmd} (method=${cr.method})")
                    bridgeApi.reportWirelessResult(
                        ip = cr.ip.ifBlank { targetIp },
                        port = cr.port,
                        ok = true,
                        error = null,
                        method = cr.method,
                        requestId = requestId,
                        targetIp = targetIp,
                    )
                } else {
                    val err = result.exceptionOrNull()?.message ?: "未知错误"
                    Log.e(TAG, "开启无线调试失败: $err")
                    bridgeApi.reportWirelessResult(
                        ip = targetIp,
                        port = 0,
                        ok = false,
                        error = err,
                        requestId = requestId,
                        targetIp = targetIp,
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "处理无线调试命令异常: ${e.message}")
            }
        }
    }

    private suspend fun showTaskDoneNotification(ide: String, title: String, body: String, isPendingTest: Boolean = false) {
        val notificationsEnabled = settings.notificationsEnabledRaw()
        if (!notificationsEnabled) return

        val silent = settings.silentNotificationsRaw()
        val haptic = settings.hapticFeedbackRaw()

        val channelId = if (silent) CHANNEL_TASKS_SILENT else CHANNEL_TASKS
        val ideLabel = ideLabel(ide)
        val notifTitle = if (isPendingTest) {
            if (title.isNotBlank()) "🟡 $title" else "$ideLabel 任务待测试"
        } else {
            if (title.isNotBlank()) title else "$ideLabel 任务完成"
        }
        val notifBody = if (isPendingTest) {
            "等待验证，点击确认完成"
        } else {
            if (body.isNotBlank()) body else "点击查看详情"
        }

        // 检查屏幕状态，决定是否使用 fullScreenIntent 唤醒屏幕
        val pm = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val isScreenOn = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT_WATCH) {
            pm.isInteractive
        } else {
            @Suppress("DEPRECATION")
            pm.isScreenOn
        }

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("from_notification", true)
            putExtra("notif_ide", ide)
            putExtra("notif_title", notifTitle)
            putExtra("notif_body", notifBody)
        }
        val pendingIntent = PendingIntent.getActivity(
            context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val builder = NotificationCompat.Builder(context, channelId)
            .setContentTitle(notifTitle)
            .setContentText(notifBody)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)

        // 锁屏时使用 fullScreenIntent 唤醒屏幕
        if (!isScreenOn) {
            val fullScreenPendingIntent = PendingIntent.getActivity(
                context, 1, Intent(intent),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            builder.setFullScreenIntent(fullScreenPendingIntent, true)
            Log.d(TAG, "Task notification with fullScreenIntent (screen is off)")
        }

        if (!silent) {
            builder.setDefaults(NotificationCompat.DEFAULT_ALL)
            builder.setSound(
                Uri.parse("android.resource://${context.packageName}/${R.raw.final_done}")
            )
        }

        val nm = context.getSystemService(NotificationManager::class.java)
        val notifId = NOTIFICATION_ID_BASE + (System.currentTimeMillis() % 1000).toInt()
        nm.notify(notifId, builder.build())

        // 额外播放震动（即使通知渠道可能被系统静音）
        if (haptic) {
            vibrate()
        }
        Log.d(TAG, "Task done notification shown: ide=$ide title=$title")
    }

    private suspend fun showTaskFeedbackNotification(ide: String, title: String, body: String) {
        val feedbackTitle = if (title.isNotBlank()) "任务反馈: $title" else "${ideLabel(ide)} 任务反馈"
        val feedbackBody = body.ifBlank { "点击查看任务会话" }
        showTaskDoneNotification(ide, feedbackTitle, feedbackBody, false)
    }

    private suspend fun showTaskFailedNotification(ide: String, error: String) {
        val notificationsEnabled = settings.notificationsEnabledRaw()
        if (!notificationsEnabled) return

        val silent = settings.silentNotificationsRaw()
        val channelId = if (silent) CHANNEL_TASKS_SILENT else CHANNEL_TASKS
        val ideLabel = ideLabel(ide)

        // 检查屏幕状态，决定是否使用 fullScreenIntent 唤醒屏幕
        val pm = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val isScreenOn = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT_WATCH) {
            pm.isInteractive
        } else {
            @Suppress("DEPRECATION")
            pm.isScreenOn
        }

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("from_notification", true)
            putExtra("notif_ide", ide)
            putExtra("notif_title", "$ideLabel 任务失败")
            putExtra("notif_body", error)
        }
        val pendingIntent = PendingIntent.getActivity(
            context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val builder = NotificationCompat.Builder(context, channelId)
            .setContentTitle("$ideLabel 任务失败")
            .setContentText(error)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(if (silent) NotificationCompat.PRIORITY_LOW else NotificationCompat.PRIORITY_HIGH)

        // 如果屏幕关闭，使用 fullScreenIntent 唤醒屏幕
        if (!isScreenOn) {
            val fullScreenIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or
                        Intent.FLAG_ACTIVITY_CLEAR_TOP or
                        Intent.FLAG_ACTIVITY_SINGLE_TOP
                putExtra("from_notification", true)
                putExtra("notif_ide", ide)
                putExtra("notif_title", "$ideLabel 任务失败")
                putExtra("notif_body", error)
            }
            val fullScreenPendingIntent = PendingIntent.getActivity(
                context, 1, fullScreenIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            builder.setFullScreenIntent(fullScreenPendingIntent, true)
        }

        val nm = context.getSystemService(NotificationManager::class.java)
        val notifId = NOTIFICATION_ID_BASE + 500 + (System.currentTimeMillis() % 1000).toInt()
        nm.notify(notifId, builder.build())

        if (!silent) {
            playNotificationSound()
        }
    }

    private fun playNotificationSound() {
        try {
            val uri = Uri.parse("android.resource://${context.packageName}/${R.raw.final_done}")
            val ringtone = RingtoneManager.getRingtone(context, uri)
            if (ringtone != null) {
                // 锁屏时通过 AudioManager 强制播放
                val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
                if (audioManager.ringerMode != android.media.AudioManager.RINGER_MODE_SILENT) {
                    ringtone.play()
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to play sound: ${e.message}")
        }
    }

    private fun vibrate() {
        try {
            val pattern = longArrayOf(0, 300, 200, 300)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
                vm.defaultVibrator.vibrate(
                    VibrationEffect.createWaveform(pattern, -1)
                )
            } else {
                @Suppress("DEPRECATION")
                val v = context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
                @Suppress("DEPRECATION")
                v.vibrate(pattern, -1)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to vibrate: ${e.message}")
        }
    }

    private fun ideLabel(ide: String): String = when (ide.lowercase()) {
        "trae" -> "Trae"
        "oc", "opencode" -> "OpenCode"
        "mimo", "mimocode" -> "MimoCode"
        "antigravity_ide" -> "Antigravity IDE"
        "cursor" -> "Cursor"
        "aide" -> "Aide"
        else -> ide
    }

    private fun showUpdateNotification(versionName: String, versionCode: Int) {
        val channelId = CHANNEL_TASKS
        val notifTitle = "🆕 新版本可用: v$versionName"
        val notifBody = "当前 v${cc.aidelink.app.BuildConfig.VERSION_NAME} → 点击下载更新"

        // 点击通知 → 打开设置页触发更新
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("from_notification", true)
            putExtra("trigger_update", true)
            putExtra("update_version_name", versionName)
            putExtra("update_version_code", versionCode)
        }
        val pendingIntent = PendingIntent.getActivity(
            context, 2, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val builder = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle(notifTitle)
            .setContentText(notifBody)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)

        val nm = context.getSystemService(NotificationManager::class.java)
        val notifId = NOTIFICATION_ID_BASE + 900
        nm.notify(notifId, builder.build())
        playNotificationSound()
    }
}

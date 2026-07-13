package cc.aidelink.app.ui.screens.chat.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.SwapVert
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import java.util.Locale

@Composable
fun ScreenMonitorPanel(
    active: Boolean,
    windowFound: Boolean = true,
    targetLabel: String = "IDE",
    sleeping: Boolean = false,
    image: androidx.compose.ui.graphics.ImageBitmap?,
    croppedImage: androidx.compose.ui.graphics.ImageBitmap?,
    originalWidth: Int,
    originalHeight: Int,
    calibWidth: Int,
    calibHeight: Int,
    intervalMs: Long,
    heightDp: Dp,
    cropLeft: Int,
    cropRight: Int,
    cropTop: Int,
    cropBottom: Int,
    onHeightChange: (Dp) -> Unit,
    onClose: () -> Unit = {},
    onDragStart: () -> Unit = {},
    onDragEnd: () -> Unit = {},
    onImageClick: () -> Unit = {},
    onImageDoubleClick: () -> Unit = {},
    onAutoDetectBlackEdge: (Int, Int, Dp) -> Unit = { _, _, _ -> },
    onWake: () -> Unit = {},
) {
    val context = LocalContext.current
    var scale by remember { mutableStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }

    LaunchedEffect(image) {
        scale = 1f
        offset = Offset.Zero
    }

    Card(
        shape = RoundedCornerShape(0.dp),
        modifier = Modifier
            .fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        BoxWithConstraints {
            val containerWidthDp = maxWidth
            val density = LocalDensity.current

            // 图片实际高度（按容器宽度等比缩放）—— 用全屏原图
            val fullImageHeightDp = if (image != null && image.width > 0) {
                val ratio = image.height.toFloat() / image.width.toFloat()
                val maxHeightPx = with(density) { containerWidthDp.toPx() } * ratio
                with(density) { maxHeightPx.toDp() }
            } else {
                700.dp
            }

            // 裁剪后图片的显示高度（双击恢复目标）—— 直接用裁剪后图片尺寸
            val calibratedHeightDp = if (croppedImage != null && croppedImage.width > 0) {
                val croppedRatio = croppedImage.height.toFloat() / croppedImage.width.toFloat()
                val croppedPx = with(density) { containerWidthDp.toPx() } * croppedRatio
                with(density) { croppedPx.toDp() }
            } else {
                fullImageHeightDp
            }

            // 限制高度范围：最小150dp，最大=裁剪后图片高度（或全图高度）
            var localHeightDp by remember { mutableStateOf(heightDp) }
            LaunchedEffect(heightDp) { localHeightDp = heightDp }
            val maxHeightForDrag = if (croppedImage != null && croppedImage.width > 0) calibratedHeightDp else fullImageHeightDp
            val clampedHeightDp = localHeightDp.coerceIn(150.dp, 1200.dp)

            Column {
                // 截图区域（上面）—— 高度=用户设定高度；从顶部裁剪，底部对齐，不变形
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(clampedHeightDp)
                        .background(Color.Black.copy(alpha = 0.05f))
                ) {
                    if (active && image != null) {
                        val imgW = image.width
                        val imgH = image.height

                        val density = LocalDensity.current
                        val containerWidthPx = with(density) { this@BoxWithConstraints.maxWidth.toPx() }
                        val containerHeightPx = with(density) { clampedHeightDp.toPx() }

                        val imageDisplayWDp = with(density) { containerWidthPx.toDp() }
                        val imageDisplayHDp = with(density) { containerHeightPx.toDp() }

                        Box(
                            modifier = Modifier
                                .size(imageDisplayWDp, imageDisplayHDp)
                                .pointerInput(Unit) {
                                    detectTransformGestures { _, pan, zoom, _ ->
                                        val newScale = (scale * zoom).coerceIn(1f, 5f)
                                        scale = newScale
                                        offset = if (newScale <= 1f) Offset.Zero else offset + pan
                                    }
                                }
                                .pointerInput(Unit) {
                                    detectTapGestures(
                                        onDoubleTap = {
                                            onImageDoubleClick()
                                        },
                                        onTap = {
                                            onImageClick()
                                        }
                                    )
                                }
                                .graphicsLayer(
                                    scaleX = scale,
                                    scaleY = scale,
                                    translationX = offset.x,
                                    translationY = offset.y,
                                    transformOrigin = TransformOrigin.Center
                                )
                        ) {
                            Canvas(modifier = Modifier.fillMaxSize()) {
                                if (imgW > 0 && imgH > 0 && originalWidth > 0 && originalHeight > 0) {
                                    val canvasW = size.width.toInt()
                                    val canvasH = size.height.toInt()

                                    val scaleFactorX = imgW.toFloat() / originalWidth
                                    val scaleFactorY = imgH.toFloat() / originalHeight
                                    val sLeft = (cropLeft * scaleFactorX).toInt().coerceIn(0, imgW - 1)
                                    val sRight = (cropRight * scaleFactorX).toInt().coerceIn(0, imgW - sLeft - 1)
                                    val sTop = (cropTop * scaleFactorY).toInt().coerceIn(0, imgH - 1)
                                    val sBottom = (cropBottom * scaleFactorY).toInt().coerceIn(0, imgH - sTop - 1)

                                    val croppedW = imgW - sLeft - sRight
                                    val croppedH = imgH - sTop - sBottom
                                    val croppedDisplayH = canvasW * croppedH.toFloat() / croppedW

                                    val visibleH: Int
                                    val srcOffsetY: Int

                                    if (croppedDisplayH > canvasH) {
                                        visibleH = (croppedH * canvasH / croppedDisplayH).toInt().coerceIn(1, croppedH)
                                        srcOffsetY = sTop + croppedH - visibleH
                                    } else {
                                        val fullDisplayH = canvasW * imgH.toFloat() / imgW
                                        visibleH = (imgH * canvasH / fullDisplayH).toInt().coerceIn(1, imgH)
                                        srcOffsetY = (imgH - sBottom - visibleH).coerceAtLeast(0)
                                    }

                                    drawImage(
                                        image = image,
                                        srcOffset = IntOffset(sLeft, srcOffsetY),
                                        srcSize = IntSize(croppedW, (imgH - srcOffsetY).coerceAtMost(visibleH)),
                                        dstOffset = IntOffset.Zero,
                                        dstSize = IntSize(canvasW, canvasH)
                                    )
                                }
                            }
                        }

                        Row(
                            modifier = Modifier
                                .align(Alignment.BottomEnd)
                                .padding(8.dp)
                                .background(Color.Black.copy(alpha = 0.5f), RoundedCornerShape(4.dp)),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(8.dp)
                                    .background(Color.Green, CircleShape)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = formatMonitorInterval(intervalMs),
                                color = Color.White,
                                style = MaterialTheme.typography.labelSmall
                            )
                        }
                    } else {
                        Box(
                            modifier = Modifier
                                .fillMaxSize()
                                .pointerInput(Unit) {
                                    detectTapGestures(
                                        onDoubleTap = { onImageDoubleClick() },
                                        onTap = { onImageClick() }
                                    )
                                },
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                if (active) "正在截取 PC 屏幕..." else "监控已暂停",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }

                    if (sleeping) {
                        Box(
                            modifier = Modifier
                                .fillMaxSize()
                                .background(Color.Black.copy(alpha = 0.6f))
                                .clickable { onWake() },
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(
                                    "屏幕无变化，已暂停截图",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = Color.White.copy(alpha = 0.8f)
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                Text(
                                    "点击唤醒",
                                    style = MaterialTheme.typography.titleMedium,
                                    color = Color.White
                                )
                            }
                        }
                    }

                    if (active && !windowFound) {
                        Surface(
                            modifier = Modifier
                                .align(Alignment.TopCenter)
                                .padding(8.dp),
                            color = Color(0xFFE65100).copy(alpha = 0.92f),
                            shape = RoundedCornerShape(6.dp),
                        ) {
                            Text(
                                text = "未匹配到 $targetLabel 窗口，当前可能显示整屏。请在电脑 Web 管理 → IDE 管理 → 绑定窗口中重新校准。",
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 7.dp),
                                color = Color.White,
                                style = MaterialTheme.typography.labelMedium,
                            )
                        }
                    }
                }

                // 调整边框区域（下面）
                if (active && image != null) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(24.dp)
                            .background(Color.Gray.copy(alpha = 0.1f))
                            .pointerInput(Unit) {
                                detectVerticalDragGestures(
                                    onDragStart = { onDragStart() },
                                    onDragEnd = {
                                        onDragEnd()
                                        onHeightChange(localHeightDp)
                                    },
                                    onDragCancel = { localHeightDp = heightDp },
                                    onVerticalDrag = { change, dragAmount ->
                                        change.consume()
                                        val deltaDp = with(density) { dragAmount.toDp() }
                                        localHeightDp = (localHeightDp + deltaDp).coerceIn(0.dp, maxOf(0.dp, maxHeightForDrag))
                                        if (localHeightDp <= 0.dp) {
                                            onClose()
                                        }
                                    }
                                )
                            }
                            .pointerInput(Unit) {
                                detectTapGestures(
                                    onDoubleTap = {
                                        localHeightDp = calibratedHeightDp
                                        onHeightChange(calibratedHeightDp)
                                        scale = 1f
                                        offset = Offset.Zero
                                    }
                                )
                            },
                        contentAlignment = Alignment.Center
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.SwapVert,
                                contentDescription = "拖动调整高度 / 双指缩放拖动截图",
                                modifier = Modifier.size(16.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                            )
                            Box(
                                modifier = Modifier
                                    .width(48.dp)
                                    .height(3.dp)
                                    .background(
                                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                                        shape = RoundedCornerShape(2.dp)
                                    )
                            )
                            Text(
                                text = "${heightDp.value.toInt()}dp",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                            )
                        }
                    }
                }
            }
        }
    }
}

internal fun formatMonitorInterval(intervalMs: Long): String {
    return when {
        intervalMs >= 60_000L -> {
            val minutes = intervalMs / 60_000L
            val seconds = (intervalMs % 60_000L) / 1_000L
            if (seconds == 0L) "${minutes}分"
            else "${minutes}分${seconds}秒"
        }
        intervalMs % 1_000L == 0L -> "${intervalMs / 1_000L}秒"
        else -> String.format(Locale.US, "%.1f秒", intervalMs / 1_000f)
    }
}

internal fun monitorAdjustStep(intervalMs: Long): Long {
    return when {
        intervalMs < 10_000L -> 500L
        intervalMs < 60_000L -> 5_000L
        else -> 30_000L
    }
}

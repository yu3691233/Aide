package cc.aidelink.app.ui.screens.chat.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import cc.aidelink.app.domain.model.bridge.MonitorInfo
import cc.aidelink.app.domain.model.bridge.InputPoint
import cc.aidelink.app.ui.screens.chat.AideLinkChatViewModel
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Switch
import androidx.compose.material3.RangeSlider
import androidx.compose.material3.SliderDefaults
import androidx.compose.ui.text.font.FontWeight

@Composable
fun ZoomableLiveMonitorDialog(
    ideName: String = "IDE",
    image: ImageBitmap,
    isEditing: Boolean,
    cropSource: AideLinkChatViewModel.DialogCropSource?,
    onSelectCropSource: (AideLinkChatViewModel.DialogCropSource?) -> Unit,
    intervalMs: Long,
    cropLeft: Int,
    cropRight: Int,
    cropTop: Int,
    cropBottom: Int,
    originalWidth: Int,
    originalHeight: Int,
    dialogPosition: String = "center",
    focusInputEnabled: Boolean = false,
    inputPoint: InputPoint? = null,
    onInputPointChange: (Float, Float) -> Unit = { _, _ -> },
    onFocusInputEnabledChange: (Boolean) -> Unit = {},
    onBindWindow: () -> Unit = {},
    onDialogPositionChange: (String) -> Unit = {},
    onAdjustInterval: (Long) -> Unit,
    onSetInterval: (Long) -> Unit,
    onCropChange: (String, Int) -> Unit,
    onCropSave: () -> Unit,
    onCropCapture: (left: Int, right: Int, top: Int, bottom: Int) -> Unit,
    onDismiss: () -> Unit,
    monitors: List<MonitorInfo> = emptyList(),
    selectedMonitor: String? = null,
    windowFound: Boolean = true,
    onSwitchMonitor: (String) -> Unit = {}
) {
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    var inputCalibration by remember { mutableStateOf(false) }
    val scaleFactorX = if (originalWidth > 0) image.width.toFloat() / originalWidth.toFloat() else 1f
    val scaleFactorY = if (originalHeight > 0) image.height.toFloat() / originalHeight.toFloat() else 1f

    val imgW = image.width.toFloat()
    val imgH = image.height.toFloat()
    val scaledCropLeft = (cropLeft * scaleFactorX).coerceIn(0f, imgW - 1f)
    val scaledCropRight = (cropRight * scaleFactorX).coerceIn(0f, imgW - scaledCropLeft - 1f)
    val scaledCropTop = (cropTop * scaleFactorY).coerceIn(0f, imgH - 1f)
    val scaledCropBottom = (cropBottom * scaleFactorY).coerceIn(0f, imgH - scaledCropTop - 1f)

    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(modifier = Modifier.fillMaxSize(), color = Color.Black) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .navigationBarsPadding()
            ) {
                // Top Controls: 关闭按钮 + 时间调整
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(38.dp)
                        .padding(horizontal = 12.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    IconButton(
                        onClick = onDismiss,
                        modifier = Modifier
                            .size(34.dp)
                            .background(Color.Black.copy(alpha = 0.5f), CircleShape)
                    ) {
                        Icon(Icons.Default.Close, contentDescription = "关闭", tint = Color.White, modifier = Modifier.size(18.dp))
                    }
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.background(Color.Black.copy(alpha = 0.6f), RoundedCornerShape(20.dp))
                    ) {
                        Text(ideName, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 10.dp))
                        IconButton(
                            onClick = { onAdjustInterval(-monitorAdjustStep(intervalMs)) },
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(Icons.Default.Remove, contentDescription = "减小间隔", tint = Color.White, modifier = Modifier.size(18.dp))
                        }
                        Text(
                            text = formatMonitorInterval(intervalMs),
                            color = Color.White,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 4.dp)
                        )
                        IconButton(
                            onClick = { onAdjustInterval(monitorAdjustStep(intervalMs)) },
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(Icons.Default.Add, contentDescription = "增大间隔", tint = Color.White, modifier = Modifier.size(18.dp))
                        }
                    }
                }


                // Middle: Zoomable Canvas Box (occupying remaining space)
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                        .pointerInput(Unit) {
                            detectTransformGestures { _, pan, zoom, _ ->
                                val newScale = (scale * zoom).coerceIn(1f, 5f)
                                scale = newScale
                                offset = if (newScale <= 1f) Offset.Zero else offset + pan
                            }
                        }
                        .graphicsLayer(
                            scaleX = scale,
                            scaleY = scale,
                            translationX = offset.x,
                            translationY = offset.y,
                            transformOrigin = TransformOrigin.Center
                        ),
                    contentAlignment = Alignment.Center
                ) {
                    Canvas(modifier = Modifier.fillMaxSize()) {
                        val imgWidth = image.width
                        val imgHeight = image.height
                        val drawLeft = scaledCropLeft.toInt().coerceIn(0, imgWidth - 1)
                        val drawRight = scaledCropRight.toInt().coerceIn(0, imgWidth - drawLeft - 1)
                        val drawTop = scaledCropTop.toInt().coerceIn(0, imgHeight - 1)
                        val drawBottom = scaledCropBottom.toInt().coerceIn(0, imgHeight - drawTop - 1)
                        val drawSrcWidth = imgWidth - drawLeft - drawRight
                        val drawSrcHeight = imgHeight - drawTop - drawBottom
                        if (drawSrcWidth > 0 && drawSrcHeight > 0) {
                            val canvasW = size.width
                            val canvasH = size.height
                            val imgRatio = drawSrcWidth.toFloat() / drawSrcHeight.toFloat()
                            val canvasRatio = canvasW / canvasH

                            val dstW: Float
                            val dstH: Float
                            if (imgRatio > canvasRatio) {
                                dstW = canvasW
                                dstH = canvasW / imgRatio
                            } else {
                                dstH = canvasH
                                dstW = canvasH * imgRatio
                            }
                            val dstX = (canvasW - dstW) / 2
                            val dstY = 0f

                            drawImage(
                                image = image,
                                srcOffset = IntOffset(drawLeft, drawTop),
                                srcSize = IntSize(drawSrcWidth, drawSrcHeight),
                                dstOffset = IntOffset(dstX.toInt(), dstY.toInt()),
                                dstSize = IntSize(dstW.toInt(), dstH.toInt())
                            )
                        }
                    }
                    if (inputCalibration) {
                        Box(
                            modifier = Modifier
                                .fillMaxSize()
                                .pointerInput(Unit) {
                                    detectTapGestures { point ->
                                        onInputPointChange(
                                            (point.x / size.width).coerceIn(0f, 0.99f),
                                            (point.y / size.height).coerceIn(0f, 0.99f)
                                        )
                                        inputCalibration = false
                                    }
                                }
                        )
                    }
                    if (focusInputEnabled && inputPoint != null) {
                        Canvas(modifier = Modifier.fillMaxSize()) {
                            drawCircle(
                                color = Color(0xFF3FB950),
                                radius = 8f,
                                center = Offset(inputPoint.x * size.width, inputPoint.y * size.height)
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                // Compact Monitors Switcher below screenshot
                if (monitors.size > 1 || (!windowFound && monitors.isNotEmpty())) {
                    Surface(
                        color = Color.Black.copy(alpha = 0.5f),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(start = 16.dp, end = 16.dp, bottom = 8.dp)
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp)
                        ) {
                            Text(
                                text = if (windowFound) "切换屏幕:" else "⚠️ 切换屏幕:",
                                color = if (windowFound) Color.White else Color.Yellow,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                modifier = Modifier.horizontalScroll(rememberScrollState()),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                monitors.forEach { mon ->
                                    val isSelected = selectedMonitor == mon.name || (selectedMonitor == null && mon.primary)
                                    FilterChip(
                                        selected = isSelected,
                                        onClick = { onSwitchMonitor(mon.name) },
                                        label = {
                                            Text(
                                                text = if (mon.primary) "主显示器" else "显示器 (${mon.width}x${mon.height})",
                                                fontSize = 10.sp
                                            )
                                        },
                                        colors = FilterChipDefaults.filterChipColors(
                                            selectedContainerColor = Color.Yellow,
                                            selectedLabelColor = Color.Black,
                                            containerColor = Color.White.copy(alpha = 0.15f),
                                            labelColor = Color.White
                                        ),
                                        modifier = Modifier.height(28.dp)
                                    )
                                }
                            }
                            Spacer(modifier = Modifier.weight(1f))
                            Text("位置", color = Color.White, fontSize = 10.sp)
                            mapOf("left" to "左", "center" to "中", "right" to "右").forEach { (pos, label) ->
                                FilterChip(
                                    selected = dialogPosition == pos,
                                    onClick = { onDialogPositionChange(pos) },
                                    label = { Text(label, fontSize = 10.sp) },
                                    colors = FilterChipDefaults.filterChipColors(
                                        selectedContainerColor = Color(0xFF58A6FF),
                                        selectedLabelColor = Color.White,
                                        containerColor = Color.White.copy(alpha = 0.15f),
                                        labelColor = Color.White
                                    ),
                                    modifier = Modifier.height(26.dp)
                                )
                            }
                        }

                    }
                }

                if (!windowFound) Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text("绑定窗口", color = Color.White, fontSize = 11.sp)
                    Button(onClick = onBindWindow, modifier = Modifier.height(32.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF58A6FF))) {
                        Text("绑定", fontSize = 11.sp)
                    }
                }

                // Bottom Panel: 底部控制面板（边距调整）
                Surface(
                    color = Color.Black.copy(alpha = 0.7f),
                    shape = RoundedCornerShape(20.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(start = 16.dp, end = 16.dp, bottom = 16.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                text = if (focusInputEnabled && inputPoint != null) "输入框点击：已设置" else "输入框点击：未设置",
                                color = if (focusInputEnabled && inputPoint != null) Color(0xFF3FB950) else Color.White,
                                fontSize = 11.sp
                            )
                            Button(
                                onClick = { inputCalibration = true },
                                modifier = Modifier.height(34.dp),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = Color(0xFF3FB950),
                                    contentColor = Color.Black
                                )
                            ) {
                                Text(if (inputCalibration) "请点击截图中的输入框" else "校准输入框", fontSize = 11.sp)
                            }
                            Text("派发前点击", color = Color.White, fontSize = 10.sp)
                            Switch(checked = focusInputEnabled, onCheckedChange = onFocusInputEnabledChange)
                        }

                        // 左右边距 RangeSlider
                        Column(modifier = Modifier.fillMaxWidth()) {
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("左右边距", color = Color.White, fontSize = 11.sp)
                                Text("左:$cropLeft  右:$cropRight", color = Color.White.copy(alpha = 0.7f), fontSize = 10.sp)
                            }
                            @OptIn(ExperimentalMaterial3Api::class)
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .pointerInput(Unit) {
                                        detectTapGestures(
                                            onDoubleTap = {
                                                onCropChange("left", 0)
                                                onCropChange("right", 0)
                                            }
                                        )
                                    }
                            ) {
                                val minSpan = minOf(10f, imgW).coerceAtLeast(1f)
                                val safeSliderStart = scaledCropLeft.coerceIn(0f, (imgW - minSpan).coerceAtLeast(0f))
                                val safeSliderEnd = (imgW - scaledCropRight).coerceIn(safeSliderStart + minSpan, imgW)
                                RangeSlider(
                                    value = safeSliderStart..safeSliderEnd,
                                    onValueChange = { range ->
                                        val newLeft = (range.start / scaleFactorX).toInt().coerceAtLeast(0)
                                        val newRight = ((imgW - range.endInclusive) / scaleFactorX).toInt().coerceAtLeast(0)
                                        onCropChange("left", newLeft)
                                        onCropChange("right", newRight)
                                    },
                                    valueRange = 0f..image.width.toFloat(),
                                    modifier = Modifier.fillMaxWidth(),
                                    colors = SliderDefaults.colors(thumbColor = Color.Yellow, activeTrackColor = Color.Yellow)
                                )
                            }
                        }

                        // 上下边距 RangeSlider
                        val initCropTop = remember { cropTop }
                        val initCropBottom = remember { cropBottom }
                        Column(modifier = Modifier.fillMaxWidth()) {
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                Text("上下边距", color = Color.White, fontSize = 11.sp)
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text("上:$cropTop  下:$cropBottom", color = Color.White.copy(alpha = 0.7f), fontSize = 10.sp)
                                    Text(
                                        "重置",
                                        color = Color(0xFF58A6FF),
                                        fontSize = 10.sp,
                                        modifier = Modifier
                                            .clickable {
                                                onCropChange("top", initCropTop)
                                                onCropChange("bottom", initCropBottom)
                                            }
                                            .background(Color.White.copy(alpha = 0.1f), RoundedCornerShape(4.dp))
                                            .padding(horizontal = 6.dp, vertical = 2.dp)
                                    )
                                }
                            }
                            val minVerticalSpan = minOf(10f, imgH).coerceAtLeast(1f)
                            val safeVerticalStart = scaledCropTop.coerceIn(0f, (imgH - minVerticalSpan).coerceAtLeast(0f))
                            val safeVerticalEnd = (imgH - scaledCropBottom).coerceIn(safeVerticalStart + minVerticalSpan, imgH)
                            @OptIn(ExperimentalMaterial3Api::class)
                            RangeSlider(
                                value = safeVerticalStart..safeVerticalEnd,
                                onValueChange = { range ->
                                    val newTop = (range.start / scaleFactorY).toInt().coerceAtLeast(0)
                                    val newBottom = ((imgH - range.endInclusive) / scaleFactorY).toInt().coerceAtLeast(0)
                                    onCropChange("top", newTop)
                                    onCropChange("bottom", newBottom)
                                },
                                valueRange = 0f..image.height.toFloat(),
                                modifier = Modifier.fillMaxWidth(),
                                colors = SliderDefaults.colors(thumbColor = Color.Yellow, activeTrackColor = Color.Yellow)
                            )
                        }

                        // 应用裁剪按钮
                        Button(
                            onClick = {
                                onCropSave()
                            },
                            modifier = Modifier.fillMaxWidth().height(40.dp),
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Color.Yellow,
                                contentColor = Color.Black
                            )
                        ) {
                            Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("应用裁剪", fontSize = 14.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}

package cc.aidelink.app.ui.screens.chat.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cc.aidelink.app.domain.model.bridge.ProjectNode
import cc.aidelink.app.domain.model.bridge.PromptCandidate
import cc.aidelink.app.ui.screens.chat.PromptAction
import androidx.compose.foundation.lazy.LazyColumn

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProjectMapPanel(
    categories: List<ProjectNode>,
    loading: Boolean,
    selectedNode: ProjectNode?,
    promptAction: PromptAction?,
    promptDescription: String,
    promptVersion: String,
    generatedPrompt: String,
    promptCandidates: List<PromptCandidate>,
    promptPredictLoading: Boolean,
    onRescan: () -> Unit,
    onSelectNode: (ProjectNode) -> Unit,
    onClearSelection: () -> Unit,
    onSetAction: (PromptAction) -> Unit,
    onSetDescription: (String) -> Unit,
    onPredictPrompts: (String) -> Unit,
    onSetVersion: (String) -> Unit,
    onLockFeature: () -> Unit,
    onGenerate: () -> Unit,
    onUsePrompt: () -> Unit,
) {
    val clipboardManager = LocalClipboardManager.current
    var mapFilter by remember { mutableStateOf("all") }

    // 按 filter 分组
    val sourceCodeKeywords = listOf("API", "数据仓库", "后台服务", "依赖注入", "导航", "服务端", "桥接", "任务运行时", "模型", "调度器", "扫描器", "事件总线", "上下文", "通知", "进化", "注入", "托盘", "吉祥物", "调用", "协作")
    val filteredCategories = remember(categories, mapFilter) {
        if (mapFilter == "all") return@remember categories
        categories.map { cat ->
            if (cat.id == "android_app") {
                val children = cat.children.filter { child ->
                    val name = child.name
                    val isSource = sourceCodeKeywords.any { name.contains(it) }
                    if (mapFilter == "ui") !isSource else isSource
                }
                cat.copy(children = children)
            } else if (cat.id == "server") {
                if (mapFilter == "code") cat else null
            } else if (cat.id == "web_manager_ui") {
                if (mapFilter == "ui") cat else null
            } else {
                cat
            }
        }.filterNotNull()
    }

    ElevatedCard(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        colors = CardDefaults.elevatedCardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow,
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Title row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Default.FolderOpen,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                        tint = MaterialTheme.colorScheme.primary,
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        "项目地图",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (loading) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                        Spacer(modifier = Modifier.width(8.dp))
                    }
                    IconButton(onClick = onRescan, modifier = Modifier.size(30.dp), enabled = !loading) {
                        Icon(Icons.Default.Refresh, contentDescription = "重新扫描", modifier = Modifier.size(16.dp))
                    }
                }
            }

            // Filter chips
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                FilterChip(
                    selected = mapFilter == "ui",
                    onClick = { mapFilter = "ui" },
                    label = { Text("🎨 界面", style = MaterialTheme.typography.labelSmall) },
                    leadingIcon = if (mapFilter == "ui") {{ Icon(Icons.Default.Check, null, modifier = Modifier.size(14.dp)) }} else null,
                )
                FilterChip(
                    selected = mapFilter == "code",
                    onClick = { mapFilter = "code" },
                    label = { Text("📂 源码", style = MaterialTheme.typography.labelSmall) },
                    leadingIcon = if (mapFilter == "code") {{ Icon(Icons.Default.Check, null, modifier = Modifier.size(14.dp)) }} else null,
                )
                FilterChip(
                    selected = mapFilter == "all",
                    onClick = { mapFilter = "all" },
                    label = { Text("全部", style = MaterialTheme.typography.labelSmall) },
                    leadingIcon = if (mapFilter == "all") {{ Icon(Icons.Default.Check, null, modifier = Modifier.size(14.dp)) }} else null,
                )
            }

            Spacer(modifier = Modifier.height(6.dp))

            if (filteredCategories.isEmpty() && !loading) {
                Text(
                    "暂无数据，点击刷新按钮扫描",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            if (filteredCategories.isNotEmpty()) {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 100.dp, max = 400.dp),
                    verticalArrangement = Arrangement.spacedBy(1.dp),
                ) {
                    filteredCategories.forEach { category ->
                        item(key = "cat_${category.id}") {
                            TreeCategoryItem(
                                category = category,
                                selectedNode = selectedNode,
                                onSelectNode = onSelectNode,
                            )
                        }
                    }
                }
            }

            if (selectedNode != null) {
                HorizontalDivider(
                    modifier = Modifier.padding(vertical = 6.dp),
                    color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.4f),
                )
                PromptBuilderSection(
                    node = selectedNode,
                    action = promptAction,
                    description = promptDescription,
                    version = promptVersion,
                    generatedPrompt = generatedPrompt,
                    promptCandidates = promptCandidates,
                    promptPredictLoading = promptPredictLoading,
                    onClear = onClearSelection,
                    onSetAction = onSetAction,
                    onSetDescription = onSetDescription,
                    onPredictPrompts = onPredictPrompts,
                    onSetVersion = onSetVersion,
                    onGenerate = onGenerate,
                    onUsePrompt = onUsePrompt,
                    onLockFeature = onLockFeature,
                    onCopyPrompt = {
                        clipboardManager.setText(AnnotatedString(generatedPrompt))
                    },
                )
            }
        }
    }
}

@Composable
fun TreeCategoryItem(
    category: ProjectNode,
    selectedNode: ProjectNode?,
    onSelectNode: (ProjectNode) -> Unit,
    depth: Int = 0,
) {
    var expanded by remember { mutableStateOf(false) }
    val hasChildren = category.children.isNotEmpty()
    val isSelected = selectedNode?.id == category.id

    val rootBackground = if (isSelected) {
        MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.85f)
    } else if (depth == 0) {
        MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f)
    } else {
        Color.Transparent
    }

    val textColor = if (isSelected) {
        MaterialTheme.colorScheme.onPrimaryContainer
    } else if (depth == 0) {
        MaterialTheme.colorScheme.primary
    } else {
        MaterialTheme.colorScheme.onSurface
    }

    val fontWeight = if (isSelected || depth == 0) {
        FontWeight.Bold
    } else if (depth == 1) {
        FontWeight.Medium
    } else {
        FontWeight.Normal
    }

    val fontSize = if (depth == 0) {
        13.5.sp
    } else if (depth == 1) {
        12.5.sp
    } else {
        12.sp
    }

    val verticalPadding = if (depth == 0) 6.dp else 5.dp

    Column {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 1.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(rootBackground)
                .clickable {
                    onSelectNode(category)
                }
                .padding(start = (depth * 10).dp, top = verticalPadding, bottom = verticalPadding, end = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (hasChildren) {
                Box(
                    modifier = Modifier
                        .size(24.dp)
                        .clip(CircleShape)
                        .clickable {
                            expanded = !expanded
                        },
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = if (expanded) "收起" else "展开",
                        modifier = Modifier.size(16.dp),
                        tint = if (isSelected) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                Spacer(modifier = Modifier.width(24.dp))
            }

            Spacer(modifier = Modifier.width(4.dp))

            Text(
                text = category.name,
                style = MaterialTheme.typography.bodySmall.copy(
                    fontSize = fontSize,
                    fontWeight = fontWeight,
                    color = textColor
                ),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
        }

        AnimatedVisibility(visible = expanded) {
            Column {
                category.children.forEach { child ->
                    TreeCategoryItem(
                        category = child,
                        selectedNode = selectedNode,
                        onSelectNode = onSelectNode,
                        depth = depth + 1,
                    )
                }
            }
        }
    }
}

@Composable
fun PromptBuilderSection(
    node: ProjectNode,
    action: PromptAction?,
    description: String,
    version: String,
    generatedPrompt: String,
    promptCandidates: List<PromptCandidate>,
    promptPredictLoading: Boolean,
    onClear: () -> Unit,
    onSetAction: (PromptAction) -> Unit,
    onSetDescription: (String) -> Unit,
    onPredictPrompts: (String) -> Unit,
    onSetVersion: (String) -> Unit,
    onGenerate: () -> Unit,
    onUsePrompt: () -> Unit,
    onLockFeature: () -> Unit,
    onCopyPrompt: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    "📍 ${node.name}",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                if (node.locationLabel.isNotEmpty()) {
                    Text(
                        node.locationLabel,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        fontFamily = FontFamily.Monospace,
                    )
                }
                if (!node.description.isNullOrEmpty()) {
                    Text(
                        node.description,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            IconButton(onClick = onClear, modifier = Modifier.size(28.dp)) {
                Icon(
                    Icons.Default.Close,
                    contentDescription = "取消选择",
                    modifier = Modifier.size(16.dp),
                )
            }
        }

        Text(
            "操作类型",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.horizontalScroll(rememberScrollState()),
        ) {
            PromptAction.entries.forEach { a ->
                FilterChip(
                    selected = action == a,
                    onClick = { onSetAction(a) },
                    label = {
                        Text("${a.emoji} ${a.label}", style = MaterialTheme.typography.labelMedium)
                    },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = MaterialTheme.colorScheme.primaryContainer,
                        selectedLabelColor = MaterialTheme.colorScheme.onPrimaryContainer,
                    ),
                )
            }
        }

        if (action == PromptAction.FEATURE_LOCK) {
            OutlinedTextField(
                value = version,
                onValueChange = onSetVersion,
                modifier = Modifier.fillMaxWidth(),
                textStyle = MaterialTheme.typography.bodySmall,
                label = { Text("版本号", style = MaterialTheme.typography.labelSmall) },
                placeholder = { Text("例如 v1.2", style = MaterialTheme.typography.bodySmall) },
                maxLines = 1,
                shape = RoundedCornerShape(12.dp),
            )
        }

        OutlinedTextField(
            value = description,
            onValueChange = onSetDescription,
            modifier = Modifier.fillMaxWidth(),
            textStyle = MaterialTheme.typography.bodySmall,
            placeholder = {
                Text(
                    if (action == PromptAction.FEATURE_LOCK) "详细功能作用说明（必填，将写入版本文档）..."
                    else "补充描述（可选）…",
                    style = MaterialTheme.typography.bodySmall,
                )
            },
            maxLines = 2,
            shape = RoundedCornerShape(12.dp),
        )

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Button(
                onClick = { onPredictPrompts(description) },
                modifier = Modifier.weight(1f),
                enabled = action != null && !promptPredictLoading,
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary)
            ) {
                if (promptPredictLoading) {
                    CircularProgressIndicator(modifier = Modifier.size(16.dp), color = MaterialTheme.colorScheme.onSecondary, strokeWidth = 2.dp)
                    Spacer(Modifier.width(6.dp))
                    Text("正在分析...", fontSize = 11.sp)
                } else {
                    Icon(Icons.Default.AutoAwesome, contentDescription = null, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("AI 预测", fontSize = 11.sp)
                }
            }

            Button(
                onClick = onGenerate,
                modifier = Modifier.weight(1f),
                enabled = action != null && (action != PromptAction.FEATURE_LOCK || (version.isNotBlank() && description.isNotBlank()))
            ) {
                Text("生成", fontSize = 11.sp)
            }

            if (action == PromptAction.FEATURE_LOCK) {
                Button(
                    onClick = onLockFeature,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.tertiary),
                    enabled = version.isNotBlank() && description.isNotBlank()
                ) {
                    Text("🔒 锁定并归档", fontSize = 11.sp)
                }
            }
        }

        if (promptCandidates.isNotEmpty()) {
            Text("推荐候选 (点击可填入)", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                promptCandidates.forEachIndexed { idx, c ->
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onSetDescription(c.prompt) },
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f)),
                        shape = RoundedCornerShape(8.dp),
                        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f))
                    ) {
                        Column(modifier = Modifier.padding(10.dp)) {
                            Text(
                                text = "推荐 ${idx + 1}: ${c.prompt}",
                                style = MaterialTheme.typography.bodySmall,
                                fontWeight = FontWeight.Medium,
                                color = MaterialTheme.colorScheme.onSurface
                            )
                            if (c.effect.isNotEmpty() || c.reason.isNotEmpty()) {
                                HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp), color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f))
                                if (c.effect.isNotEmpty()) {
                                    Text("🎯 预期效果: ${c.effect}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.secondary)
                                }
                                if (c.reason.isNotEmpty()) {
                                    Text("💡 建议理由: ${c.reason}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                }
            }
        }

        if (generatedPrompt.isNotEmpty()) {
            Surface(
                color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.3f),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(10.dp)) {
                    Text(
                        "生成的提示词：",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    SelectionContainer {
                        Text(
                            generatedPrompt,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Button(
                            onClick = onUsePrompt,
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                        ) {
                            Text("填入输入框", fontSize = 11.sp)
                        }
                        OutlinedButton(
                            onClick = onCopyPrompt,
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                        ) {
                            Text("复制提示词", fontSize = 11.sp)
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UiLocatorDialog(
    loading: Boolean,
    error: String?,
    device: String?,
    baseUrl: String,
    onDismiss: () -> Unit,
    onLocate: (x: Int, y: Int, width: Int, height: Int) -> Unit,
) {
    androidx.compose.ui.window.Dialog(
        onDismissRequest = onDismiss,
        properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = MaterialTheme.colorScheme.surface,
            modifier = Modifier
                .fillMaxWidth(0.95f)
                .fillMaxHeight(0.85f)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            text = "📸 手机端 UI 定位模式",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        device?.let {
                            Text(
                                text = "已连设备: $it",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }
                    }
                    IconButton(onClick = onDismiss, modifier = Modifier.size(28.dp)) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "关闭",
                            modifier = Modifier.size(16.dp)
                        )
                    }
                }

                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.4f))

                if (loading) {
                    Column(
                        modifier = Modifier.weight(1f).fillMaxWidth(),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(36.dp))
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = "正在同步手机界面，请稍候...",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                } else {
                    if (error != null) {
                        Surface(
                            color = MaterialTheme.colorScheme.errorContainer,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp)
                        ) {
                            Text(
                                text = error,
                                color = MaterialTheme.colorScheme.onErrorContainer,
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.padding(8.dp)
                            )
                        }
                    } else {
                        Text(
                            text = "请点击截图中您想要优化或修改的元素位置：",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }

                    // Show screenshot and handle touch events
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .background(Color.Black.copy(alpha = 0.05f)),
                        contentAlignment = Alignment.Center
                    ) {
                        val imageUrl = "$baseUrl/ui-locator/screen.png?t=${System.currentTimeMillis()}"
                        var imageWidth by remember { mutableStateOf(0) }
                        var imageHeight by remember { mutableStateOf(0) }

                        coil.compose.AsyncImage(
                            model = imageUrl,
                            contentDescription = "手机屏幕截图",
                            modifier = Modifier
                                .fillMaxSize()
                                .onGloballyPositioned { coordinates ->
                                    imageWidth = coordinates.size.width
                                    imageHeight = coordinates.size.height
                                }
                                .pointerInput(Unit) {
                                    detectTapGestures { offset ->
                                        if (imageWidth > 0 && imageHeight > 0) {
                                            onLocate(
                                                offset.x.toInt(),
                                                offset.y.toInt(),
                                                imageWidth,
                                                imageHeight
                                            )
                                        }
                                    }
                                },
                            contentScale = ContentScale.Fit
                        )
                    }
                }
            }
        }
    }
}

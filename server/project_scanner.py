#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AideLink 项目结构扫描器
========================
扫描 Kotlin（Android）和 Python（Server）源码，提取组件/路由/类定义，
生成分类树形 JSON 供手机端"项目地图"使用。

使用方式：
  python project_scanner.py              # 直接运行，输出到 project_map.json
  from project_scanner import scan_project  # 作为模块导入
"""

import os
import re
import json
import hashlib
import ast
import copy
from datetime import datetime
from json_utils import safe_read_json, safe_write_json

# 项目根目录（AideLink 仓库根）
from paths import PROJECT_ROOT, STATE_DIR, get_project_root
BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BRIDGE_DIR, "project_map.json")
PROJECT_MAP_CACHE_DIR = os.path.join(str(STATE_DIR), "project_maps")


def _current_root():
    return os.path.abspath(str(get_project_root()))


def _normalized_root(path):
    return os.path.normcase(os.path.normpath(str(path or "")))


def _cache_file(project_root=None):
    root = _normalized_root(project_root or _current_root())
    digest = hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]
    return os.path.join(PROJECT_MAP_CACHE_DIR, f"project_map_{digest}.json")


def _learned_file(project_root=None):
    root = _normalized_root(project_root or _current_root())
    digest = hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]
    return os.path.join(PROJECT_MAP_CACHE_DIR, f"learned_components_{digest}.json")


def add_learned_component(surface, component):
    """保存截图/运行态识别出的组件，使后续扫描仍可复用。"""
    if surface not in {"android", "web", "windows"}:
        raise ValueError(f"unsupported surface: {surface}")
    os.makedirs(PROJECT_MAP_CACHE_DIR, exist_ok=True)
    data = safe_read_json(_learned_file(), {"components": []}) or {"components": []}
    components = list(data.get("components") or [])
    item = dict(component or {})
    stable_source = "|".join([
        surface,
        str(item.get("page") or ""),
        str(item.get("area") or ""),
        str(item.get("name") or ""),
    ])
    item["id"] = item.get("id") or f"learned_{hashlib.sha256(stable_source.encode('utf-8')).hexdigest()[:16]}"
    item["surface"] = surface
    item["source"] = item.get("source") or "screenshot"
    item["confidence"] = float(item.get("confidence") or 0.65)
    item["category"] = item.get("category") or "交互"
    components = [existing for existing in components if existing.get("id") != item["id"]]
    components.append(item)
    safe_write_json(_learned_file(), {"components": components})
    return item


def _learned_pages(surface):
    data = safe_read_json(_learned_file(), {"components": []}) or {"components": []}
    groups = {}
    for item in data.get("components") or []:
        if item.get("surface") != surface:
            continue
        page_name = str(item.get("page") or "截图识别组件").strip()
        page = groups.setdefault(page_name, {
            "id": f"{surface}_learned_{_make_id(page_name)}",
            "name": f"✨ {page_name}",
            "description": "通过截图或运行态采集补充的界面",
            "children": [],
        })
        page["children"].append({
            "id": item.get("id", ""),
            "name": f"[组件] {item.get('name') or '未命名组件'}",
            "description": item.get("description") or item.get("area") or "截图识别组件",
            "category": item.get("category", "交互"),
            "file": item.get("file", ""),
            "line_start": item.get("line_start", 0),
            "line_end": item.get("line_end", 0),
            "source": item.get("source", "screenshot"),
            "confidence": item.get("confidence", 0.65),
            "bounds": item.get("bounds"),
        })
    return list(groups.values())


def _get_app_name():
    """获取 App 子项目名称（从 settings 动态读取）"""
    from config import load_settings
    try:
        return load_settings().get("app_project_name", "")
    except Exception:
        return "AideLink-app"


def load_strings_xml():
    strings = {}
    path = os.path.join(PROJECT_ROOT, _get_app_name(), "app", "src", "main", "res", "values", "strings.xml")
    if os.path.isfile(path):
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(path)
            root = tree.getroot()
            for string_elem in root.findall("string"):
                name = string_elem.get("name")
                text = string_elem.text
                if name and text:
                    strings[name] = text
        except Exception as e:
            print(f"Error parsing strings.xml: {e}")
    return strings


def _get_file_mtime(filepath):
    """获取文件修改时间（ISO 格式）"""
    try:
        mtime = os.path.getmtime(filepath)
        return datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
    except Exception:
        return None


_STRINGS_DICT = load_strings_xml()


def extract_ui_elements(lines, start_line_0based, end_line_0based, strings_dict, rel_path):
    """
    提取 Composable 函数体内的关键 UI 元素。
    核心思路：用户看到的是屏幕上的文字和控件，按类型分组。
    """
    body_lines = lines[start_line_0based:end_line_0based+1]
    elements = []
    
    # 按用户可见性分类：交互控件 > 展示控件 > 布局容器
    # 交互控件：用户能点击/输入/选择的
    # 展示控件：用户能看到的静态内容
    # 布局容器：用户看不到但影响布局的
    
    interactive_patterns = [
        (r'\bButton\b', '按钮', 'Button'),
        (r'\bTextButton\b', '文字按钮', 'TextButton'),
        (r'\bIconButton\b', '图标按钮', 'IconButton'),
        (r'\bOutlinedButton\b', '边框按钮', 'OutlinedButton'),
        (r'\bFilledTonalButton\b', '填充按钮', 'FilledTonalButton'),
        (r'\bFloatingActionButton\b', '悬浮按钮', 'FloatingActionButton'),
        (r'\bSmallFloatingActionButton\b', '小悬浮按钮', 'SmallFloatingActionButton'),
        (r'\bExtendedFloatingActionButton\b', '扩展悬浮按钮', 'ExtendedFloatingActionButton'),
        (r'\bOutlinedTextField\b', '输入框', 'OutlinedTextField'),
        (r'\bTextField\b', '输入框', 'TextField'),
        (r'\bBasicTextField\b', '基础输入框', 'BasicTextField'),
        (r'\bSwitch\b', '开关', 'Switch'),
        (r'\bCheckbox\b', '复选框', 'Checkbox'),
        (r'\bRadioButton\b', '单选按钮', 'RadioButton'),
        (r'\bSlider\b', '滑块', 'Slider'),
        (r'\bRangeSlider\b', '范围滑块', 'RangeSlider'),
        (r'\bDropdownMenu\b', '下拉菜单', 'DropdownMenu'),
        (r'\bDropdownMenuItem\b', '下拉选项', 'DropdownMenuItem'),
        (r'\bExposedDropdownMenu\b', '展开下拉菜单', 'ExposedDropdownMenu'),
        (r'\bFilterChip\b', '筛选芯片', 'FilterChip'),
        (r'\bAssistChip\b', '辅助芯片', 'AssistChip'),
        (r'\bSuggestionChip\b', '建议芯片', 'SuggestionChip'),
        (r'\bTab\b', '标签页', 'Tab'),
        (r'\bTabRow\b', '标签栏', 'TabRow'),
        (r'\bNavigationBarItem\b', '导航栏项', 'NavigationBarItem'),
        (r'\bBottomNavigationItem\b', '底部导航项', 'BottomNavigationItem'),
        (r'\bSwipeToDismiss\b', '滑动操作', 'SwipeToDismiss'),
        (r'\bModalBottomSheet\b', '模态底部抽屉', 'ModalBottomSheet'),
        (r'\bBottomSheet\b', '底部抽屉', 'BottomSheet'),
        (r'\bDrawerState\b', '抽屉', 'DrawerState'),
        (r'\bAlertDialog\b', '对话框', 'AlertDialog'),
        (r'\bBasicAlertDialog\b', '基础对话框', 'BasicAlertDialog'),
    ]
    
    display_patterns = [
        (r'\bText\b', '文本', 'Text'),
        (r'\bRichText\b', '富文本', 'RichText'),
        (r'\bIcon\b', '图标', 'Icon'),
        (r'\bImage\b', '图片', 'Image'),
        (r'\bAsyncImage\b', '异步图片', 'AsyncImage'),
        (r'\bCoilImage\b', 'Coil图片', 'CoilImage'),
        (r'\bCard\b', '卡片', 'Card'),
        (r'\bElevatedCard\b', '浮起卡片', 'ElevatedCard'),
        (r'\bOutlinedCard\b', '边框卡片', 'OutlinedCard'),
        (r'\bSurface\b', '表面', 'Surface'),
        (r'\bCircularProgressIndicator\b', '加载指示器', 'CircularProgressIndicator'),
        (r'\bLinearProgressIndicator\b', '进度条', 'LinearProgressIndicator'),
        (r'\bBadge\b', '徽章', 'Badge'),
        (r'\bTooltip\b', '提示', 'Tooltip'),
        (r'\bDivider\b', '分割线', 'Divider'),
        (r'\bHorizontalDivider\b', '水平分割线', 'HorizontalDivider'),
        (r'\bVerticalDivider\b', '垂直分割线', 'VerticalDivider'),
        (r'\bSpacer\b', '间距', 'Spacer'),
        (r'\bCanvas\b', '画布', 'Canvas'),
    ]
    
    layout_patterns = [
        (r'\bScaffold\b', '脚手架', 'Scaffold'),
        (r'\bTopAppBar\b', '顶部应用栏', 'TopAppBar'),
        (r'\bMediumTopAppBar\b', '中等顶部栏', 'MediumTopAppBar'),
        (r'\bLargeTopAppBar\b', '大顶部栏', 'LargeTopAppBar'),
        (r'\bBottomAppBar\b', '底部应用栏', 'BottomAppBar'),
        (r'\bNavigationBar\b', '导航栏', 'NavigationBar'),
        (r'\bBottomNavigation\b', '底部导航', 'BottomNavigation'),
        (r'\bLazyColumn\b', '可滚动列表', 'LazyColumn'),
        (r'\bLazyRow\b', '可滚动横向列表', 'LazyRow'),
        (r'\bLazyVerticalGrid\b', '可滚动网格', 'LazyVerticalGrid'),
        (r'\bLazyVerticalStaggeredGrid\b', '瀑布流网格', 'LazyVerticalStaggeredGrid'),
        (r'\bColumn\b', '列布局', 'Column'),
        (r'\bRow\b', '行布局', 'Row'),
        (r'\bBox\b', '容器', 'Box'),
        (r'\bBoxWithConstraints\b', '约束容器', 'BoxWithConstraints'),
        (r'\bFlowRow\b', '流式行', 'FlowRow'),
        (r'\bFlowColumn\b', '流式列', 'FlowColumn'),
        (r'\bConstraintLayout\b', '约束布局', 'ConstraintLayout'),
    ]
    
    all_patterns = interactive_patterns + display_patterns + layout_patterns
    
    # 过滤规则：排除无意义的短文本和框架内部文本
    EXCLUDE_LABELS = {
        "", "user", "assistant", "auto", "code", "aidelink", "mimocode",
        "opencode", "trae", "antigravity", "ok", "cancel", "yes", "no",
        "true", "false", "null", "error", "success", "loading",
        "http", "https", "file", "content", "text", "icon", "image",
    }
    
    def extract_label(lookahead_lines):
        """从组件周围代码中提取可见文本标签"""
        text = "\n".join(lookahead_lines)
        
        # 1. 优先：strings.xml 引用
        r_string = re.search(r'R\.string\.([a-zA-Z0-9_]+)', text)
        if r_string:
            key = r_string.group(1)
            resolved = strings_dict.get(key, "")
            if resolved:
                return resolved
        
        # 2. contentDescription 参数
        cd_match = re.search(r'contentDescription\s*=\s*"([^"]+)"', text)
        if cd_match:
            val = cd_match.group(1).strip()
            if val and len(val) < 40 and val.lower() not in EXCLUDE_LABELS:
                return val
        
        # 3. text 参数
        text_match = re.search(r'text\s*=\s*"([^"]+)"', text)
        if text_match:
            val = text_match.group(1).strip()
            if val and len(val) < 40 and val.lower() not in EXCLUDE_LABELS:
                return val
        
        # 4. label 参数
        label_match = re.search(r'label\s*=\s*\{\s*Text\s*\(\s*"([^"]+)"', text)
        if label_match:
            val = label_match.group(1).strip()
            if val and len(val) < 40 and val.lower() not in EXCLUDE_LABELS:
                return val
        
        # 5. title 参数
        title_match = re.search(r'title\s*=\s*\{\s*Text\s*\(\s*"([^"]+)"', text)
        if not title_match:
            title_match = re.search(r'title\s*=\s*"([^"]+)"', text)
        if title_match:
            val = title_match.group(1).strip()
            if val and len(val) < 40 and val.lower() not in EXCLUDE_LABELS:
                return val
        
        # 6. heading 参数
        heading_match = re.search(r'heading\s*=\s*"([^"]+)"', text)
        if heading_match:
            val = heading_match.group(1).strip()
            if val and len(val) < 40 and val.lower() not in EXCLUDE_LABELS:
                return val
        
        # 7. 任意双引号字符串（排除 URL/路径/框架词）
        literals = re.findall(r'"([^"]{2,30})"', text)
        for lit in literals:
            lit = lit.strip()
            if (lit and 
                not lit.startswith("http") and 
                not lit.endswith(".apk") and 
                not lit.endswith(".png") and 
                not lit.endswith(".jpg") and
                not lit.endswith(".kt") and
                not lit.endswith(".py") and
                lit.lower() not in EXCLUDE_LABELS):
                # 排除纯英文变量名风格
                if re.match(r'^[a-z_][a-z0-9_]*$', lit):
                    continue
                return lit
        
        return ""
    
    seen = set()  # 去重
    
    for rel_idx, line in enumerate(body_lines):
        stripped = line.strip()
        # 排除注释行
        if stripped.startswith('//') or stripped.startswith('*') or stripped.startswith('/*'):
            continue
        
        matched_type = None
        matched_comp = None
        category = None
        
        for pat, type_cn, comp_name in interactive_patterns:
            if re.search(pat, line):
                matched_type = type_cn
                matched_comp = comp_name
                category = "交互"
                break
        
        if not matched_type:
            for pat, type_cn, comp_name in display_patterns:
                if re.search(pat, line):
                    matched_type = type_cn
                    matched_comp = comp_name
                    category = "展示"
                    break
        
        if not matched_type:
            for pat, type_cn, comp_name in layout_patterns:
                if re.search(pat, line):
                    matched_type = type_cn
                    matched_comp = comp_name
                    category = "布局"
                    break
        
        if not matched_type:
            continue
        
        abs_line_num = start_line_0based + rel_idx + 1
        
        # 查找组件周围的文本（后方 12 行 + 前方 3 行）
        look_start = max(0, rel_idx - 3)
        look_end = min(len(body_lines), rel_idx + 12)
        lookahead = body_lines[look_start:look_end]
        
        label = extract_label(lookahead)
        
        # 组合显示名
        if label:
            display_name = f"[{matched_type}] {label}"
        else:
            display_name = f"[{matched_type}] {matched_comp}"
        
        # 去重：同类型+同行 只保留一个
        dedup_key = f"{abs_line_num}_{matched_comp}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        
        node_id = f"ui_{abs_line_num}_{matched_comp.lower()}"
        
        # 提取用途描述：从周围上下文推断组件用途
        purpose = ""
        # 向上查找父级容器/对话框上下文
        context_start = max(0, rel_idx - 20)
        context_lines = body_lines[context_start:rel_idx]
        context_text = "\n".join(context_lines)
        
        # 查找对话框标题
        dialog_title = re.search(r'text\s*=\s*"([^"]{2,40})".*?(?:Dialog|Sheet|弹窗|对话框)', context_text, re.DOTALL)
        if not dialog_title:
            dialog_title = re.search(r'(?:Dialog|Sheet|弹窗|对话框).*?text\s*=\s*"([^"]{2,40})"', context_text, re.DOTALL)
        if dialog_title:
            purpose = dialog_title.group(1)
        
        # 查找 onClick 回调中的 Toast/导航等
        if not purpose and matched_comp in ['Button', 'TextButton', 'IconButton', 'OutlinedButton', 'FloatingActionButton']:
            onclick_area = body_lines[rel_idx:min(rel_idx + 8, len(body_lines))]
            onclick_text = "\n".join(onclick_area)
            toast_match = re.search(r'Toast\.makeText\([^,]+,\s*"([^"]+)"', onclick_text)
            if toast_match:
                purpose = toast_match.group(1)
            else:
                nav_match = re.search(r'navController\.(?:navigate|popBackStack)', onclick_text)
                if nav_match:
                    purpose = "导航跳转"
        
        # 查找 contentDescription 作为描述
        if not purpose:
            cd_desc = re.search(r'contentDescription\s*=\s*"([^"]+)"', "\n".join(body_lines[max(0,rel_idx-2):rel_idx+3]))
            if cd_desc:
                purpose = cd_desc.group(1)
        
        elements.append({
            "id": node_id,
            "name": display_name,
            "file": rel_path,
            "line_start": abs_line_num,
            "line_end": abs_line_num,
            "description": purpose or f"{category}控件",
            "category": category,
        })
    
    return elements


# ── Kotlin 扫描 ─────────────────────────────────────────────

# 匹配 @Composable fun XxxScreen(...) 或 @Composable fun XxxCard(...) 等
_RE_COMPOSABLE = re.compile(
    r'^@(?:OptIn\(.*?\)\s*\n)?@?Composable\s*\n\s*(?:(?:private|internal|public)\s+)?fun\s+(\w+)\s*\(',
    re.MULTILINE
)
# 简化版：匹配 fun XxxScreen( 和 fun XxxCard( 等大写开头的函数
_RE_COMPOSABLE_SIMPLE = re.compile(
    r'^\s*(?:(?:private|internal|public)\s+)?fun\s+([A-Z]\w+)\s*\(',
    re.MULTILINE
)
# 匹配 @Composable 注解（独占一行）
_RE_COMPOSABLE_ANNO = re.compile(r'@Composable', re.MULTILINE)
_RE_COMPOSE_UI_BUILDER = re.compile(
    r'^\s*(?:(?:private|internal|public)\s+)?fun\s+'
    r'(?:LazyListScope|LazyGridScope|ColumnScope|RowScope)\.(\w+)\s*\(',
    re.MULTILINE,
)
# 匹配 class/object 定义
_RE_CLASS = re.compile(
    r'^\s*(?:@\w+\s+)*(?:data\s+)?(?:class|object)\s+(\w+)',
    re.MULTILINE
)
# 匹配 ViewModel 类
_RE_VIEWMODEL = re.compile(
    r'class\s+(\w+ViewModel)\s+',
    re.MULTILINE
)

def _find_function_end(lines, start_line_0based):
    """从函数定义行向下找，用大括号计数估算函数结束行（0-based）"""
    depth = 0
    started = False
    for i in range(start_line_0based, len(lines)):
        line = lines[i]
        for ch in line:
            if ch == '{':
                depth += 1
                started = True
            elif ch == '}':
                depth -= 1
                if started and depth <= 0:
                    return i
    return len(lines) - 1


_COMPOSABLE_CHINESE_NAMES = {
    'AboutScreen': 'ℹ️ "关于"介绍页面',
    'AddServerDialog': '➕ "添加服务器"弹窗',
    'AideLinkChatScreen': '🤖 IDE 助手聊天主页面',
    'AideLinkHomeScreen': '🏠 AideLink 主导航外层',
    'AideLinkSettingsScreen': '⚙️ 设置主页面',
    'AideLinkTabScreen': '⚡ Aide 对话面板',
    'AssistantMessageBubble': '🤖 AI 助手回复的气泡',
    'BatteryOptimizationBanner': '🔋 电池优化警告条',
    'ChatBubble': '💬 聊天气泡',
    'ChatInputBar': '⌨️ 聊天输入栏',
    'ConnectionSettingsDialog': '🔌 连接配置对话框',
    'ConversationList': '📋 聊天历史消息列表',
    'CropSliderDark': '✂️ 截图裁剪滑块',
    'CustomIdePathDialog': '📁 自定义 IDE 路径对话框',
    'DesktopIdeManagerDialog': '💻 本机 IDE 软件管理弹窗',
    'DirectoryRow': '📁 文件夹列表行',
    'EmptyServersView': '🖥️ 空服务器列表提示',
    'HappyScreen': '🎉 Happy 控制台页面 (网页)',
    'HomeScreen': '🏠 主页 (服务器列表与本地运行控制)',
    'IdeChatMessageBubble': '💬 IDE 聊天气泡',
    'IdeChatScreen': '🤖 IDE 注入式对话主页面',
    'InputBar': '⌨️ 消息发送输入框',
    'LocalLaunchOptionsDialog': '⚙️ 本地服务启动配置弹窗',
    'LocalRuntimeCard': '🖥️ 本地运行时状态控制卡片',
    'MarkdownContent': '📝 富文本/代码块显示区',
    'MessageBubble': '💬 消息对话气泡',
    'MimoControlBar': '🤖 Aide 服务控制条',
    'NewSessionQuickDialog': '➕ 新建会话快速弹窗',
    'OcChatMessageItem': '💬 OpenCode 消息气泡',
    'OcChatScreen': '🤖 OpenCode Remote 对话页面',
    'OcModelPickerDialog': '🧠 OpenCode 模型选择对话框',
    'OcServerCard': '🖥️ OpenCode 服务器连接卡片',
    'OpenProjectDialog': '📂 打开项目文件夹对话框',
    'PreviewAssistantMessage': '🤖 AI 回复内容预览块',
    'PreviewStreamingMessage': '⏳ 正在生成的 AI 回复预览',
    'PreviewUserMessage': '👤 用户发送内容预览块',
    'ProjectHeader': '📂 项目标题栏',
    'ProjectMapPanel': '🗺️ 项目地图面板',
    'PromptBuilderSection': '📋 提示词构建器操作区',
    'ProviderRow': '📡 服务提供商配置行',
    'PulsingDotsIndicator': '⏳ AI 正在思考/加载动画',
    'QrScannerContent': '📷 扫码配置界面',
    'QuickActionCard': '⚡ 快速操作按钮卡片',
    'QuickReplyManagerDialog': '💬 管理快捷回复弹窗',
    'ScannedIdesDialog': '🔍 本地 IDE 软件扫描列表',
    'ScreenMonitorPanel': '🖥️ 电脑屏幕监控画面面板',
    'SectionTitle': '📌 分类小标题',
    'ServerCard': '🖥️ 远程服务器卡片',
    'ServerDialog': '➕ 添加/修改服务器弹窗',
    'ServerItem': '🖥️ 服务器列表单项',
    'ServerListSection': '📋 服务器分组列表',
    'ServerModelFilterScreen': '🧠 服务器模型过滤与设置页面',
    'ServerProvidersScreen': '📡 服务器提供商设置页面',
    'ServerSettingsScreen': '⚙️ 服务器连接与API Key设置页面',
    'ServerTabScreen': '🖥️ 服务器与模型管理主页',
    'SessionCard': '📋 会话列表单项卡片',
    'SessionListDialog': '📋 快速切换会话弹窗',
    'SessionListScreen': '📋 历史会话管理列表页面',
    'SessionRow': '📋 会话列表项',
    'StreamingContent': '⏳ 正在输出的消息文本',
    'StreamingIndicator': '⏳ 正在输入状态指示器',
    'TargetBadge': '🎯 发送目标 IDE 徽章',
    'TargetChips': '🎯 发送目标 IDE 选择按钮组',
    'TargetIcon': '🎯 发送目标图标',
    'ToolCallCard': '🛠️ AI 正在执行的工具/命令卡片',
    'ToolMenuDropdown': '⚙️ Aide 右上角设置下拉菜单',
    'TreeCategoryItem': '🗺️ 项目地图树状单项',
    'UserMessageBubble': '👤 用户发送的消息气泡',
    'WebPanelDialog': '🌐 网页控制面板弹窗',
    'WebViewScreen': '🌐 网页浏览器容器页面',
    'ZoomableLiveMonitorDialog': '🖥️ 电脑屏幕监控大图弹窗',
}

def get_friendly_name(name):
    if name in _COMPOSABLE_CHINESE_NAMES:
        return _COMPOSABLE_CHINESE_NAMES[name]
    if name.endswith("ViewModel"):
        return f"🧠 业务逻辑与状态管理 ({name})"
    return name


def scan_kotlin_file(filepath, rel_path):
    """扫描单个 Kotlin 文件，返回组件节点列表"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    lines = content.split('\n')
    nodes = []

    # 1. 找所有 @Composable 注解的位置
    composable_lines = set()
    for m in _RE_COMPOSABLE_ANNO.finditer(content):
        line_num = content[:m.start()].count('\n')
        composable_lines.add(line_num)
        composable_lines.add(line_num + 1)
        composable_lines.add(line_num + 2)  # 可能隔一行

    # 2. 提取大写开头函数（可能是 Composable）
    for m in _RE_COMPOSABLE_SIMPLE.finditer(content):
        func_name = m.group(1)
        line_num_0 = content[:m.start()].count('\n')

        # 检查是否有 @Composable 注解在附近
        is_composable = any(ln in composable_lines for ln in range(max(0, line_num_0 - 3), line_num_0 + 1))

        # 只关注 Composable 函数和重要的普通函数
        if not is_composable:
            continue

        end_line_0 = _find_function_end(lines, line_num_0)

        # 提取内部 UI 元素
        ui_children = extract_ui_elements(lines, line_num_0, end_line_0, _STRINGS_DICT, rel_path)

        friendly_func_name = get_friendly_name(func_name)

        node = {
            "id": _make_id(func_name),
            "name": friendly_func_name,
            "file": rel_path,
            "line_start": line_num_0 + 1,  # 转 1-based
            "line_end": end_line_0 + 1,
            "composable": func_name,
            "description": "",
        }
        node["last_modified"] = _get_file_mtime(filepath)
        node["line_count"] = end_line_0 - line_num_0 + 1

        if ui_children:
            # 添加一个代表容器本身的可点击节点
            self_node = {
                "id": _make_id(f"{func_name}_container"),
                "name": f"🎨 容器整体: {friendly_func_name}",
                "file": rel_path,
                "line_start": line_num_0 + 1,
                "line_end": end_line_0 + 1,
                "composable": func_name,
                "description": f"对整个 {friendly_func_name} 组件进行操作",
            }
            self_node["last_modified"] = _get_file_mtime(filepath)
            self_node["line_count"] = end_line_0 - line_num_0 + 1
            node["children"] = [self_node] + ui_children
            
        nodes.append(node)

    # 3. Compose 的 LazyListScope/ColumnScope 等 UI DSL 函数没有 @Composable，
    # 但它们直接决定页面分区，必须纳入组件调用图。
    existing_composables = {node.get("composable") for node in nodes}
    for match in _RE_COMPOSE_UI_BUILDER.finditer(content):
        func_name = match.group(1)
        if func_name in existing_composables:
            continue
        line_num_0 = content[:match.start()].count("\n")
        end_line_0 = _find_function_end(lines, line_num_0)
        ui_children = extract_ui_elements(
            lines, line_num_0, end_line_0, _STRINGS_DICT, rel_path,
        )
        if not ui_children:
            continue
        readable = re.sub(r"(?<!^)(?=[A-Z])", " ", func_name).replace("_", " ").strip()
        nodes.append({
            "id": _make_id(func_name),
            "name": readable,
            "file": rel_path,
            "line_start": line_num_0 + 1,
            "line_end": end_line_0 + 1,
            "composable": func_name,
            "description": f"页面区域: {readable}",
            "last_modified": _get_file_mtime(filepath),
            "line_count": end_line_0 - line_num_0 + 1,
            "children": ui_children,
        })

    # 4. 提取 ViewModel 类
    for m in _RE_VIEWMODEL.finditer(content):
        vm_name = m.group(1)
        line_num_0 = content[:m.start()].count('\n')
        end_line_0 = _find_function_end(lines, line_num_0)
        node = {
            "id": _make_id(vm_name),
            "name": get_friendly_name(vm_name),
            "file": rel_path,
            "line_start": line_num_0 + 1,
            "line_end": end_line_0 + 1,
            "class": vm_name,
            "description": "ViewModel - 状态管理",
        }
        node["last_modified"] = _get_file_mtime(filepath)
        node["line_count"] = end_line_0 - line_num_0 + 1
        nodes.append(node)

    return nodes


# ── Python 扫描 ──────────────────────────────────────────────

_RE_FLASK_ROUTE = re.compile(
    r"^@app\.route\(\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE
)
_RE_PY_FUNC = re.compile(
    r'^def\s+(\w+)\s*\(',
    re.MULTILINE
)
_RE_PY_CLASS = re.compile(
    r'^class\s+(\w+)',
    re.MULTILINE
)

_KNOWN_ROUTE_NAMES = {
    "/ping": "🔌 服务健康检查 (Ping)",
    "/history": "📋 获取历史消息 (History)",
    "/send": "✉️ 发送或委派消息 (Send)",
    "/sessions": "💻 获取 IDE 会话列表 (Sessions)",
    "/clipboard": "📋 获取系统剪贴板 (Clipboard)",
    "/clipboard/append": "📥 追加剪贴板内容 (Append)",
    "/clipboard/clear": "🧹 清空剪贴板 (Clear)",
    "/upload": "📤 上传图片或附件 (Upload)",
    "/screenshot/full": "🖥️ 获取电脑全屏截图 (Full)",
    "/screenshot/crop": "✂️ 获取框选区域截图 (Crop)",
    "/window/focus-input": "🎯 聚焦到目标输入框 (Focus Input)",
    "/window/focus": "🔍 激活目标窗口 (Focus Window)",
    "/window/info": "ℹ️ 获取窗口坐标信息 (Window Info)",
    "/xiaomengling/mimo/status": "🤖 获取 Aide运行状态 (Mimo Status)",
    "/xiaomengling/mimo/start": "▶️ 启动 Aide 服务 (Start Mimo)",
    "/xiaomengling/mimo/stop": "⏹️ 停止 Aide 服务 (Stop Mimo)",
    "/xiaomengling/models": "🧠 获取 Aide可用模型 (Mimo Models)",
    "/xiaomengling/models/set": "⚙️ 设置 Aide当前模型 (Set Model)",
    "/xiaomengling/mimo/weburl": "🌐 获取 Aide Web 端 URL (Web URL)",
    "/xiaomengling/session/new": "➕ 创建 Aide新会话 (New Session)",
    "/settings": "⚙️ 获取或修改系统设置 (Settings)",
    "/screen/wake": "⏰ 唤醒电脑屏幕 (Wake Screen)",
    "/screen/ensure-unlocked": "🔓 确保屏幕已解锁 (Ensure Unlocked)",
    "/project-map": "🗺️ 获取项目结构地图 (Get Map)",
    "/project-map/scan": "🔄 扫描并更新项目地图 (Scan Map)",
}

def scan_python_file(filepath, rel_path):
    """扫描单个 Python 文件，返回组件节点列表"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    lines = content.split('\n')
    nodes = []

    # 1. Flask 路由
    route_positions = []
    for m in _RE_FLASK_ROUTE.finditer(content):
        route_path = m.group(1)
        line_num_0 = content[:m.start()].count('\n')
        route_positions.append((route_path, line_num_0))

    # 找路由对应的处理函数
    func_positions = []
    for m in _RE_PY_FUNC.finditer(content):
        func_name = m.group(1)
        line_num_0 = content[:m.start()].count('\n')
        func_positions.append((func_name, line_num_0))

    for route_path, route_line in route_positions:
        # 找路由下方最近的函数定义
        handler = None
        for func_name, func_line in func_positions:
            if func_line >= route_line and func_line <= route_line + 5:
                handler = func_name
                handler_line = func_line
                break

        if handler:
            # 找函数结束行
            end_line_0 = _find_py_func_end(lines, handler_line)
            # 使用友好名称
            route_display_name = _KNOWN_ROUTE_NAMES.get(route_path, route_path)
            node = {
                "id": _make_id(f"route_{route_path.replace('/', '_')}"),
                "name": route_display_name,
                "file": rel_path,
                "line_start": route_line + 1,
                "line_end": end_line_0 + 1,
                "function": handler,
                "description": f"Flask 路由 → {handler}()",
            }
            node["last_modified"] = _get_file_mtime(filepath)
            node["line_count"] = end_line_0 - route_line + 1
            nodes.append(node)

    # 2. 类定义（仅顶层有意义的类）
    for m in _RE_PY_CLASS.finditer(content):
        class_name = m.group(1)
        line_num_0 = content[:m.start()].count('\n')
        # 跳过已被路由覆盖的行
        if any(abs(line_num_0 - n.get("line_start", 0) + 1) < 5 for n in nodes):
            continue
        end_line_0 = _find_py_func_end(lines, line_num_0)
        node = {
            "id": _make_id(class_name),
            "name": class_name,
            "file": rel_path,
            "line_start": line_num_0 + 1,
            "line_end": end_line_0 + 1,
            "class": class_name,
            "description": "",
        }
        node["last_modified"] = _get_file_mtime(filepath)
        node["line_count"] = end_line_0 - line_num_0 + 1
        nodes.append(node)

    return nodes


def _find_py_func_end(lines, start_line_0based):
    """Python 函数/类结束行估算：找下一个同缩进的 def/class 或文件末尾"""
    if start_line_0based >= len(lines):
        return len(lines) - 1

    # 获取起始行的缩进
    start_line = lines[start_line_0based]
    base_indent = len(start_line) - len(start_line.lstrip())

    for i in range(start_line_0based + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            continue
        current_indent = len(line) - len(line.lstrip())
        # 遇到同级或更低缩进的 def/class/装饰器，认为上一个结束
        if current_indent <= base_indent and (
            stripped.startswith('def ') or
            stripped.startswith('class ') or
            stripped.startswith('@app.route') or
            (stripped.startswith('@') and not stripped.startswith('@staticmethod') and not stripped.startswith('@classmethod'))
        ):
            return i - 1

    return len(lines) - 1


def _make_id(name):
    """生成 ID：小写 + 下划线"""
    # CamelCase -> snake_case
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    result = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    # 清理特殊字符
    result = re.sub(r'[^a-z0-9_]', '_', result)
    result = re.sub(r'_+', '_', result).strip('_')
    return result


# ── 描述增强 ─────────────────────────────────────────────────

# 已知组件的中文描述（静态映射，避免每次调 API）
_KNOWN_DESCRIPTIONS = {
    # Android Screens
    "HomeScreen": "主页面 - 服务器列表和管理",
    "AideLinkHomeScreen": "首页包装器 - 桥接 NavGraph 和 HomeScreen",
    "LocalRuntimeCard": "本地 Termux 运行时管理卡片 - 启动/停止/安装",
    "ServerCard": "远程服务器连接管理卡片",
    "ServerDialog": "添加/编辑服务器的对话框",
    "AideLinkTabScreen": "Aide 对话面板 - MiniMax AI 交互",
    "AideLinkChatScreen": "桌面 IDE 对话页面 - 消息发送与截图监控",
    "ChatScreen": "OpenCode 会话对话页面",
    "OcChatScreen": "OpenCode Remote 对话界面",
    "SessionListScreen": "会话列表页面 - 显示所有 IDE 会话",
    "AideLinkSettingsScreen": "设置页面 - 主题/语言/连接配置",
    "ServerTabScreen": "服务器管理 Tab 页面",
    "IdeChatScreen": "IDE 对话页面 - 注入式 IDE 交互",
    "HappyScreen": "Happy Console 页面",
    "WebViewScreen": "WebView 容器页面",
    "MainScreen": "底部导航栏主框架",
    # ViewModels
    "HomeViewModel": "首页状态管理 - 服务器连接/本地运行时",
    "AideLinkTabViewModel": "Aide面板状态管理 - 消息/模型选择",
    "ChatViewModel": "对话页状态管理 - 消息收发/截图",
    # UI Components
    "ConversationList": "对话消息列表",
    "ChatBubble": "聊天气泡组件",
    "InputBar": "底部消息输入栏",
    "ToolMenuDropdown": "工具菜单下拉框 - OpenCode 启停/模型选择",
    "EmptyServersView": "空服务器列表提示",
    "BatteryOptimizationBanner": "电池优化警告横幅",
    "LocalLaunchOptionsDialog": "本地服务器启动选项对话框",
    "PulsingDotsIndicator": "加载动画 - 脉冲点指示器",
    # Python
    "send_message": "发送消息处理 - 路由到 MiniMax 或 IDE",
    "wake_screen": "屏幕唤醒 - 含锁屏检测和解除",
    "TaskRuntime": "任务运行时 - 管理 IDE 任务派发与状态",
}

def _enrich_description(node):
    """用静态映射补充描述"""
    name = node.get("composable") or node.get("function") or node.get("class") or node.get("name", "")
    if not node.get("description") and name in _KNOWN_DESCRIPTIONS:
        node["description"] = _KNOWN_DESCRIPTIONS[name]
    return node


# ── 导航树发现 ───────────────────────────────────────────────

def discover_navigation_tree(project_root):
    """
    From MainActivity entry, trace NavHost navigation tree.
    Returns: {"entry": str, "entry_file": str, "screens": [{"route": str, "composable": str, "file": str}]}
    """
    app_base = os.path.join(project_root, _get_app_name(), "app", "src", "main",
                            "java", "cc", "aidelink", "app")
    entry_composable = _find_setcontent_entry(app_base, project_root)
    if not entry_composable:
        return {"entry": None, "screens": []}
    screens = _trace_navhost(app_base, entry_composable["name"], entry_composable["file"], project_root)
    return {"entry": entry_composable["name"], "entry_file": entry_composable["file"], "screens": screens}


def _find_setcontent_entry(app_base, project_root):
    """Find Activity's setContent { ... } call, extract root composable"""
    for fname in os.listdir(app_base):
        if not fname.endswith("Activity.kt"):
            continue
        fpath = os.path.join(app_base, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue
        m = re.search(r'setContent\s*\{[^}]*?(\w+Screen)\s*\(', content, re.DOTALL)
        if m:
            rel_path = os.path.relpath(fpath, project_root).replace('\\', '/')
            return {"name": m.group(1), "file": rel_path}
    return None


def _resolve_composable_file(app_base, func_name, project_root):
    """Find the file that defines a given composable function"""
    for root, dirs, files in os.walk(app_base):
        for fname in files:
            if not fname.endswith('.kt'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue
            if re.search(rf'(?:@Composable\s*\n\s*)?(?:private\s+|internal\s+|public\s+)?fun\s+{func_name}\s*\(', content):
                rel_path = os.path.relpath(fpath, project_root).replace('\\', '/')
                return rel_path
    return None


def _trace_navhost(app_base, root_composable, root_file, project_root):
    """Trace NavHost from root composable, extract all routes"""
    resolved_file = _resolve_composable_file(app_base, root_composable, project_root)
    fpath = os.path.join(project_root, resolved_file or root_file)
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    navhost_match = re.search(r'NavHost\s*\(', content)
    if not navhost_match:
        m = re.search(rf'fun\s+{root_composable}\s*\([^)]*\)\s*\{{', content)
        if m:
            body_start = m.end()
            lines = content.split('\n')
            body_end = _find_function_end(lines, content[:body_start].count('\n'))
            body = '\n'.join(lines[body_start:body_end])
            inner_match = re.search(r'NavHost\s*\(', body)
            if not inner_match:
                screen_match = re.search(r'(\w+Screen)\s*\(', body)
                if screen_match:
                    inner_name = screen_match.group(1)
                    inner_file = _resolve_composable_file(app_base, inner_name, project_root)
                    if inner_file:
                        return _trace_navhost(app_base, inner_name, inner_file, project_root)
        return []

    navhost_pos = navhost_match.end()
    rest = content[navhost_pos:]

    screens = []
    for m in re.finditer(r'composable\s*\(\s*(?:["\']([^"\']+)["\']|(\w+(?:\.\w+)*\.route))\s*(?:,|\))', rest):
        route = m.group(1) or m.group(2)
        block_start = m.end()
        block_rest = rest[block_start:block_start + 2000]
        screen_call = re.search(r'(\w+Screen)\s*\(', block_rest)
        if screen_call:
            screen_name = screen_call.group(1)
            screen_file = _resolve_composable_file(app_base, screen_name, project_root)
            if screen_file:
                screens.append({"route": route, "composable": screen_name, "file": screen_file})

    all_screens = list(screens)
    for s in screens:
        sub_screens = _trace_navhost(app_base, s["composable"], s["file"], project_root)
        for sub in sub_screens:
            sub["parent"] = s["composable"]
            all_screens.append(sub)

    return all_screens


# ── 主扫描流程 ───────────────────────────────────────────────

def _scan_kotlin_screens():
    """扫描活跃 Android 页面（基于导航树遍历，过滤死代码）"""
    app_base = os.path.join(
        PROJECT_ROOT, _get_app_name(), "app", "src", "main",
        "java", "cc", "aidelink", "app"
    )

    nav_tree = discover_navigation_tree(PROJECT_ROOT)
    if not nav_tree.get("screens"):
        return _scan_kotlin_screens_fallback()

    active_files = {}
    for s in nav_tree["screens"]:
        rel_path = s["file"]
        if rel_path not in active_files:
            active_files[rel_path] = s

    screen_categories = []
    scanned_files = set()
    for rel_path, screen_info in active_files.items():
        fpath = os.path.join(PROJECT_ROOT, rel_path)
        if not os.path.isfile(fpath):
            continue
        nodes = scan_kotlin_file(fpath, rel_path)
        scanned_files.add(rel_path)

        screen_dir = os.path.dirname(fpath)
        for fname in sorted(os.listdir(screen_dir)):
            if not fname.endswith('.kt'):
                continue
            sibling_path = os.path.join(screen_dir, fname)
            sibling_rel = os.path.relpath(sibling_path, PROJECT_ROOT).replace('\\', '/')
            if sibling_rel in scanned_files:
                continue
            scanned_files.add(sibling_rel)
            sibling_nodes = scan_kotlin_file(sibling_path, sibling_rel)
            nodes.extend(sibling_nodes)

        for n in nodes:
            _enrich_description(n)
        if nodes:
            route = screen_info.get("route", "")
            composable = screen_info.get("composable", "")
            parent = screen_info.get("parent", "")
            category_name = f"📱 {composable}"
            if parent:
                category_name = f"📱 {parent} → {composable}"
            screen_categories.append({
                "id": f"nav_{route or composable}",
                "name": category_name,
                "route": route,
                "file": rel_path,
                "children": nodes,
            })
    return screen_categories


def _scan_kotlin_screens_fallback():
    """扫描 Android 客户端的 screens 目录（导航树发现失败时的兜底）"""
    screens_dir = os.path.join(
        PROJECT_ROOT, _get_app_name(), "app", "src", "main",
        "java", "cc", "aidelink", "app", "ui", "screens"
    )

    if not os.path.isdir(screens_dir):
        return []

    screen_categories = []

    for subdir in sorted(os.listdir(screens_dir)):
        subdir_path = os.path.join(screens_dir, subdir)
        if not os.path.isdir(subdir_path):
            continue

        screen_nodes = []
        for fname in sorted(os.listdir(subdir_path)):
            if not fname.endswith('.kt'):
                continue
            fpath = os.path.join(subdir_path, fname)
            rel_path = os.path.relpath(fpath, PROJECT_ROOT).replace('\\', '/')
            nodes = scan_kotlin_file(fpath, rel_path)
            for n in nodes:
                _enrich_description(n)
            screen_nodes.extend(nodes)

        category = {
            "id": f"screen_{subdir}",
            "name": subdir,
            "children": screen_nodes,
        }
        screen_categories.append(category)

    return screen_categories


def _scan_kotlin_screens_generic(project_root):
    """发现任意 Android/Compose 工程中的真实 Screen/Dialog 界面文件。"""
    candidates = []
    ignored_dirs = {".git", ".gradle", "build", "node_modules", ".idea", "generated"}
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        normalized = root.replace("\\", "/").lower()
        if "/src/main/" not in normalized:
            continue
        for filename in files:
            if not filename.endswith(".kt"):
                continue
            if not re.search(r"(screen|dialog|sheet|page|view)\.kt$", filename, re.IGNORECASE):
                continue
            candidates.append(os.path.join(root, filename))
            if len(candidates) >= 300:
                break
        if len(candidates) >= 300:
            break

    groups = {}
    for filepath in candidates:
        rel_path = os.path.relpath(filepath, project_root).replace("\\", "/")
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as source:
                content = source.read()
        except OSError:
            continue
        if "@Composable" not in content:
            continue
        nodes = scan_kotlin_file(filepath, rel_path)
        if not nodes:
            continue
        group_name = os.path.basename(os.path.dirname(filepath)) or "screens"
        group = groups.setdefault(group_name, {
            "id": f"screen_{_make_id(group_name)}",
            "name": f"📱 {group_name}",
            "children": [],
        })
        group["children"].extend(nodes)
    return list(groups.values())


def _scan_android_interfaces(project_root):
    """按真实 Composable 页面与组件调用关系构建通用 Android 界面地图。"""
    ignored_dirs = {".git", ".gradle", "build", "node_modules", ".idea", "generated"}
    registry = {}
    bodies = {}
    routes = {}

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [item for item in dirs if item not in ignored_dirs]
        if "/src/main/" not in root.replace("\\", "/").lower():
            continue
        for filename in files:
            if not filename.endswith(".kt"):
                continue
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, project_root).replace("\\", "/")
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as source:
                    content = source.read()
            except OSError:
                continue
            if "@Composable" not in content:
                continue
            lines = content.splitlines()
            for node in scan_kotlin_file(filepath, rel_path):
                name = node.get("composable")
                if not name:
                    continue
                registry[name] = node
                start = max(0, int(node.get("line_start") or 1) - 1)
                end = min(len(lines), int(node.get("line_end") or len(lines)))
                bodies[name] = "\n".join(lines[start:end])

            # 支持字符串路由、常量路由和带 arguments 的 composable 声明。
            for match in re.finditer(r'\bcomposable\s*\(([\s\S]{0,800}?)\)\s*\{([\s\S]{0,1600}?)\n\s*\}', content):
                declaration, block = match.groups()
                route_match = re.search(
                    r'(?:route\s*=\s*)?(?:"([^"]+)"|([A-Za-z_]\w*(?:\.\w+)*))',
                    declaration,
                )
                screen_match = re.search(r'\b([A-Z]\w*(?:Screen|Page))\s*\(', block)
                if route_match and screen_match:
                    routes[screen_match.group(1)] = route_match.group(1) or route_match.group(2)

    if not registry:
        return []

    page_names = {
        name for name in registry
        if re.search(r"(?:Screen|Page)$", name)
        and not name.lower().startswith(("preview", "test"))
    }

    def component_children(name, page_name, visited, depth=0):
        if name in visited or depth > 4:
            return []
        visited = visited | {name}
        source_node = registry.get(name) or {}
        own_children = []
        for child in source_node.get("children") or []:
            if str(child.get("name") or "").startswith("🎨 容器整体:"):
                continue
            child_name = str(child.get("name") or "")
            if re.match(
                r"^\[(?:文本|图标|间距|表面|分割线|水平分割线|垂直分割线)\]\s*"
                r"(?:Text|Icon|Spacer|Surface|Divider|HorizontalDivider|VerticalDivider)$",
                child_name,
            ):
                continue
            item = copy.deepcopy(child)
            item["id"] = f"android_{_make_id(page_name)}_{_make_id(name)}_{item.get('id', '')}"
            item["source"] = "compose_static"
            item["confidence"] = 0.82 if "[" in str(item.get("name") or "") else 0.7
            own_children.append(item)

        calls = []
        for called in re.findall(r'\b([A-Za-z_]\w*)\s*\(', bodies.get(name, "")):
            if called in registry and called != name and called not in calls:
                calls.append(called)
        for called in calls:
            # 页面之间的导航关系由页面列表表达，不能把另一个完整页面复制进当前页面。
            if called in page_names:
                continue
            nested = component_children(called, page_name, visited, depth + 1)
            if not nested:
                continue
            called_node = registry[called]
            own_children.append({
                "id": f"android_{_make_id(page_name)}_{_make_id(called)}",
                "name": called_node.get("name") or get_friendly_name(called),
                "description": called_node.get("description") or f"{page_name}中的功能区域",
                "file": called_node.get("file", ""),
                "line_start": called_node.get("line_start", 0),
                "line_end": called_node.get("line_end", 0),
                "source": "compose_call_graph",
                "confidence": 0.86,
                "children": nested,
            })
        return own_children

    pages = []
    for name in sorted(page_names):
        node = registry[name]
        children = component_children(name, name, set())
        def has_visible_component(items):
            return any(
                child.get("category") in {"交互", "展示"}
                or has_visible_component(child.get("children") or [])
                for child in items
            )
        if not children or not has_visible_component(children):
            continue
        friendly = get_friendly_name(name)
        pages.append({
            "id": f"android_page_{_make_id(name)}",
            "name": f"📱 {friendly}",
            "description": node.get("description") or f"Android 界面: {name}",
            "route": routes.get(name, ""),
            "file": node.get("file", ""),
            "line_start": node.get("line_start", 0),
            "line_end": node.get("line_end", 0),
            "source": "compose_navigation" if name in routes else "compose_screen",
            "confidence": 0.9 if name in routes else 0.82,
            "children": children,
        })
    return pages


def _scan_android_xml_interfaces(project_root):
    """发现传统 Android XML layout，兼容非 Compose 用户项目。"""
    pages = []
    ignored_dirs = {".git", ".gradle", "build", ".idea", "generated"}
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [item for item in dirs if item not in ignored_dirs]
        normalized = root.replace("\\", "/").lower()
        if "/src/main/res/layout" not in normalized:
            continue
        for filename in sorted(files):
            if not filename.endswith(".xml"):
                continue
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, project_root).replace("\\", "/")
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as source:
                    content = source.read()
            except OSError:
                continue
            components = []
            for index, match in enumerate(re.finditer(r"<([A-Za-z_][\w.]*)\b([^>]*)>", content), 1):
                tag, attrs = match.groups()
                short_type = tag.rsplit(".", 1)[-1]
                if short_type in {
                    "LinearLayout", "RelativeLayout", "ConstraintLayout", "FrameLayout",
                    "CoordinatorLayout", "ScrollView", "NestedScrollView", "merge",
                }:
                    continue
                label_match = re.search(
                    r'android:(?:text|hint|contentDescription)\s*=\s*"([^"]+)"',
                    attrs,
                )
                id_match = re.search(r'android:id\s*=\s*"@\+?id/([^"]+)"', attrs)
                label = (label_match.group(1) if label_match else "") or (
                    id_match.group(1).replace("_", " ") if id_match else short_type
                )
                category = "交互" if re.search(
                    r"(Button|EditText|CheckBox|RadioButton|Switch|Spinner|SeekBar|RecyclerView)",
                    short_type,
                    re.IGNORECASE,
                ) else "展示"
                line = content[:match.start()].count("\n") + 1
                components.append({
                    "id": f"android_xml_{_make_id(rel_path)}_{index}",
                    "name": f"[{short_type}] {label}",
                    "file": rel_path,
                    "line_start": line,
                    "line_end": line,
                    "description": f"XML 布局中的 {short_type}",
                    "category": category,
                    "source": "android_xml",
                    "confidence": 0.9 if label_match or id_match else 0.65,
                })
            if components:
                page_name = os.path.splitext(filename)[0].replace("_", " ")
                pages.append({
                    "id": f"android_xml_page_{_make_id(rel_path)}",
                    "name": f"📱 {page_name}",
                    "description": f"Android XML 界面: {rel_path}",
                    "file": rel_path,
                    "source": "android_xml",
                    "confidence": 0.86,
                    "children": components,
                })
    return pages


def _scan_kotlin_other():
    """扫描 Android 客户端的 data/service/navigation 等"""
    base = os.path.join(
        PROJECT_ROOT, _get_app_name(), "app", "src", "main",
        "java", "cc", "aidelink", "app"
    )

    other_dirs = {
        "ui/navigation": "🧭 导航",
        "data/api": "📡 API 层",
        "data/repository": "💾 数据仓库",
        "service": "🔧 后台服务",
        "di": "💉 依赖注入",
    }

    categories = []
    for dir_key, dir_name in other_dirs.items():
        dir_path = os.path.join(base, *dir_key.split('/'))
        if not os.path.isdir(dir_path):
            continue

        nodes = []
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith('.kt'):
                continue
            fpath = os.path.join(dir_path, fname)
            rel_path = os.path.relpath(fpath, PROJECT_ROOT).replace('\\', '/')
            file_nodes = scan_kotlin_file(fpath, rel_path)
            if not file_nodes:
                # 至少把文件作为一个节点
                nodes.append({
                    "id": _make_id(fname.replace('.kt', '')),
                    "name": fname,
                    "file": rel_path,
                    "line_start": 1,
                    "line_end": _count_lines(fpath),
                    "description": "",
                })
            else:
                for n in file_nodes:
                    _enrich_description(n)
                nodes.extend(file_nodes)

        if nodes:
            categories.append({
                "id": _make_id(dir_key),
                "name": dir_name,
                "children": nodes,
            })

    return categories


def _scan_python_server():
    """扫描 PC 服务端 Python 文件"""
    server_dir = BRIDGE_DIR

    # 只扫描核心 Python 文件，忽略一次性脚本和备份
    core_files = [
        "phone_chat_bridge.py",
        "manager.py",
        "manager_app.py",
        "manager_utils.py",
        "manager_process.py",
        "manager_tray.py",
        "task_runtime.py",
        "model_registry.py",
        "free_model_scheduler.py",
        "ide_scanner.py",
        "event_bus.py",
        "context_linker.py",
        "notification_watcher.py",
        "evolution_daemon.py",
        "self_evolution.py",
        "inject_to_ide.py",
        "tray_app.py",
        "mascot_tray.py",
        "call_assistant.py",
        "call_co_workers.py",
    ]

    file_categories = {
        "phone_chat_bridge.py": ("🌉 桥接核心", "主 Flask 应用 - 所有 API 路由"),
        "manager.py": ("🚀 管理器入口", "启动入口，调用 manager_tray"),
        "manager_app.py": ("🌐 Flask 应用", "Flask app 初始化 + Blueprint 注册"),
        "manager_utils.py": ("🔧 共享工具", "配置读写、日志、会话等公共函数"),
        "manager_process.py": ("⚙️ 进程管理", "服务启停、状态监控"),
        "manager_tray.py": ("🖥️ 系统托盘", "托盘图标 + pywebview 桌面窗口"),
        "task_runtime.py": ("📋 任务运行时", "IDE 任务派发与状态管理"),
        "model_registry.py": ("🧠 模型注册", "AI 模型配置与切换"),
        "free_model_scheduler.py": ("📊 调度器", "免费模型调度与负载均衡"),
        "ide_scanner.py": ("🔍 IDE 扫描器", "检测本机已安装的 IDE"),
        "event_bus.py": ("📢 事件总线", "SSE 事件分发"),
        "context_linker.py": ("🔗 上下文链接", "跨 IDE 上下文共享"),
        "notification_watcher.py": ("🔔 通知监听", "IDE 任务完成通知"),
        "evolution_daemon.py": ("🧬 进化守护", "自进化系统守护进程"),
        "self_evolution.py": ("🧬 自进化", "自进化核心逻辑"),
        "inject_to_ide.py": ("💉 IDE 注入", "向 IDE 聊天框注入消息"),
        "tray_app.py": ("🖥️ 托盘应用", "系统托盘图标和菜单"),
        "mascot_tray.py": ("🧚 吉祥物", "桌面宠物/吉祥物程序"),
        "call_assistant.py": ("🤖 Aide 调用", "MiniMax-M3 单次调用"),
        "call_co_workers.py": ("👥 协作团队", "Coder + Reviewer 协同调用"),
    }

    categories = []
    for fname in core_files:
        fpath = os.path.join(server_dir, fname)
        if not os.path.isfile(fpath):
            continue

        rel_path = os.path.relpath(fpath, PROJECT_ROOT).replace('\\', '/')
        nodes = scan_python_file(fpath, rel_path)
        for n in nodes:
            _enrich_description(n)

        cat_name, cat_desc = file_categories.get(fname, (fname, ""))

        category = {
            "id": _make_id(fname.replace('.py', '')),
            "name": cat_name,
            "file": rel_path,
            "description": cat_desc,
        }
        if nodes:
            category["children"] = nodes
        else:
            category["line_start"] = 1
            category["line_end"] = _count_lines(fpath)

        categories.append(category)

    return categories


def _count_lines(filepath):
    """计算文件行数"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _get_web_manager_ui():
    """动态解析 dashboard.html 模板，提取真实页面结构和组件（带二级分类）"""
    import re

    # 优先从 templates/dashboard.html 读取，兼容旧的 manager.py 内嵌 HTML
    html_path = os.path.join(BRIDGE_DIR, "templates", "dashboard.html")
    manager_path = os.path.join(BRIDGE_DIR, "manager.py")
    html = None

    for path in [html_path, manager_path]:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue
        # 尝试从文件中提取 HTML
        html_match = re.search(r'render_template_string\s*\(\s*f?"""(.*?)"""', content, re.DOTALL)
        if not html_match:
            html_match = re.search(r'render_template_string\s*\(\s*"""(.*?)"""', content, re.DOTALL)
        if html_match:
            html = html_match.group(1)
            break
        # 如果文件本身就是 HTML（templates/dashboard.html）
        if "<!DOCTYPE html>" in content[:200]:
            html = content
            break

    if not html:
        return {"id": "web_manager_ui", "name": "🖥️ Web 管理端界面", "children": []}

    # 1. 提取导航项
    nav_pattern = r"switchPage\(['\"](\w+)['\"]\)[^>]*>.*?<span[^>]*>([^<]*)</span><span>([^<]*)</span>"
    nav_items = re.findall(nav_pattern, html, re.DOTALL)
    page_names = {}
    for page_id, icon, label in nav_items:
        page_names[page_id] = f"{icon.strip()} {label.strip()}"

    # 2. 提取每个页面，按 card 分二级分类
    pages = []
    for page_id, page_label in page_names.items():
        page_pattern = rf'id=["\']page-{page_id}["\']'
        page_match = re.search(page_pattern, html)
        if not page_match:
            continue

        start = page_match.start()
        next_page = re.search(r'id=["\']page-(?!' + re.escape(page_id) + r')', html[start + 10:])
        end = start + 10 + (next_page.start() if next_page else min(start + 30000, len(html)))
        page_html = html[start:end]

        # 按 <div class="card"> 切分二级分类
        sections = _split_by_cards(page_html, page_id)

        # 如果没有 card，整页作为一个分类
        if not sections:
            sections = [{"name": page_label, "html": page_html}]

        children = []
        for section in sections:
            section_components = _extract_components(section["html"], page_id)
            if section_components:
                children.append({
                    "id": f"web_{page_id}_{_make_id(section['name'])}",
                    "name": section["name"],
                    "children": section_components,
                })

        pages.append({
            "id": f"web_page_{page_id}",
            "name": page_label,
            "description": f"页面: {page_label}",
            "children": children,
        })

    # 注入 file 字段
    def inject_file_info(node):
        node["file"] = "server/templates/dashboard.html"
        if "children" in node:
            for child in node["children"]:
                inject_file_info(child)

    for page in pages:
        inject_file_info(page)

    return {
        "id": "web_manager_ui",
        "name": "🖥️ Web 管理端界面",
        "icon": "web",
        "children": pages,
    }


def _scan_generic_web_interfaces(project_root, excluded_files=None):
    """扫描任意项目中的 HTML 页面，以用户可见页面和控件组织界面地图。"""
    excluded = {
        os.path.normcase(os.path.normpath(path))
        for path in (excluded_files or [])
    }
    ignored_dirs = {
        ".git", "node_modules", "dist", "build", ".next", "coverage",
        "vendor", "fonts", "ffmpeg", "__pycache__",
    }
    html_files = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for filename in files:
            if filename.lower().endswith((".html", ".htm")):
                filepath = os.path.join(root, filename)
                if os.path.normcase(os.path.normpath(filepath)) not in excluded:
                    html_files.append(filepath)
            if len(html_files) >= 100:
                break
        if len(html_files) >= 100:
            break

    pages = []
    for filepath in sorted(html_files):
        try:
            if os.path.getsize(filepath) > 2 * 1024 * 1024:
                continue
            with open(filepath, "r", encoding="utf-8", errors="replace") as source:
                html = source.read()
        except OSError:
            continue
        rel_path = os.path.relpath(filepath, project_root).replace("\\", "/")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
        raw_title = (title_match or h1_match)
        page_name = re.sub(r"<[^>]+>", "", raw_title.group(1)).strip() if raw_title else ""
        page_name = page_name or os.path.splitext(os.path.basename(filepath))[0]

        components = []
        patterns = [
            ("交互", "按钮", r"<button\b[^>]*>(.*?)</button>"),
            ("交互", "链接", r"<a\b[^>]*>(.*?)</a>"),
            ("展示", "标题", r"<h[1-4]\b[^>]*>(.*?)</h[1-4]>"),
        ]
        for category, kind, pattern in patterns:
            for index, match in enumerate(re.finditer(pattern, html, re.I | re.S)):
                label = re.sub(r"<[^>]+>", " ", match.group(1))
                label = re.sub(r"\s+", " ", label).strip()
                if not label or len(label) > 80:
                    continue
                line = html.count("\n", 0, match.start()) + 1
                components.append({
                    "id": f"web_{_make_id(rel_path)}_{kind}_{line}_{index}",
                    "name": f"[{kind}] {label}",
                    "file": rel_path,
                    "line_start": line,
                    "line_end": line,
                    "description": f"{page_name}中的{kind}",
                    "category": category,
                })

        form_pattern = re.compile(r"<(input|textarea|select)\b([^>]*)>", re.I | re.S)
        for index, match in enumerate(form_pattern.finditer(html)):
            attrs = match.group(2)
            input_type = re.search(r'type=["\']?([^"\'\s>]+)', attrs, re.I)
            if input_type and input_type.group(1).lower() in {"hidden", "submit", "image"}:
                continue
            label_match = re.search(r'(?:placeholder|aria-label|title|name|id)=["\']([^"\']+)', attrs, re.I)
            label = label_match.group(1).strip() if label_match else match.group(1).lower()
            line = html.count("\n", 0, match.start()) + 1
            components.append({
                "id": f"web_{_make_id(rel_path)}_field_{line}_{index}",
                "name": f"[输入] {label}",
                "file": rel_path,
                "line_start": line,
                "line_end": line,
                "description": f"{page_name}中的输入控件",
                "category": "交互",
            })

        if components:
            pages.append({
                "id": f"web_page_{_make_id(rel_path)}",
                "name": f"🌐 {page_name}",
                "description": f"页面文件: {rel_path}",
                "file": rel_path,
                "children": components[:400],
            })
    return pages


def _scan_python_desktop_interfaces(project_root):
    """从任意 Python Tkinter/CustomTkinter 项目发现桌面界面和可交互控件。"""
    ignored_dirs = {
        ".git", ".venv", "venv", "__pycache__", "site-packages",
        "build", "dist", "node_modules",
    }
    widget_types = {
        "Button": ("按钮", "交互"),
        "Entry": ("输入框", "交互"),
        "Text": ("文本域", "交互"),
        "Checkbutton": ("复选框", "交互"),
        "Radiobutton": ("单选按钮", "交互"),
        "Combobox": ("下拉框", "交互"),
        "Listbox": ("列表", "交互"),
        "Menu": ("菜单", "交互"),
        "Notebook": ("标签页", "交互"),
        "Label": ("文本", "展示"),
        "Canvas": ("画布", "展示"),
        "Frame": ("区域", "布局"),
        "Toplevel": ("弹窗", "交互"),
        "create_text": ("文本", "展示"),
        "create_image": ("图标", "展示"),
    }
    page_labels = {
        "create": "创建任务",
        "manage": "任务管理",
        "tools": "工具",
        "settings": "设置",
        "login": "登录",
        "main": "主界面",
    }

    def call_name(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""

    def literal_keyword(call, keyword):
        for item in call.keywords:
            if item.arg == keyword and isinstance(item.value, ast.Constant):
                return str(item.value.value or "").strip()
        return ""

    def page_and_area(owner_name):
        lowered = owner_name.lower()
        if "prompt" in lowered or "create_tab" in lowered:
            page = "创建任务"
        elif any(key in lowered for key in ("task_tab", "task_card", "group_header", "manage")):
            page = "任务管理"
        elif "tools" in lowered:
            page = "工具"
        elif "setting" in lowered:
            page = "设置"
        elif any(key in lowered for key in ("component_map", "component_locator", "screenshot_dialog")):
            page = "组件定位"
        elif lowered in {"build_ui", "_build_ui", "create_ui", "_create_ui"}:
            page = "主界面"
        elif any(key in lowered for key in ("dialog", "popup", "picker")):
            page = owner_name.strip("_").replace("_", " ")
        else:
            return None, None
        area_rules = (
            ("prompt_builder", "智能提示词"),
            ("create_tab", "待派发任务"),
            ("task_card", "任务卡片"),
            ("task_tab", "任务分组"),
            ("group_header", "分组标题"),
            ("component_map", "地图选择"),
            ("component_locator", "组件定位"),
            ("screenshot", "截图识别"),
            ("quota", "额度状态"),
            ("build_ui", "窗口框架"),
        )
        area = next((label for key, label in area_rules if key in lowered), None)
        return page, area or owner_name.strip("_").replace("_", " ")

    pages = {}
    file_count = 0
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for filename in files:
            if not filename.endswith(".py"):
                continue
            filepath = os.path.join(root, filename)
            try:
                if os.path.getsize(filepath) > 2 * 1024 * 1024:
                    continue
                with open(filepath, "r", encoding="utf-8", errors="replace") as source:
                    content = source.read()
                if not any(marker in content for marker in ("tkinter", "customtkinter", "tk.", "ttk.")):
                    continue
                tree = ast.parse(content, filename=filepath)
            except (OSError, SyntaxError):
                continue
            rel_path = os.path.relpath(filepath, project_root).replace("\\", "/")
            file_count += 1
            for owner in ast.walk(tree):
                if not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                page_name, area_name = page_and_area(owner.name)
                if not page_name:
                    continue
                page = pages.setdefault(page_name, {
                    "id": f"windows_page_{_make_id(page_name)}",
                    "name": f"🪟 {page_name}",
                    "description": f"Python 桌面界面: {page_name}",
                    "file": rel_path,
                    "children": [],
                })
                area = next(
                    (child for child in page["children"] if child.get("area_key") == owner.name),
                    None,
                )
                if area is None:
                    area = {
                        "id": f"windows_area_{_make_id(rel_path)}_{_make_id(owner.name)}",
                        "name": area_name,
                        "description": f"{page_name}中的{area_name}区域",
                        "file": rel_path,
                        "line_start": owner.lineno,
                        "line_end": getattr(owner, "end_lineno", owner.lineno),
                        "source": "tkinter_function",
                        "confidence": 0.84,
                        "area_key": owner.name,
                        "children": [],
                    }
                    page["children"].append(area)
                seen = {child["id"] for child in area["children"]}
                for node in ast.walk(owner):
                    if not isinstance(node, ast.Call):
                        continue
                    raw_type = call_name(node.func)
                    widget_type = next(
                        (
                            name for name in widget_types
                            if raw_type == name
                            or (name[:1].isupper() and raw_type.endswith(name))
                        ),
                        None,
                    )
                    if not widget_type and raw_type.lower().endswith("button"):
                        widget_type = "Button"
                    if not widget_type:
                        continue
                    kind, category = widget_types[widget_type]
                    positional_label = ""
                    if widget_type == "Button":
                        positional_label = next(
                            (
                                str(arg.value).strip()
                                for arg in node.args[1:3]
                                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                            ),
                            "",
                        )
                    label = (
                        literal_keyword(node, "text")
                        or literal_keyword(node, "placeholder_text")
                        or literal_keyword(node, "name")
                        or positional_label
                        or widget_type
                    )
                    node_id = f"windows_{_make_id(rel_path)}_{_make_id(owner.name)}_{node.lineno}_{widget_type.lower()}"
                    if node_id in seen:
                        continue
                    seen.add(node_id)
                    area["children"].append({
                        "id": node_id,
                        "name": f"[{kind}] {label}",
                        "file": rel_path,
                        "line_start": node.lineno,
                        "line_end": getattr(node, "end_lineno", node.lineno),
                        "description": f"{page_name}中的{kind}",
                        "category": category,
                        "source": "static_scan",
                        "confidence": 0.78 if label != widget_type else 0.55,
                    })
            if file_count >= 200:
                break
        if file_count >= 200:
            break
    for page in pages.values():
        page["children"] = [area for area in page["children"] if area.get("children")]
        for area in page["children"]:
            area.pop("area_key", None)
    return [page for page in pages.values() if page["children"]]


def _split_by_cards(page_html, page_id):
    """按 <div class="card"> 切分页面为多个 section"""
    import re
    sections = []
    # 找所有 card 的起始位置
    card_starts = [(m.start(), m.end()) for m in re.finditer(r'<div\s+class=["\']card["\']', page_html)]

    if not card_starts:
        return []

    for i, (cs, ce) in enumerate(card_starts):
        # 提取 card-title 作为 section 名
        card_content = page_html[cs:card_starts[i+1][0] if i+1 < len(card_starts) else len(page_html)]
        title_match = re.search(r'class=["\']card-title["\'][^>]*>.*?<span[^>]*>([^<]+)</span>', card_content, re.DOTALL)
        if not title_match:
            title_match = re.search(r'class=["\']card-title["\'][^>]*>([^<]+)<', card_content)
        section_name = title_match.group(1).strip() if title_match else f"区域 {i+1}"

        # 截到下一个 card 或结束
        next_cs = card_starts[i+1][0] if i+1 < len(card_starts) else len(page_html)
        sections.append({
            "name": section_name,
            "html": page_html[cs:next_cs],
        })

    return sections


def _extract_components(section_html, page_id):
    """从一个 section HTML 中提取所有组件"""
    import re
    components = []

    # 按钮
    btn_pattern = r'<button[^>]*onclick=["\']([^"\']+)["\'][^>]*>(.*?)</button>'
    for m in re.finditer(btn_pattern, section_html, re.DOTALL):
        action = m.group(1).strip()
        label = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        func_match = re.match(r'(\w+)\s*\(', action)
        func_name = func_match.group(1) if func_match else ''
        if not func_name:
            func_name = re.sub(r'[^a-z0-9]', '_', action.split('(')[0].lower()).strip('_')
        if label and len(label) < 60:
            components.append({
                "id": f"web_{page_id}_{func_name}",
                "name": f"按钮: {label}",
                "description": f"触发 {action[:60]}",
            })

    # 输入框（过滤空的）
    inp_pattern = r'<input[^>]*(?:type=["\']([^"\']*)["\'])?[^>]*(?:id=["\']([^"\']*)["\'])?[^>]*(?:placeholder=["\']([^"\']*)["\'])?'
    for m in re.finditer(inp_pattern, section_html):
        inp_type = m.group(1) or 'text'
        inp_id = m.group(2) or ''
        placeholder = m.group(3) or ''
        # 跳过 hidden/submit/checkbox 等非文本输入
        if inp_type in ('hidden', 'submit', 'checkbox', 'radio', 'file', 'image'):
            continue
        # 跳过没有 id 且没有 placeholder 的
        if not inp_id and not placeholder:
            continue
        label = inp_id or placeholder
        components.append({
            "id": f"web_{page_id}_{_make_id(label)}",
            "name": f"输入框: {label}",
            "description": "",
        })

    # 下拉框
    select_pattern = r'<select[^>]*(?:id=["\']([^"\']*)["\'])?[^>]*>.*?</select>'
    for m in re.finditer(select_pattern, section_html, re.DOTALL):
        sel_id = m.group(1) or ''
        first_opt = re.search(r'<option[^>]*>([^<]+)', m.group(0))
        hint = first_opt.group(1).strip() if first_opt else ''
        label = sel_id or hint
        if not label:
            continue
        components.append({
            "id": f"web_{page_id}_{_make_id(label)}",
            "name": f"下拉框: {label}",
            "description": "",
        })

    # 文本域
    textarea_pattern = r'<textarea[^>]*(?:id=["\']([^"\']*)["\'])?[^>]*(?:placeholder=["\']([^"\']*)["\'])?'
    for m in re.finditer(textarea_pattern, section_html):
        tid = m.group(1) or ''
        placeholder = m.group(2) or ''
        label = tid or placeholder
        if not label:
            continue
        components.append({
            "id": f"web_{page_id}_{_make_id(label)}",
            "name": f"文本域: {label}",
            "description": "",
        })

    # 折叠面板
    details_pattern = r'<details[^>]*>.*?<summary[^>]*>(.*?)</summary>'
    for m in re.finditer(details_pattern, section_html, re.DOTALL):
        summary_text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if summary_text and len(summary_text) < 80:
            components.append({
                "id": f"web_{page_id}_{_make_id(summary_text)}",
                "name": f"折叠面板: {summary_text}",
                "description": "",
            })

    # 表格
    table_pattern = r'<thead[^>]*>(.*?)</thead>'
    for m in re.finditer(table_pattern, section_html, re.DOTALL):
        headers = re.findall(r'<th[^>]*>([^<]+)', m.group(1))
        if headers:
            table_name = " / ".join(h.strip() for h in headers[:4])
            components.append({
                "id": f"web_{page_id}_{_make_id(table_name)}",
                "name": f"表格: {table_name}",
                "description": "",
            })

    # 去重
    seen = set()
    unique = []
    for c in components:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique.append(c)

    return unique


def scan_project(include_runtime=False):
    """
    扫描整个 AideLink 项目，返回项目地图字典。
    """
    # 外部目标项目可能不是 AideLink Android 工程；此时跳过 Android 专用
    # 扫描，避免对不存在的 app/src/main/java/... 路径调用 listdir。
    project_root = _current_root()
    screen_cats = _scan_android_interfaces(project_root) + _scan_android_xml_interfaces(project_root)
    runtime_status = {}
    if include_runtime:
        try:
            from runtime_interface_scanner import scan_android_runtime
            runtime_android, android_status = scan_android_runtime()
            try:
                from android_project import inspect_android_project
                expected_packages = {
                    item.get("application_id")
                    for item in inspect_android_project(project_root).get("modules") or []
                    if item.get("application_id")
                }
            except Exception:
                expected_packages = set()
            active_package = android_status.get("package", "")
            if expected_packages and active_package and active_package not in expected_packages:
                runtime_android = []
                android_status.update({
                    "available": False,
                    "message": f"手机前台应用 {active_package} 不属于当前项目",
                    "expected_packages": sorted(expected_packages),
                })
            screen_cats = runtime_android + screen_cats
            runtime_status["android"] = android_status
        except Exception as exc:
            runtime_status["android"] = {"available": False, "message": str(exc)}

    android_category = {
        "id": "android_app",
        "name": "📱 Android 客户端",
        "icon": "phone_android",
        "children": screen_cats + _learned_pages("android"),
    }

    # PC 服务端
    server_cats = _scan_python_server() if os.path.isdir(os.path.join(project_root, "server")) else []
    server_category = {
        "id": "server",
        "name": "🖥️ PC 服务端",
        "icon": "computer",
        "children": server_cats,
    }

    dashboard_path = os.path.join(project_root, "server", "templates", "dashboard.html")
    if os.path.isfile(dashboard_path):
        web_manager_ui = _get_web_manager_ui()
    else:
        web_manager_ui = {
            "id": "web_manager_ui",
            "name": "🌐 Web 界面",
            "icon": "web",
            "children": [],
        }
    generic_web_pages = _scan_generic_web_interfaces(
        project_root,
        excluded_files=[dashboard_path] if os.path.isfile(dashboard_path) else [],
    )
    if generic_web_pages:
        web_manager_ui["children"].extend(generic_web_pages)
    web_manager_ui["children"].extend(_learned_pages("web"))

    runtime_windows = []
    if include_runtime:
        try:
            from runtime_interface_scanner import scan_windows_runtime
            runtime_windows, windows_status = scan_windows_runtime(project_root)
            runtime_status["windows"] = windows_status
        except Exception as exc:
            runtime_status["windows"] = {"available": False, "message": str(exc)}
    windows_category = {
        "id": "windows_ui",
        "name": "🪟 Windows 桌面界面",
        "icon": "desktop_windows",
        "children": runtime_windows + _scan_python_desktop_interfaces(project_root) + _learned_pages("windows"),
    }

    project_map = {
        "version": 2,
        "scan_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "project_root": project_root.replace("\\", "/"),
        "runtime_status": runtime_status,
        "categories": [android_category, server_category, web_manager_ui, windows_category],
    }

    return project_map


def scan_and_save(include_runtime=False):
    """扫描当前项目并保存到按项目隔离的缓存。"""
    result = scan_project(include_runtime=include_runtime)
    try:
        save_map(result)
        print(f"[OK] 项目地图已保存到 {_cache_file(result.get('project_root'))}")
        total_nodes = _count_nodes(result.get("categories", []))
        print(f"[OK] 共扫描 {total_nodes} 个节点")
    except Exception as e:
        print(f"[ERROR] 保存失败: {e}")
    return result


def load_cached():
    """仅加载当前项目自己的缓存，拒绝返回其它项目的旧地图。"""
    current_root = _current_root()
    data = safe_read_json(_cache_file(current_root), None)
    if data and _normalized_root(data.get("project_root")) == _normalized_root(current_root):
        return data
    return None


def save_map(data):
    """保存地图；供普通扫描和 AI 增强扫描共同使用。"""
    if not data:
        return
    root = data.get("project_root") or _current_root()
    os.makedirs(PROJECT_MAP_CACHE_DIR, exist_ok=True)
    safe_write_json(_cache_file(root), data)


def _count_nodes(categories):
    """递归计算节点总数"""
    count = 0
    for cat in categories:
        count += 1
        if "children" in cat:
            count += _count_nodes(cat["children"])
    return count


def generate_component_map(project_map=None):
    """
    从项目地图生成组件地图：按类型分组，每个组件显示所属页面位置。
    区分 Android 和 Web 端，只包含用户可见的组件。
    """
    if project_map is None:
        project_map = load_cached()
    if not project_map:
        return {
            "android": {"component_types": [], "total": 0},
            "web": {"component_types": [], "total": 0},
            "windows": {"component_types": [], "total": 0},
        }
    
    VISIBLE_CATEGORIES = {"交互", "展示"}
    
    def build_platform_map(categories, platform_name):
        """为单个平台构建组件地图"""
        type_map = {}
        counter = [0]
        
        def walk_node(node, page_name=""):
            if "children" in node:
                current_page = node.get("name", page_name)
                for child in node["children"]:
                    walk_node(child, current_page)
            else:
                category = node.get("category", "")
                name = node.get("name", "")
                
                # 三端统一优先解析新格式 "[类型] 标签"，兼容 Web 旧格式 "类型: 标签"。
                if name.startswith("[") and "]" in name:
                    comp_type = name[1:name.index("]")].strip() or "其他"
                    comp_label = name[name.index("]") + 1:].strip()
                elif platform_name == "Web" and ": " in name:
                    comp_type = name[:name.index(": ")].strip() or "其他"
                    comp_label = name[name.index(": ") + 2:].strip()
                else:
                    comp_type = "其他"
                    comp_label = name

                # Android/Windows 组件必须来自可见分类。
                if platform_name in {"Android", "Windows"}:
                    if category not in VISIBLE_CATEGORIES:
                        return
                else:
                    # Web 组件都视为可见
                    category = "展示"
                
                if comp_type not in type_map:
                    type_map[comp_type] = []
                
                type_map[comp_type].append({
                    "id": node.get("id", ""),
                    "label": comp_label,
                    "file": node.get("file", ""),
                    "line_start": node.get("line_start", 0),
                    "line_end": node.get("line_end", 0),
                    "page": page_name,
                    "description": node.get("description", ""),
                })
                counter[0] += 1
        
        for cat in categories:
            for component in cat.get("children", []):
                walk_node(component)
        
        # 排序
        TYPE_ORDER = {
            "按钮": 1, "文字按钮": 1, "图标按钮": 1, "边框按钮": 1,
            "填充按钮": 1, "悬浮按钮": 1, "小悬浮按钮": 1, "扩展悬浮按钮": 1,
            "输入框": 2, "基础输入框": 2,
            "开关": 3, "复选框": 3, "单选按钮": 3,
            "滑块": 4, "范围滑块": 4,
            "筛选芯片": 5, "辅助芯片": 5, "建议芯片": 5,
            "下拉菜单": 6, "下拉选项": 6, "展开下拉菜单": 6,
            "标签页": 7, "标签栏": 7,
            "导航栏项": 8, "底部导航项": 8,
            "对话框": 9, "基础对话框": 9,
            "模态底部抽屉": 10, "底部抽屉": 10,
            "文本": 20, "富文本": 20,
            "图标": 21, "图片": 22, "异步图片": 22,
            "卡片": 23, "浮起卡片": 23, "边框卡片": 23,
            "加载指示器": 24, "进度条": 24,
            "徽章": 25, "提示": 25,
            "分割线": 26, "水平分割线": 26, "垂直分割线": 26,
            "间距": 27, "画布": 28,
        }
        
        sorted_types = sorted(
            type_map.items(),
            key=lambda x: (TYPE_ORDER.get(x[0], 99), -len(x[1]))
        )
        
        component_types = []
        for comp_type, items in sorted_types:
            page_groups = {}
            for item in items:
                page = item.get("page", "未知页面")
                if page not in page_groups:
                    page_groups[page] = []
                page_groups[page].append(item)
            
            items_sorted = sorted(items, key=lambda x: x.get("label", ""))
            
            component_types.append({
                "type": comp_type,
                "count": len(items),
                "items": items_sorted,
                "page_groups": {page: sorted(grp, key=lambda x: x.get("label", "")) 
                               for page, grp in sorted(page_groups.items())},
            })
        
        return {
            "component_types": component_types,
            "total": counter[0],
        }
    
    # 分别构建 Android 和 Web 的组件地图
    android_cats = [c for c in project_map.get("categories", []) if c.get("id") == "android_app"]
    web_cats = [c for c in project_map.get("categories", []) if c.get("id") == "web_manager_ui"]
    windows_cats = [c for c in project_map.get("categories", []) if c.get("id") == "windows_ui"]
    
    android_map = build_platform_map(android_cats, "Android")
    web_map = build_platform_map(web_cats, "Web")
    windows_map = build_platform_map(windows_cats, "Windows")
    
    return {
        "android": android_map,
        "web": web_map,
        "windows": windows_map,
        "scan_time": project_map.get("scan_time", ""),
    }


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    result = scan_and_save()
    # 打印摘要
    for cat in result.get("categories", []):
        print(f"\n{cat['name']}:")
        for child in cat.get("children", []):
            n_children = len(child.get("children", []))
            suffix = f" ({n_children} 子项)" if n_children else ""
            print(f"  ├── {child['name']}{suffix}")

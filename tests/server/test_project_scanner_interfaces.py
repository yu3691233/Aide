import sys
import tempfile
import unittest
import types
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import project_scanner
import runtime_interface_scanner


class ProjectScannerInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.cache_dir = self.root / "cache"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generic_html_pages_are_exposed_as_real_interfaces(self):
        page = self.root / "tools" / "prompt-generator.html"
        page.parent.mkdir()
        page.write_text(
            """<!doctype html><html><head><title>提示词生成器</title></head>
            <body><h1>智能提示词</h1><input placeholder="描述需求">
            <button>生成提示词</button><a href="history.html">历史记录</a></body></html>""",
            encoding="utf-8",
        )

        pages = project_scanner._scan_generic_web_interfaces(str(self.root))

        self.assertEqual(1, len(pages))
        self.assertIn("提示词生成器", pages[0]["name"])
        names = [node["name"] for node in pages[0]["children"]]
        self.assertIn("[按钮] 生成提示词", names)
        self.assertIn("[输入] 描述需求", names)
        self.assertIn("[链接] 历史记录", names)

    def test_function_end_ignores_default_lambda_braces_in_signature(self):
        lines = [
            "fun DemoScreen(",
            "    onDone: () -> Unit = {},",
            ") {",
            "    Button(onClick = onDone) { Text(\"完成\") }",
            "}",
        ]

        self.assertEqual(4, project_scanner._find_function_end(lines, 0))

    def test_component_map_classifies_new_web_node_format(self):
        project_map = {
            "categories": [{
                "id": "web_manager_ui",
                "children": [{
                    "id": "page",
                    "name": "🌐 首页",
                    "children": [
                        {"id": "save", "name": "[按钮] 保存", "category": "交互"},
                        {"id": "query", "name": "[输入] 搜索", "category": "交互"},
                    ],
                }],
            }],
        }

        component_map = project_scanner.generate_component_map(project_map)
        types = {item["type"]: item["count"] for item in component_map["web"]["component_types"]}

        self.assertEqual({"按钮": 1, "输入": 1}, types)
        self.assertNotIn("其他", types)

    def test_component_type_map_preserves_page_and_nested_area(self):
        project_map = {
            "categories": [{
                "id": "windows_ui",
                "children": [{
                    "id": "page",
                    "name": "🪟 创建任务",
                    "children": [{
                        "id": "area",
                        "name": "智能提示词",
                        "category": "布局",
                        "children": [{
                            "id": "target",
                            "name": "[按钮] 添加目标",
                            "category": "交互",
                        }],
                    }],
                }],
            }],
        }

        component_map = project_scanner.generate_component_map(project_map)
        item = component_map["windows"]["component_types"][0]["items"][0]

        self.assertEqual("🪟 创建任务", item["page"])
        self.assertEqual("智能提示词", item["area"])

    def test_cache_is_isolated_and_validated_by_current_project(self):
        first = self.root / "first"
        second = self.root / "second"
        first.mkdir()
        second.mkdir()
        with patch.object(project_scanner, "PROJECT_MAP_CACHE_DIR", str(self.cache_dir)):
            with patch.object(project_scanner, "get_project_root", return_value=first):
                project_scanner.save_map({"project_root": str(first), "categories": []})
                self.assertIsNotNone(project_scanner.load_cached())
            with patch.object(project_scanner, "get_project_root", return_value=second):
                self.assertIsNone(project_scanner.load_cached())

    def test_generic_compose_screen_discovery_does_not_require_aidelink_package(self):
        screen = self.root / "mobile" / "src" / "main" / "kotlin" / "demo" / "ui" / "HomeScreen.kt"
        screen.parent.mkdir(parents=True)
        screen.write_text(
            """package demo.ui
            @Composable
            fun HomeScreen() {
                Column {
                    Text("首页")
                    Button(onClick = {}) { Text("开始") }
                }
            }""",
            encoding="utf-8",
        )

        groups = project_scanner._scan_kotlin_screens_generic(str(self.root))

        self.assertEqual(1, len(groups))
        self.assertTrue(groups[0]["children"])
        self.assertEqual("HomeScreen", groups[0]["children"][0]["composable"])

    def test_python_desktop_scanner_discovers_tkinter_pages_and_controls(self):
        app_file = self.root / "desktop_app.py"
        app_file.write_text(
            """import tkinter as tk
class App:
    def _render_create_tab(self):
        panel = tk.Frame(self.root)
        tk.Label(panel, text="智能提示词")
        tk.Entry(panel)
        tk.Button(panel, text="生成提示词", command=self.generate)
    def _render_tools_tab(self):
        self._rounded_button(self.root, "组件定位", self.locate)
""",
            encoding="utf-8",
        )

        pages = project_scanner._scan_python_desktop_interfaces(str(self.root))

        self.assertEqual(2, len(pages))
        create_page = next(page for page in pages if "创建任务" in page["name"])
        tools_page = next(page for page in pages if "工具" in page["name"])
        names = [
            item["name"]
            for area in create_page["children"]
            for item in area["children"]
        ]
        self.assertIn("[按钮] 生成提示词", names)
        self.assertIn("[输入框] Entry", names)
        tool_names = [
            item["name"]
            for area in tools_page["children"]
            for item in area["children"]
        ]
        self.assertIn("[按钮] 组件定位", tool_names)

    def test_component_locator_dialog_is_grouped_under_tools(self):
        app_file = self.root / "desktop_app.py"
        app_file.write_text(
            """import tkinter as tk
class App:
    def _show_component_map_picker(self):
        tk.Button(self.root, text="选择组件")
""",
            encoding="utf-8",
        )

        pages = project_scanner._scan_python_desktop_interfaces(str(self.root))

        self.assertEqual(["🪟 工具"], [page["name"] for page in pages])
        self.assertIn(
            "[按钮] 选择组件",
            pages[0]["children"][0]["children"][0]["name"],
        )

    def test_tools_tuple_buttons_keep_visible_labels(self):
        app_file = self.root / "desktop_app.py"
        app_file.write_text(
            """import tkinter as tk
class App:
    def _render_tools_tab(self):
        tools = (
            ("快捷回复", "more", self.reply),
            ("组件定位", "globe", self.locate),
            ("设置", "settings", self.settings),
        )
        for label, icon, command in tools:
            self._rounded_button(self.root, label, command)
""",
            encoding="utf-8",
        )

        pages = project_scanner._scan_python_desktop_interfaces(str(self.root))
        names = [
            item["name"]
            for area in pages[0]["children"]
            for item in area["children"]
        ]

        self.assertIn("[按钮] 组件定位", names)

    def test_android_compose_scanner_builds_pages_from_call_graph(self):
        screen = self.root / "app" / "src" / "main" / "kotlin" / "demo" / "MainScreen.kt"
        screen.parent.mkdir(parents=True)
        screen.write_text(
            """@Composable
fun MainScreen() {
    Header()
    Button(onClick = {}) { Text("保存") }
}
@Composable
fun SettingsScreen() {
    Text("设置")
}
@Composable
fun Header() {
    Text("标题")
}
""",
            encoding="utf-8",
        )

        pages = project_scanner._scan_android_interfaces(str(self.root))

        self.assertEqual(["MainScreen", "SettingsScreen"], [
            page["name"].removeprefix("📱 ") for page in pages
        ])
        main = pages[0]
        self.assertTrue(any(child.get("name") == "Header" for child in main["children"]))
        self.assertFalse(any(child.get("name") == "SettingsScreen" for child in main["children"]))

    def test_android_interface_scan_follows_set_content_and_ignores_legacy_screen(self):
        source_root = self.root / "app" / "src" / "main" / "kotlin" / "demo"
        source_root.mkdir(parents=True)
        (source_root / "MainActivity.kt").write_text(
            """class MainActivity {
    fun onCreate() {
        setContent { ActiveScreen(onDone = {}) }
    }
}
""",
            encoding="utf-8",
        )
        (source_root / "Screens.kt").write_text(
            """@Composable
fun ActiveScreen(onDone: () -> Unit = {}) {
    Button(onClick = onDone) { Text("保存") }
}
@Composable
fun LegacyScreen() {
    Button(onClick = {}) { Text("旧页面") }
}
""",
            encoding="utf-8",
        )

        pages = project_scanner._scan_android_interfaces(str(self.root))

        self.assertEqual(["ActiveScreen"], [
            page["name"].removeprefix("📱 ") for page in pages
        ])
        self.assertTrue(any(
            "保存" in str(component.get("name") or "")
            for component in pages[0]["children"]
        ))

    def test_android_xml_layout_is_available_as_interface(self):
        layout = self.root / "app" / "src" / "main" / "res" / "layout" / "activity_login.xml"
        layout.parent.mkdir(parents=True)
        layout.write_text(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
            <EditText android:id="@+id/account" android:hint="账号" />
            <Button android:id="@+id/login" android:text="登录" />
            </LinearLayout>""",
            encoding="utf-8",
        )

        pages = project_scanner._scan_android_xml_interfaces(str(self.root))

        self.assertEqual(1, len(pages))
        self.assertEqual(["[EditText] 账号", "[Button] 登录"], [
            item["name"] for item in pages[0]["children"]
        ])

    def test_android_runtime_scanner_uses_uiautomator_attributes(self):
        fake_locator = types.SimpleNamespace(
            ADB_PATH="adb",
            get_interactive_elements=lambda: {
                "ok": True,
                "device": "device-1",
                "elements": [{
                    "text": "保存",
                    "resource_id": "demo:id/save",
                    "content_desc": "",
                    "class_name": "android.widget.Button",
                    "clickable": True,
                    "focusable": True,
                    "scrollable": False,
                    "bounds": [10, 20, 110, 70],
                }],
            },
            _run=lambda *_args, **_kwargs: types.SimpleNamespace(
                stdout="mCurrentFocus=Window{1 u0 demo/.MainActivity}"
            ),
        )
        with patch.dict(sys.modules, {"ui_locator": fake_locator}):
            pages, status = runtime_interface_scanner.scan_android_runtime()

        self.assertTrue(status["available"])
        self.assertEqual("demo", status["package"])
        self.assertEqual("📡 当前运行界面 · MainActivity", pages[0]["name"])
        component = pages[0]["children"][0]
        self.assertEqual("[Button] 保存", component["name"])
        self.assertEqual([10, 20, 110, 70], component["bounds"])
        self.assertEqual("android_uiautomator", component["source"])

    def test_windows_runtime_pages_prioritize_foreground_window(self):
        pages = [
            {"name": "后台窗口", "is_foreground": False},
            {"name": "当前窗口", "is_foreground": True},
        ]

        pages.sort(key=lambda page: (not page.get("is_foreground"), page["name"]))

        self.assertEqual("当前窗口", pages[0]["name"])

    def test_screenshot_learned_component_survives_map_regeneration(self):
        with patch.object(project_scanner, "PROJECT_MAP_CACHE_DIR", str(self.cache_dir)):
            with patch.object(project_scanner, "get_project_root", return_value=self.root):
                learned = project_scanner.add_learned_component(
                    "windows",
                    {
                        "name": "保存按钮",
                        "page": "编辑器",
                        "area": "底部操作区",
                        "bounds": {"selected_box": [10, 20, 30, 40]},
                    },
                )
                pages = project_scanner._learned_pages("windows")

        self.assertTrue(learned["id"].startswith("learned_"))
        self.assertEqual("✨ 编辑器", pages[0]["name"])
        self.assertEqual("[组件] 保存按钮", pages[0]["children"][0]["name"])

    def test_learned_setting_location_is_not_exposed_as_interface_name(self):
        with patch.object(project_scanner, "PROJECT_MAP_CACHE_DIR", str(self.cache_dir)):
            with patch.object(project_scanner, "get_project_root", return_value=self.root):
                project_scanner.add_learned_component(
                    "windows",
                    {"name": "保存按钮", "page": "设置窗口右下角"},
                )
                pages = project_scanner._learned_pages("windows")

        self.assertEqual("✨ 设置", pages[0]["name"])
        self.assertEqual("窗口右下角", pages[0]["children"][0]["area"])


if __name__ == "__main__":
    unittest.main()

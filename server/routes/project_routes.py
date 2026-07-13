import os
import sys
import json
import time
import logging
import threading
from pathlib import Path
from flask import Blueprint, request, jsonify, Response, stream_with_context
from paths import BRIDGE_DIR as BASE_DIR, PROJECT_ROOT

project_bp = Blueprint('project', __name__)

from json_utils import safe_read_json, safe_write_json


# ============================================================
# watchdog 文件监控（避免和本地 watchdog.py 冲突）
# ============================================================

def _import_watchdog():
    """从 site-packages 导入 watchdog，跳过同目录的 watchdog.py"""
    import sys as _sys
    _cwd = os.path.abspath(os.path.dirname(__file__))
    _parent = str(BASE_DIR)
    _removed = []
    for _p in list(_sys.path):
        if os.path.abspath(_p) in (_cwd, _parent):
            _removed.append(_p)
            _sys.path.remove(_p)
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        return Observer, FileSystemEventHandler
    finally:
        for _p in _removed:
            _sys.path.insert(0, _p)


Observer, FileSystemEventHandler = _import_watchdog()


# ============================================================
# Project Map State
# ============================================================

_sse_clients = []
_sse_lock = threading.Lock()

# 监控状态
_file_observer = None
_map_change_events = []  # 最近的变更事件
_map_change_lock = threading.Lock()
WATCH_EXTENSIONS = {'.kt', '.java', '.py', '.xml', '.kts', '.gradle', '.json', '.md'}
_DEBOUNCE_SECONDS = 2.0
_last_scan_time = 0
_watcher_started = False


class _ProjectMapHandler(FileSystemEventHandler):
    def __init__(self):
        self._pending = {}
        self._timer = None

    def _fire_debounced(self):
        global _last_scan_time
        now = time.time()
        with _map_change_lock:
            events = dict(self._pending)
            self._pending.clear()

        if not events:
            return

        # 记录变更事件
        change_list = []
        for path, evt_type in events.items():
            rel = os.path.relpath(path, str(PROJECT_ROOT))
            change_list.append({"path": rel, "type": evt_type})

        with _map_change_lock:
            _map_change_events.clear()
            _map_change_events.extend(change_list)

        # 推送 SSE 通知
        _broadcast_sse({"type": "file_changes", "changes": change_list})

        # 距上次扫描超过 debounce 就自动触发增量扫描
        if now - _last_scan_time > 5:
            _last_scan_time = now
            try:
                import project_scanner
                project_scanner.scan_and_save()
                _broadcast_sse({"type": "map_updated", "message": "项目地图已自动更新"})
            except Exception as e:
                logging.warning(f"Auto scan failed: {e}")

    def _debounce_timer(self):
        self._fire_debounced()

    def on_any_event(self, event):
        if event.is_directory:
            return
        ext = os.path.splitext(event.src_path)[1].lower()
        if ext not in WATCH_EXTENSIONS:
            return

        if event.event_type in ('created', 'modified'):
            evt_type = 'modified'
        elif event.event_type == 'deleted':
            evt_type = 'deleted'
        elif event.event_type == 'moved':
            evt_type = 'modified'
        else:
            return

        with _map_change_lock:
            self._pending[event.src_path] = evt_type

        # 重置 debounce 定时器
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(_DEBOUNCE_SECONDS, self._debounce_timer)
        self._timer.daemon = True
        self._timer.start()


def _broadcast_sse(data):
    """向所有 SSE 客户端推送事件"""
    import json as _json
    msg = f"data: {_json.dumps(data, ensure_ascii=False)}\n\n"
    dead = []
    with _sse_lock:
        for q in _sse_clients:
            try:
                q.append(msg)
            except Exception:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


_last_watched_root = None

def _start_file_watcher():
    """启动/重启文件监控守护线程"""
    global _file_observer, _last_watched_root
    
    from paths import get_project_root
    current_root = str(get_project_root())
    
    # If the observer is already running and watching the correct root, do nothing
    if _file_observer and _file_observer.is_alive() and _last_watched_root == current_root:
        return

    # If it is running but root changed, stop it first
    if _file_observer:
        try:
            _file_observer.stop()
            _file_observer.join(timeout=2)
        except Exception:
            pass
        _file_observer = None

    try:
        handler = _ProjectMapHandler()
        _file_observer = Observer()
        
        watch_dirs = [current_root]
        
        # Also watch BASE_DIR to ensure bridge server file changes are watched
        if os.path.normpath(str(BASE_DIR)) not in [os.path.normpath(d) for d in watch_dirs]:
            watch_dirs.append(str(BASE_DIR))

        for d in watch_dirs:
            if os.path.isdir(d):
                try:
                    _file_observer.schedule(handler, d, recursive=True)
                except Exception as e:
                    logging.warning(f"Failed to watch {d}: {e}")

        _file_observer.daemon = True
        _file_observer.start()
        _last_watched_root = current_root
        logging.info(f"Project file watcher started for root: {current_root}")
    except Exception as e:
        logging.warning(f"Failed to start file watcher: {e}")


def _ai_scan_project():
    """调用 Aide AI 接口，分析源码结构优化项目地图"""
    import project_scanner
    import requests as _req

    # 先做基础扫描
    raw_map = project_scanner.scan_and_save()

    # 获取 API 配置
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    api_base = "https://api.minimax.chat/v1"
    model = "MiniMax-Text-01"

    # 从 config 或 phone_chat_bridge 获取
    if not api_key:
        try:
            from manager_utils import CONFIG_FILE
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
            api_key = config.get("minimax_api_key", "")
            api_base = config.get("minimax_api_base", api_base)
            model = config.get("xiaomengling_model", model)
        except Exception:
            pass
    if not api_key:
        try:
            from config import MINIMAX_API_KEY
            api_key = MINIMAX_API_KEY
        except Exception:
            pass

    if not api_key:
        return raw_map

    # 构造 prompt：让 AI 分析源码目录结构，生成更准确的地图
    map_json = json.dumps(raw_map, ensure_ascii=False, indent=2)[:16000]
    prompt = f"""你是项目结构分析专家。当前自动扫描的项目地图如下：
{map_json}

请分析这个项目的实际结构，返回优化后的 JSON 地图。
规则：
1. 保持 categories 数组结构（必须包含 Android 客户端、PC 服务端、Web 管理端三个分类）
2. 每个 category 有 id, name, children
3. 每个 child 有 id, name, file（如有）, children（子组件）
4. 按功能模块分组，不要平铺
5. 只返回纯 JSON，不要 markdown 代码块"""

    try:
        resp = _req.post(
            f"{api_base}/text/chatcompletion_v2",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=60
        )
        if resp.status_code == 200:
            result = resp.json()
            ai_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            import re
            # 提取 JSON（去掉可能的 markdown 代码块）
            ai_text = re.sub(r'```json\s*', '', ai_text)
            ai_text = re.sub(r'```\s*$', '', ai_text)
            json_match = re.search(r'\{[\s\S]*\}', ai_text)
            if json_match:
                ai_map = json.loads(json_match.group())
                if "categories" in ai_map:
                    raw_map["categories"] = ai_map["categories"]
                raw_map["ai_enhanced"] = True
                project_scanner.save_map(raw_map)
    except Exception as e:
        logging.warning(f"AI scan failed: {e}")

    return raw_map


# ============================================================
# Project Map API
# ============================================================

def _project_map_response(cache, **extra):
    payload = {
        "success": True,
        "ok": True,
        "project_map": cache,
        **(cache or {}),
    }
    payload.update(extra)
    return jsonify(payload)

@project_bp.route("/api/project-map/events")
def api_project_map_events():
    """SSE 端点：实时推送项目地图变更事件"""
    q = []
    with _sse_lock:
        _sse_clients.append(q)

    def generate():
        try:
            yield "data: {\"type\": \"connected\"}\n\n"
            while True:
                if q:
                    msg = q.pop(0)
                    yield msg
                else:
                    time.sleep(0.5)
        except GeneratorExit:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@project_bp.route("/project-map")
@project_bp.route("/api/project-map")
def api_project_map():
    """获取项目结构地图"""
    _start_file_watcher()
    try:
        import project_scanner
        cache = project_scanner.load_cached()
        if not cache:
            cache = project_scanner.scan_and_save()
        return _project_map_response(cache)
    except Exception as e:
        return jsonify({"success": False, "ok": False, "message": f"加载项目地图失败: {e}"})


@project_bp.route("/project-map/scan", methods=["POST"])
@project_bp.route("/api/project-map/scan", methods=["POST"])
def api_project_map_scan():
    """扫描并更新项目地图，支持 AI 增强"""
    data = request.json or {}
    use_ai = data.get("ai", False)
    try:
        if use_ai:
            cache = _ai_scan_project()
        else:
            import project_scanner
            cache = project_scanner.scan_and_save()
        _broadcast_sse({"type": "map_updated", "message": "项目地图已更新"})
        return _project_map_response(cache, ai_enhanced=use_ai)
    except Exception as e:
        return jsonify({"success": False, "ok": False, "message": f"扫描项目地图失败: {e}"})


@project_bp.route("/api/component-map")
def api_component_map():
    """获取组件地图：按类型分组，显示所属页面位置"""
    try:
        import project_scanner
        
        project_map = project_scanner.load_cached()
        if not project_map:
            project_map = project_scanner.scan_and_save()
        
        component_map = project_scanner.generate_component_map(project_map)
        return jsonify({"success": True, "component_map": component_map})
    except Exception as e:
        return jsonify({"success": False, "message": f"生成组件地图失败: {e}"})


@project_bp.route("/api/project-map/collapsed-states", methods=["GET"])
def api_collapsed_states_get():
    """获取项目地图的折叠状态"""
    states_file = BASE_DIR / "state" / "map_collapsed_states.json"
    data = safe_read_json(states_file, default={})
    return jsonify(data)


@project_bp.route("/api/project-map/collapsed-states", methods=["POST"])
def api_collapsed_states_post():
    """更新项目地图的折叠状态"""
    states_file = BASE_DIR / "state" / "map_collapsed_states.json"
    data = request.get_json(force=True) or {}
    try:
        os.makedirs(states_file.parent, exist_ok=True)
        safe_write_json(states_file, data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# ============================================================
# 项目地图搜索 / 代码预览
# ============================================================

def _search_nodes(nodes, q, current_path, results):
    """递归搜索节点树，匹配 name 或 file 字段（大小写不敏感）"""
    if not nodes:
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_name = node.get("name", "")
        new_path = current_path + [node_name]
        name_lower = node_name.lower()
        file_lower = (node.get("file") or "").lower()
        if q in name_lower or q in file_lower:
            results.append({
                "node": node,
                "path": new_path,
            })
        children = node.get("children")
        if children:
            _search_nodes(children, q, new_path, results)


@project_bp.route("/api/project-map/search")
def api_project_map_search():
    """搜索项目地图中的组件节点"""
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"success": False, "message": "缺少搜索关键词 q"})

    try:
        import project_scanner
        cache = project_scanner.load_cached()
        if not cache:
            cache = project_scanner.scan_and_save()
    except Exception as e:
        return jsonify({"success": False, "message": f"加载项目地图失败: {e}"})

    results = []
    categories = cache.get("categories", []) if cache else []
    _search_nodes(categories, q, [], results)

    return jsonify({
        "success": True,
        "query": q,
        "results": results,
    })


@project_bp.route("/api/project-map/code")
def api_project_map_code():
    """预览指定文件的代码片段"""
    file_param = request.args.get("file", "").strip()
    if not file_param:
        return jsonify({"success": False, "message": "缺少 file 参数"}), 400

    # 安全校验：禁止目录穿越
    if ".." in file_param:
        return jsonify({"success": False, "message": "路径包含非法字符 '..'"}), 400

    # 解析真实路径，确保在 PROJECT_ROOT 下
    project_root_real = os.path.realpath(str(PROJECT_ROOT))
    target_path = os.path.realpath(os.path.join(project_root_real, file_param))
    if target_path != project_root_real and not target_path.startswith(project_root_real + os.sep):
        return jsonify({"success": False, "message": "路径越界，禁止访问项目根目录之外的文件"}), 400

    if not os.path.isfile(target_path):
        return jsonify({"success": False, "message": f"文件不存在: {file_param}"}), 404

    # 解析行号参数
    try:
        start = int(request.args.get("start", "1"))
    except ValueError:
        start = 1
    if start < 1:
        start = 1

    try:
        end = int(request.args.get("end", str(start + 99)))
    except ValueError:
        end = start + 99

    # 限制最多 200 行
    if end < start:
        end = start
    if end - start + 1 > 200:
        end = start + 199

    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.read().split("\n")
    except Exception as e:
        return jsonify({"success": False, "message": f"读取文件失败: {e}"}), 500

    total_lines = len(all_lines)
    start_idx = start - 1
    end_idx = end  # slice 不含 end_idx
    sliced = all_lines[start_idx:end_idx]

    lines = []
    for i, content in enumerate(sliced):
        lines.append({
            "num": start + i,
            "content": content,
        })

    actual_end = start + len(lines) - 1 if lines else start

    return jsonify({
        "success": True,
        "file": file_param,
        "start": start,
        "end": actual_end,
        "total_lines": total_lines,
        "lines": lines,
    })


# ============================================================
# 从 phone_chat_bridge.py 迁移的路由（Step 1.4）
# ============================================================

@project_bp.route('/project-map/lock', methods=['POST'])
def lock_project_feature():
    """锁定一个项目功能，生成版本说明文档，更新 AGENTS.md 规则并提交 Git"""
    import re
    import subprocess
    from datetime import datetime
    from json_utils import atomic_write_json
    
    data = request.json or {}
    node_id = data.get("node_id")
    node_name = data.get("node_name", "未命名组件")
    file_path = data.get("file", "")
    symbol = data.get("symbol", "")
    version = data.get("version", "v1.0.0").strip()
    description = data.get("description", "").strip()

    if not node_id:
        return jsonify({"ok": False, "error": "Missing node_id"})

    # 1. 持有并持久化记录到 locked_features.json
    state_dir = os.path.join(BRIDGE_DIR, "state")
    os.makedirs(state_dir, exist_ok=True)
    locked_json_path = os.path.join(state_dir, "locked_features.json")
    
    locked_features = []
    if os.path.exists(locked_json_path):
        data = safe_read_json(locked_json_path, [])
        locked_features = data if isinstance(data, list) else []

    # 避免重复记录，更新或追加
    existing = next((item for item in locked_features if item["node_id"] == node_id), None)
    lock_info = {
        "node_id": node_id,
        "node_name": node_name,
        "file": file_path,
        "symbol": symbol,
        "version": version,
        "description": description,
        "locked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    if existing:
        locked_features.remove(existing)
    locked_features.append(lock_info)

    atomic_write_json(locked_json_path, locked_features)

    # 2. 追加写入 docs/version_features.md 版本说明文档
    docs_dir = os.path.join(os.path.dirname(BRIDGE_DIR), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    version_md_path = os.path.join(docs_dir, "version_features.md")
    
    md_header = "# 🗺️ 已完成功能与版本定义说明书\n\n本文件记录了项目中已锁定保护的各版本核心功能与组件作用说明，防止协同开发被修改破坏。\n\n"
    if not os.path.exists(version_md_path):
        with open(version_md_path, 'w', encoding='utf-8') as f:
            f.write(md_header)

    md_item = f"""
## [{version}] {node_name}
- **锁定代码路径**: `{file_path}`
- **代码符号/函数**: `{symbol}`
- **锁定时间**: `{lock_info["locked_at"]}`
- **详细功能作用说明**:
  > {description}
"""
    with open(version_md_path, 'a', encoding='utf-8') as f:
        f.write(md_item)

    # 3. 动态更新仓库根目录下的 AGENTS.md 规则 (加锁提示)
    agents_md_path = os.path.join(os.path.dirname(BRIDGE_DIR), "AGENTS.md")
    if os.path.exists(agents_md_path):
        try:
            with open(agents_md_path, 'r', encoding='utf-8') as f:
                agents_content = f.read()

            # 寻找或创建 已锁定保护的功能 区域
            lock_header = "## 🔒 已锁定保护的功能 (Lock List)"
            lock_footer = "<!-- LOCK_LIST_END -->"
            
            # 生成锁定的条目列表
            lock_entries = ["\n以下代码区域已锁定，禁止任何 IDE/Agent 对其进行修改或覆盖损坏：\n"]
            for lf in locked_features:
                lock_entries.append(f"- ❌ **禁止修改**：`{lf['file']}` 中的 `{lf['symbol']}` (功能：{lf['node_name']}，锁定于版本 {lf['version']})\n")
            lock_entries.append("\n")
            lock_text = lock_header + "\n" + "".join(lock_entries) + lock_footer

            if lock_header in agents_content:
                # 替换已有区域
                pattern = re.compile(rf"{re.escape(lock_header)}.*?{re.escape(lock_footer)}", re.DOTALL)
                new_agents_content = pattern.sub(lock_text, agents_content)
            else:
                # 插入到安全红线后面
                redline_marker = "### 🔴 3. 不要把运行时产物入版本库"
                if redline_marker in agents_content:
                    idx = agents_content.find(redline_marker)
                    # 寻找该小节结束位置 (下一个二级或三级标题)
                    next_section = agents_content.find("\n##", idx + len(redline_marker))
                    if next_section == -1:
                        next_section = len(agents_content)
                    new_agents_content = agents_content[:next_section] + "\n\n" + lock_text + "\n" + agents_content[next_section:]
                else:
                    new_agents_content = agents_content + "\n\n" + lock_text

            with open(agents_md_path, 'w', encoding='utf-8') as f:
                f.write(new_agents_content)
        except Exception as e:
            print(f"[ERROR] 写入 AGENTS.md 失败: {e}")

    # 4. 执行本地 Git 提交保护与记录
    try:
        # 添加修改的文件到暂存区
        subprocess.run(["git", "add", locked_json_path, version_md_path, agents_md_path], cwd=os.path.dirname(BRIDGE_DIR))
        # 提交 commit
        commit_msg = f"feat(lock): 🔒 锁定功能 [{node_name}] 对应版本 {version}"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=os.path.dirname(BRIDGE_DIR))
    except Exception as e:
        print(f"[ERROR] 执行 Git commit 失败: {e}")

    return jsonify({
        "ok": True,
        "message": f"功能 [{node_name}] 已成功在 {version} 锁定并受保护！",
        "lock_info": lock_info
    })

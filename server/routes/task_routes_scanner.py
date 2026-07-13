import hashlib
import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from paths import BRIDGE_DIR as BASE_DIR
from json_utils import safe_read_json, safe_write_json


logger = logging.getLogger("manager")

# 同一个 bug 签名累计出现这么多次才真正建任务
BUG_REPEAT_THRESHOLD = 5

# 增量扫描：每次扫描到哪个字节偏移，写到 state/scan_state.json
SCAN_STATE_FILE = BASE_DIR / "state" / "bug_scan_state.json"
SIGNATURE_COUNTS_FILE = BASE_DIR / "state" / "bug_signature_counts.json"

# 已见 bug 签名落盘（独立于任务是否被删除）
SEEN_BUG_SIGS_FILE = BASE_DIR / "state" / "seen_bug_signatures.json"

# 已知假阳性的 file 路径前缀或 error_line 子串；任一命中即跳过
_FALSE_POSITIVE_FILE_PREFIXES = (
    "_core.py",       # 安装包内的依赖文件被 traceback 引用时常见
    "_cache.py",
    "site-packages/",
    "dist-packages/",
    "<frozen ",
    "<string>",
)
_FALSE_POSITIVE_ERROR_SUBSTRINGS = (
    "DEBUG",                                # 调试级别
    "return render_template",               # Flask 模板栈底常见无害栈帧
    "test_",                                # pytest/单元测试运行痕迹
    "DeprecationWarning",                   # 弃用警告
    "UserWarning",                          # 普通用户级警告
    "FutureWarning",
    "PendingDeprecationWarning",
    "ResourceWarning",
)
_LOG_LEVEL_REQUIRED = ("ERROR", "CRITICAL", "FATAL")

# 显式以级别 + 空格/] 开头，避免 UserWarning / FutureWarning 等子串误命中
_LEVEL_HEAD_RE = None


def _build_level_head_regex():
    global _LEVEL_HEAD_RE
    import re as _re
    if _LEVEL_HEAD_RE is None:
        _LEVEL_HEAD_RE = _re.compile(
            r"(?:^|[\s\[\|])(" + "|".join(_LOG_LEVEL_REQUIRED) + r")(?=[\s\]\:\|]|$)",
            _re.MULTILINE,
        )
    return _LEVEL_HEAD_RE


def _normalize_error_line(error_line: str) -> str:
    """规范化错误字符串：去掉十六进制地址和数字时间戳，让签名更稳定。"""
    if not error_line:
        return ""
    cleaned = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", error_line)
    cleaned = re.sub(r"\b\d{10,13}\b", "TS", cleaned)
    return cleaned.strip()


def _make_signature(file_path: str, line_num: str, error_line: str) -> str:
    norm_file = file_path.replace("\\", "/").strip()
    norm_err = _normalize_error_line(error_line)
    return f"{norm_file}:{line_num}:{norm_err}"


def _is_false_positive(file_path: str, error_line: str) -> bool:
    norm_file = file_path.replace("\\", "/").lower()
    if any(prefix.lower() in norm_file for prefix in _FALSE_POSITIVE_FILE_PREFIXES):
        return True
    norm_err = (error_line or "").lower()
    return any(token.lower() in norm_err for token in _FALSE_POSITIVE_ERROR_SUBSTRINGS)


def _has_error_level_marker(content: str) -> bool:
    """Traceback 块所在上下文是否带有显式 ERROR/CRITICAL/FATAL 级别日志行。"""
    if not content:
        return False
    regex = _build_level_head_regex()
    return bool(regex.search(content))


def _load_scan_state():
    """读取上次扫描字节偏移；文件不存在或损坏时返回 0。"""
    data = safe_read_json(SCAN_STATE_FILE, default={})
    return int(data.get("last_offset", 0) or 0) if isinstance(data, dict) else 0


def _save_scan_state(offset: int):
    try:
        SCAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        safe_write_json(SCAN_STATE_FILE, {"last_offset": offset}, indent=None)
    except Exception as exc:
        logger.error(f"Failed to save bug scan state: {exc}")


def _load_signature_counts():
    if not SIGNATURE_COUNTS_FILE.exists():
        return {}
    try:
        data = json.loads(SIGNATURE_COUNTS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_signature_counts(counts):
    try:
        SIGNATURE_COUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        safe_write_json(SIGNATURE_COUNTS_FILE, counts, indent=None)
    except Exception as exc:
        logger.error(f"Failed to save signature counts: {exc}")


def _load_seen_signatures():
    if not SEEN_BUG_SIGS_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_BUG_SIGS_FILE.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save_seen_signatures(sigs):
    try:
        SEEN_BUG_SIGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        safe_write_json(SEEN_BUG_SIGS_FILE, sorted(sigs, key=str), indent=None)
    except Exception as exc:
        logger.error(f"Failed to save seen bug signatures: {exc}")


def _parse_tracebacks(content: str):
    """从一段日志文本里解析 (file_path, line_num, func_name, error_line, block) 五元组列表。

    仅返回 ERROR/CRITICAL/FATAL 级别附近的 traceback，并对 file_path / error_line
    做白名单 / 假阳性过滤。
    """
    blocks = content.split("Traceback (most recent call last):")
    if len(blocks) <= 1:
        return []

    results = []
    for idx in range(1, len(blocks)):
        # 当前 traceback 块体（不混入后续 traceback）
        block_body = blocks[idx].split("\n\n", 1)[0]
        # 紧邻的前一段文本（用于判断日志级别）
        prefix = blocks[idx - 1]
        prefix_tail = "\n".join(prefix.splitlines()[-5:])

        if not _has_error_level_marker(prefix_tail):
            continue

        matches = list(re.finditer(r'File "([^"]+)", line (\d+)(?:, in (\w+))?', block_body))
        if not matches:
            continue

        last_match = matches[-1]
        file_path = last_match.group(1).replace("\\", "/")
        line_num = last_match.group(2)
        func_name = last_match.group(3) or "unknown"

        remaining = block_body[last_match.end():].strip()
        error_line = remaining.split("\n")[0] if remaining else "Unknown Error"

        if _is_false_positive(file_path, error_line):
            continue

        results.append((file_path, line_num, func_name, error_line, block_body))
    return results


def scan_logs_for_errors_and_create_tasks(force=False):
    """扫描 logs 并按阈值创建 bug 任务。

    参数:
        force (bool): 强制从文件头开始扫描（用于运维/调试）。

    行为:
        - 仅扫描自上次扫描以来的新增日志内容（增量）。
        - 对每个 traceback 块按 (file, line, normalized_error) 计数。
        - 同一签名出现次数达到 BUG_REPEAT_THRESHOLD 时才建任务。
        - 已建过任务的签名不再重复建。
    """
    from manager_utils import LOG_FILE
    from task_runtime import TaskRuntime

    if not LOG_FILE.exists():
        return {"scanned_bytes": 0, "new_bugs": 0, "skipped": 0}

    last_offset = 0 if force else _load_scan_state()
    try:
        size = LOG_FILE.stat().st_size
        if last_offset > size:
            last_offset = 0
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            f.seek(last_offset)
            new_content = f.read()
        new_offset = size
    except Exception as exc:
        logger.error(f"Failed to read log file for parsing errors: {exc}")
        return {"scanned_bytes": 0, "new_bugs": 0, "skipped": 0}

    if not new_content:
        _save_scan_state(new_offset)
        return {"scanned_bytes": 0, "new_bugs": 0, "skipped": 0}

    parsed = _parse_tracebacks(new_content)
    if not parsed:
        _save_scan_state(new_offset)
        return {"scanned_bytes": len(new_content.encode("utf-8", errors="replace")),
                "new_bugs": 0, "skipped": 0}

    counts = _load_signature_counts()
    seen = _load_seen_signatures()
    runtime = TaskRuntime(BASE_DIR)

    occurrences_by_sig = defaultdict(int)
    sample_block_by_sig = {}
    for file_path, line_num, func_name, error_line, block_body in parsed:
        sig = _make_signature(file_path, line_num, error_line)
        occurrences_by_sig[sig] += 1
        sample_block_by_sig.setdefault(sig, (file_path, line_num, func_name, error_line, block_body))

    new_bugs = 0
    skipped = 0
    for sig, occ in occurrences_by_sig.items():
        prev = counts.get(sig, 0)
        total = prev + occ
        counts[sig] = total

        if sig in seen:
            skipped += 1
            continue

        if total < BUG_REPEAT_THRESHOLD:
            continue

        file_path, line_num, func_name, error_line, block_body = sample_block_by_sig[sig]
        bug_hash = hashlib.md5(sig.encode("utf-8")).hexdigest()[:8]

        message = (
            f"【自动检测到 Bug（重复 {total} 次，已达阈值 {BUG_REPEAT_THRESHOLD}）】\n"
            f"文件: {file_path}\n行号: {line_num}\n函数: {func_name}\n错误: {error_line}"
        )
        runtime.create_task(
            text=message,
            title=f"[Bug] {file_path.split('/')[-1]}:{line_num}",
            source="bug_monitor",
            target_ide=None,
            metadata={
                "bug_signature": bug_hash,
                "bug_signature_raw": sig,
                "bug_occurrences": total,
                "bug_file": file_path,
                "bug_line": line_num,
                "bug_func": func_name,
                "bug_error": error_line,
                "response_preview": block_body.strip()[:200] + "...",
            },
        )

        seen.add(sig)
        new_bugs += 1

    _save_signature_counts(counts)
    _save_seen_signatures(seen)
    _save_scan_state(new_offset)

    return {
        "scanned_bytes": len(new_content.encode("utf-8", errors="replace")),
        "new_bugs": new_bugs,
        "skipped": skipped,
        "total_signatures": len(occurrences_by_sig),
        "threshold": BUG_REPEAT_THRESHOLD,
    }

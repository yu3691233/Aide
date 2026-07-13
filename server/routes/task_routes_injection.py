import logging
import subprocess
import sys
from datetime import datetime

from paths import BRIDGE_DIR as BASE_DIR


logger = logging.getLogger("manager")


def _inject_to_ide(target_ide, message, task_id=""):
    """注入消息到 IDE 窗口。返回 (success: bool, detail: str)"""
    from task_runtime import SUPPORTED_IDES

    if target_ide not in SUPPORTED_IDES:
        return False, f"不支持的 IDE: {target_ide}"

    # Web OpenCode：本机 Web 端，走 HTTP API
    if target_ide == "oc_web":
        try:
            import requests
            from config import load_settings

            _settings = load_settings()
            _port = _settings.get("opencode_web_port", 4096)
            _username = _settings.get("opencode_web_username") or ""
            _password = _settings.get("opencode_web_password") or ""
            _auth = (_username, _password) if _password else None
            oc_url = f"http://127.0.0.1:{_port}"

            resp = requests.post(
                f"{oc_url}/api/prompt",
                json={"message": message, "task_id": task_id},
                auth=_auth,
                timeout=10,
            )

            if resp.status_code == 200:
                return True, f"已提交到 Web OpenCode ({oc_url})"

            return False, f"Web OpenCode 返回错误 ({resp.status_code}): {resp.text[:200]}"

        except Exception as e:
            return False, f"Web OpenCode 请求失败: {e}"

    # 写入 phone_in.txt（供 bridge 监控读取）
    try:
        with open(BASE_DIR / "phone_in.txt", "w", encoding="utf-8") as f:
            f.write(message)
    except Exception:
        pass

    log_file_path = BASE_DIR / "inject.log"
    try:
        log_file = open(str(log_file_path), "a", encoding="utf-8")
        log_file.write(f"\n--- Inject {task_id} to {target_ide} at {datetime.now().isoformat()} ---\n")
        log_file.flush()

        # 通过 stdin 传递消息，避免命令行参数截断/转义问题
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        proc = subprocess.Popen(
            [sys.executable, str(BASE_DIR / "inject_to_ide.py"), target_ide, "--stdin"],
            stdin=subprocess.PIPE,
            stdout=log_file,
            stderr=log_file,
            creationflags=flags,
        )
        try:
            stdout, stderr = proc.communicate(input=message.encode("utf-8"), timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            log_file.write(f"[ERROR] inject_to_ide.py timed out for {task_id}\n")
            log_file.flush()
            return False, f"注入超时（30s），请确认 {target_ide.upper()} 终端窗口已打开"

        if proc.returncode != 0:
            detail = (stderr or stdout or b"").decode("utf-8", errors="replace").strip()
            log_file.write(f"[ERROR] inject_to_ide.py exited {proc.returncode}: {detail}\n")
            log_file.flush()
            return False, f"注入失败（exit={proc.returncode}）: {detail[:200]}"

        log_file.write(f"[OK] inject_to_ide.py succeeded for {task_id}\n")
        log_file.flush()
        return True, "注入成功"
    except Exception as e:
        logger.error(f"Failed to inject: {e}")
        return False, f"注入异常: {e}"

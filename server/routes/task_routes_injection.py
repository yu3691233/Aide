import logging
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
            from config import load_settings
            from opencode_client import send_prompt

            settings = load_settings()
            directory = settings.get("current_project", "") or settings.get("project_dir", "")
            result = send_prompt(message, task_id=task_id, directory=directory, settings=settings)
            return True, f"已提交到 OpenCode 会话 {result['session_id']}"

        except Exception as e:
            return False, f"OpenCode 请求失败: {e}"

    # 写入 phone_in.txt（供 bridge 监控读取）
    try:
        with open(BASE_DIR / "phone_in.txt", "w", encoding="utf-8") as f:
            f.write(message)
    except Exception:
        pass

    try:
        from dispatch_utils import inject_text_to_desktop
        return inject_text_to_desktop(target_ide, message, task_id=task_id)
    except Exception as e:
        logger.error(f"Failed to inject: {e}")
        return False, f"注入异常: {e}"

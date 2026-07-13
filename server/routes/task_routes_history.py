import logging
import threading
import time
from datetime import datetime

from json_utils import safe_read_json, safe_write_json
from paths import BRIDGE_DIR as BASE_DIR


logger = logging.getLogger("manager")
_prompt_history_lock = threading.Lock()


def _save_prompt_history(nodes, category, user_req, candidates):
    """保存提示词生成历史到 state/prompt_history.json，保留最近 20 条"""
    history_file = BASE_DIR / "state" / "prompt_history.json"
    ts = int(time.time())
    entry = {
        "id": f"ph-{ts}",
        "generated_at": datetime.now().isoformat(),
        "nodes": nodes,
        "category": category,
        "user_req": user_req,
        "candidates": candidates,
    }

    with _prompt_history_lock:
        try:
            existing = safe_read_json(history_file, default={"history": []})
            history = existing.get("history", [])
            history.insert(0, entry)
            if len(history) > 20:
                history = history[:20]
            existing["history"] = history
            history_file.parent.mkdir(parents=True, exist_ok=True)
            safe_write_json(history_file, existing)
        except Exception as e:
            logger.warning(f"Failed to save prompt history: {e}")

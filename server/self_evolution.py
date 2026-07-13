"""进化记忆系统：失败记忆、模型健康度、用户反馈学习。"""

import os
import threading
from datetime import datetime
from paths import BRIDGE_DIR
from json_utils import atomic_write_json, safe_read_json


FAILURE_TYPES = {
    "timeout": {"weight": 0.3, "skip_after": 2, "description": "超时"},
    "rate_limit": {"weight": 0.5, "skip_after": 1, "description": "限流"},
    "auth_error": {"weight": 1.0, "skip_after": 999, "description": "鉴权失败"},
    "connection": {"weight": 0.7, "skip_after": 3, "description": "连接失败"},
    "wrong_answer": {"weight": 0.8, "skip_after": 1, "description": "答错"},
    "model_says_no": {"weight": 0.6, "skip_after": 1, "description": "模型回复无法完成"},
    "partial": {"weight": 0.4, "skip_after": 1, "description": "部分完成但不完整"},
    "crash": {"weight": 0.9, "skip_after": 2, "description": "崩溃/异常"},
}


class FailureMemory:
    """记录模型失败次数，支持衰减和跳过判定。"""

    def __init__(self, memory_path=None):
        self.memory_path = str(memory_path or BRIDGE_DIR / "failure_memory.json")
        self._lock = threading.Lock()
        self.memories = {}
        self._load()

    def _fingerprint(self, model_key, task_type, failure_type):
        return f"{model_key}::{task_type}::{failure_type}"

    def _load(self):
        data = safe_read_json(self.memory_path, {})
        self.memories = data if isinstance(data, dict) else {}

    def _save(self):
        atomic_write_json(self.memory_path, self.memories)

    def record_failure(self, model_key, task_type, failure_type, error_msg="", user_text=""):
        """记录一次失败。"""
        fp = self._fingerprint(model_key, task_type, failure_type)
        with self._lock:
            if fp not in self.memories:
                self.memories[fp] = {
                    "model_key": model_key,
                    "task_type": task_type,
                    "failure_type": failure_type,
                    "count": 0,
                    "last_error": "",
                    "last_time": "",
                }
            entry = self.memories[fp]
            entry["count"] = entry.get("count", 0) + 1
            entry["last_error"] = (error_msg or "")[:300]
            entry["last_time"] = datetime.now().isoformat()
        self._save()

    def record_success(self, model_key, task_type="*"):
        """记录成功，衰减相关失败计数。"""
        with self._lock:
            keys_to_clean = []
            for fp, entry in self.memories.items():
                if entry["model_key"] == model_key and entry["task_type"] == task_type:
                    entry["count"] = max(0, entry["count"] - 1)
                    if entry["count"] == 0:
                        keys_to_clean.append(fp)
            for k in keys_to_clean:
                del self.memories[k]
        self._save()

    def should_skip(self, model_key, task_type):
        """判断是否应跳过该模型。"""
        with self._lock:
            for fp, entry in self.memories.items():
                if entry["model_key"] != model_key:
                    continue
                if entry["task_type"] != task_type and entry["task_type"] != "*":
                    continue
                fail_type = FAILURE_TYPES.get(entry["failure_type"], {})
                skip_after = fail_type.get("skip_after", 999)
                if entry["count"] >= skip_after:
                    return True, f"{entry['failure_type']} 失败 {entry['count']} 次（{fail_type.get('description', '')}）"
        return False, ""

    def get_failure_count(self, model_key, task_type):
        """获取指定模型+任务类型的总失败次数。"""
        total = 0
        with self._lock:
            for entry in self.memories.values():
                if entry["model_key"] == model_key:
                    if entry["task_type"] == task_type or entry["task_type"] == "*":
                        total += entry["count"]
        return total

    def get_hot_failures(self, top_n=10):
        """获取失败次数最多的条目。"""
        with self._lock:
            sorted_mems = sorted(
                self.memories.values(),
                key=lambda x: x["count"],
                reverse=True,
            )
            return sorted_mems[:top_n]

    def get_model_health(self, model_key):
        """获取模型健康度（0.0~1.0）。"""
        with self._lock:
            total_failures = 0
            for entry in self.memories.values():
                if entry["model_key"] == model_key:
                    total_failures += entry["count"]
        return max(0.0, 1.0 - (total_failures * 0.05))

    def clear(self):
        """清空所有失败记忆。"""
        with self._lock:
            self.memories = {}
        self._save()


class SelfEvolver:
    """从失败历史中学习，调整模型优先级。"""

    def __init__(self, failure_memory=None, evolution_path=None):
        self.failure_memory = failure_memory or FailureMemory()
        self.evolution_path = str(evolution_path or BRIDGE_DIR / "evolution_state.json")
        self._lock = threading.Lock()
        self.learned_preferences = {}
        self.user_feedback = []
        self._load()

    def _load(self):
        data = safe_read_json(self.evolution_path, {})
        if isinstance(data, dict):
            self.learned_preferences = data.get("learned_preferences", {})
            self.user_feedback = data.get("user_feedback", [])[-50:]

    def _save(self):
        data = {
            "learned_preferences": self.learned_preferences,
            "user_feedback": self.user_feedback[-50:],
            "updated_at": datetime.now().isoformat(),
        }
        atomic_write_json(self.evolution_path, data)

    def evolve_from_history(self):
        """从失败记忆生成偏好调整。"""
        hot_failures = self.failure_memory.get_hot_failures(20)
        new_prefs = {}

        for entry in hot_failures:
            model_key = entry["model_key"]
            task_type = entry["task_type"]
            count = entry["count"]

            if task_type not in new_prefs:
                new_prefs[task_type] = {}

            if count >= 3:
                new_prefs[task_type][model_key] = max(0.0, 1.0 - (count * 0.15))
            elif count >= 1:
                new_prefs[task_type][model_key] = max(0.3, 1.0 - (count * 0.1))
            else:
                new_prefs[task_type][model_key] = 1.0

        with self._lock:
            for task_type, prefs in new_prefs.items():
                if task_type not in self.learned_preferences:
                    self.learned_preferences[task_type] = {}
                self.learned_preferences[task_type].update(prefs)

        self._save()
        return new_prefs

    def get_adjusted_chain(self, task_type, base_chain):
        """根据学习偏好调整模型链排序。"""
        prefs = self.learned_preferences.get(task_type, {})

        def score(model_key):
            return prefs.get(model_key, 1.0)

        viable = [m for m in base_chain if score(m) > 0.1]
        viable.sort(key=score, reverse=True)
        return viable

    def record_user_feedback(self, task_id, model_key, rating, comment=""):
        """记录用户反馈。"""
        with self._lock:
            self.user_feedback.append({
                "task_id": task_id,
                "model_key": model_key,
                "rating": rating,
                "comment": comment,
                "time": datetime.now().isoformat(),
            })

        if rating < 0:
            self.failure_memory.record_failure(
                model_key, "*", "wrong_answer", comment, ""
            )
        elif rating > 0:
            self.failure_memory.record_success(model_key, "*")

        self._save()

    def get_evolution_stats(self):
        """获取进化统计。"""
        return {
            "preferences": dict(self.learned_preferences),
            "feedback_count": len(self.user_feedback),
            "failure_memory_size": len(self.failure_memory.memories),
        }


def reset_evolution():
    """重置进化状态（测试用）。"""
    global _failure_memory, _self_evolver
    if _failure_memory:
        _failure_memory.clear()
    _failure_memory = None
    _self_evolver = None
    state_path = str(BRIDGE_DIR / "evolution_state.json")
    if os.path.exists(state_path):
        try:
            os.remove(state_path)
        except Exception:
            pass


_failure_memory = None
_self_evolver = None


def get_failure_memory():
    global _failure_memory
    if _failure_memory is None:
        _failure_memory = FailureMemory()
    return _failure_memory


def get_self_evolver():
    global _self_evolver
    if _self_evolver is None:
        _self_evolver = SelfEvolver(get_failure_memory())
    return _self_evolver

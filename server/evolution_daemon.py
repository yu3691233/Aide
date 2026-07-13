"""进化守护模块：Workaround 知识库、任务恢复存储、结果质量评分。"""

import os
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from paths import BRIDGE_DIR
from json_utils import atomic_write_json, safe_read_json


class WorkaroundKnowledge:
    """记录问题→解决方案映射，按成功率排序。"""

    def __init__(self, knowledge_path=None):
        self.knowledge_path = str(knowledge_path or BRIDGE_DIR / "workaround_knowledge.json")
        self._lock = threading.Lock()
        self.knowledge = {}
        self._load()

    def _key(self, model_key, task_type):
        return f"{model_key}::{task_type}"

    def _load(self):
        data = safe_read_json(self.knowledge_path, {})
        self.knowledge = data if isinstance(data, dict) else {}

    def _save(self):
        atomic_write_json(self.knowledge_path, self.knowledge)

    def add_workaround(self, model_key, task_type, problem, workaround, worked=True):
        """添加或更新一条 workaround。"""
        key = self._key(model_key, task_type)
        with self._lock:
            if key not in self.knowledge:
                self.knowledge[key] = {
                    "model_key": model_key,
                    "task_type": task_type,
                    "workarounds": [],
                    "created_at": datetime.now().isoformat(),
                }
            entry = self.knowledge[key]

            for w in entry["workarounds"]:
                if w.get("problem") == problem and w.get("workaround") == workaround:
                    if worked:
                        w["success_count"] = w.get("success_count", 0) + 1
                    else:
                        w["fail_count"] = w.get("fail_count", 0) + 1
                    w["last_used"] = datetime.now().isoformat()
                    self._save()
                    return
            entry["workarounds"].append({
                "problem": problem[:200],
                "workaround": workaround[:500],
                "success_count": 1 if worked else 0,
                "fail_count": 0 if worked else 1,
                "first_used": datetime.now().isoformat(),
                "last_used": datetime.now().isoformat(),
            })
        self._save()

    def get_workarounds(self, model_key, task_type):
        """获取指定模型+任务类型的 workaround 列表（按成功率降序）。"""
        key = self._key(model_key, task_type)
        with self._lock:
            entry = self.knowledge.get(key)
            if not entry:
                return []
            workarounds = entry.get("workarounds", [])

            scored = []
            for w in workarounds:
                total = w.get("success_count", 0) + w.get("fail_count", 0)
                success_rate = w.get("success_count", 0) / max(total, 1)
                scored.append((success_rate, total, w))
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            return [w for _, _, w in scored]

    def get_best_workaround(self, model_key, task_type, min_success_rate=0.5):
        """获取最佳 workaround（成功率 >= min_success_rate）。"""
        workarounds = self.get_workarounds(model_key, task_type)
        for w in workarounds:
            total = w.get("success_count", 0) + w.get("fail_count", 0)
            if total >= 2:
                success_rate = w.get("success_count", 0) / total
                if success_rate >= min_success_rate:
                    return w
        return None

    def apply_workaround(self, text, model_key, task_type):
        """将最佳 workaround 注入 prompt。"""
        wa = self.get_best_workaround(model_key, task_type)
        if not wa:
            return text, None
        workaround = wa.get("workaround", "")
        if not workaround:
            return text, None
        augmented = f"[提示: {workaround}]\n\n{text}"
        return augmented, workaround

    def get_all(self):
        """获取全部 workaround 数据。"""
        with self._lock:
            return dict(self.knowledge)

    def clear(self):
        """清空全部 workaround。"""
        with self._lock:
            self.knowledge = {}
        self._save()


class TaskRecoveryStore:
    """持久化任务状态，支持崩溃恢复。"""

    def __init__(self, store_path=None):
        self.store_path = str(store_path or BRIDGE_DIR / "evolution_tasks_recovery.json")
        self._lock = threading.Lock()
        self.tasks = {}
        self._load()

    def _load(self):
        data = safe_read_json(self.store_path, {})
        self.tasks = data if isinstance(data, dict) else {}

    def _save(self):
        atomic_write_json(self.store_path, self.tasks)

    def save_task(self, task_id, task_data):
        """保存任务状态。"""
        with self._lock:
            self.tasks[task_id] = {
                **task_data,
                "time": datetime.now().isoformat(),
            }
        self._save()

    def get_task(self, task_id):
        """获取单个任务。"""
        with self._lock:
            return self.tasks.get(task_id)

    def remove_task(self, task_id):
        """移除任务。"""
        with self._lock:
            self.tasks.pop(task_id, None)
        self._save()

    def cleanup_old(self, max_age_days=7):
        """清理已完成的旧任务。"""
        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0
        with self._lock:
            keys_to_remove = []
            for k, v in self.tasks.items():
                if v.get("status") in ("completed", "failed"):
                    time_str = v.get("time", "")
                    try:
                        t = datetime.fromisoformat(time_str)
                        if t < cutoff:
                            keys_to_remove.append(k)
                    except Exception:
                        pass
            for k in keys_to_remove:
                del self.tasks[k]
                removed += 1
        if removed > 0:
            self._save()
        return removed

    def get_stats(self):
        """获取任务统计。"""
        with self._lock:
            status_counts = defaultdict(int)
            for v in self.tasks.values():
                status_counts[v.get("status", "unknown")] += 1
            return {
                "total": len(self.tasks),
                "by_status": dict(status_counts),
                "oldest_pending": min(
                    (v.get("time") for v in self.tasks.values()
                     if v.get("status") in ("running", "pending")),
                    default=None
                ),
            }


class ResultQualityScorer:
    """评估模型响应质量。"""

    FAILURE_INDICATORS = [
        "无法完成", "做不了", "无法处理", "我没有能力", "我没有办法",
        "建议", "建议您", "请联系", "请咨询",
        "i cannot", "i can't", "i'm unable", "unable to",
        "not able to", "i don't have", "i'm sorry",
        "请尝试", "try a different", "consider using",
    ]

    INCOMPLETE_INDICATORS = [
        "[truncated]", "省略", "...", "后续", "（未完）", "(未完)",
        "to be continued", "tbd", "todo",
    ]

    @classmethod
    def score(cls, response, model_key=""):
        """评估响应质量（0.0~1.0）。"""
        if not response:
            return 0.0

        score = 1.0
        response_lower = response.lower()
        length = len(response)
        words = response_lower.split()

        for kw in cls.FAILURE_INDICATORS:
            if kw in response_lower:
                score -= 0.7
                break

        for kw in cls.INCOMPLETE_INDICATORS:
            if kw in response_lower:
                score -= 0.3
                break

        if length < 5:
            score -= 0.5
        elif length < 20:
            score -= 0.2
        elif length > 50000:
            score -= 0.3

        if len(words) > 50:
            unique = set(words)
            dedup_ratio = len(unique) / len(words)
            if dedup_ratio < 0.3:
                score -= 0.4

        if response.startswith("[API error") or response.startswith("Error:"):
            score -= 0.8

        return max(0.0, min(1.0, round(score, 2)))

    @classmethod
    def is_low_quality(cls, response, threshold=0.3):
        """判断响应是否低质量。"""
        return cls.score(response) < threshold


class EvolutionDaemon:
    """后台守护进程：定期触发进化、清理过期记忆、评估模型健康度。"""

    def __init__(self, interval_seconds=3600):
        self.interval = interval_seconds
        self._running = False
        self._thread = None
        self.stats = {
            "evolve_count": 0,
            "cleanup_count": 0,
            "last_evolve_time": None,
            "last_cleanup_time": None,
        }

    def _run_cycle(self):
        """单次进化周期。"""
        from self_evolution import get_self_evolver
        evolver = get_self_evolver()
        evolver.evolve_from_history()
        self.stats["evolve_count"] += 1
        self.stats["last_evolve_time"] = datetime.now().isoformat()

        store = TaskRecoveryStore()
        removed = store.cleanup_old(max_age_days=7)
        self.stats["cleanup_count"] += removed
        self.stats["last_cleanup_time"] = datetime.now().isoformat()

    def _loop(self):
        while self._running:
            try:
                self._run_cycle()
            except Exception:
                pass
            for _ in range(int(self.interval)):
                if not self._running:
                    break
                import time
                time.sleep(1)

    def start(self):
        """启动守护进程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止守护进程。"""
        self._running = False

    def force_evolve(self):
        """手动触发一次进化。"""
        self._run_cycle()

    def get_stats(self):
        """获取守护进程统计。"""
        return dict(self.stats)


_workaround = None
_task_store = None
_daemon = None


def get_workaround_knowledge():
    global _workaround
    if _workaround is None:
        _workaround = WorkaroundKnowledge()
    return _workaround


def get_task_recovery_store():
    global _task_store
    if _task_store is None:
        _task_store = TaskRecoveryStore()
    return _task_store


def get_evolution_daemon():
    global _daemon
    if _daemon is None:
        _daemon = EvolutionDaemon()
    return _daemon


def reset_all():
    """重置所有进化状态（测试用）。"""
    global _workaround, _task_store, _daemon
    if _daemon:
        _daemon.stop()
    if _workaround:
        _workaround.clear()
    _workaround = None
    _task_store = None
    _daemon = None
    for fname in [
        "workaround_knowledge.json",
        "evolution_tasks_recovery.json",
    ]:
        path = str(BRIDGE_DIR / fname)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

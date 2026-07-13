"""上下文关联器：跨会话关键词提取、相似度匹配、失败聚类。"""

import os
import re
import threading
from datetime import datetime
from paths import BRIDGE_DIR
from json_utils import atomic_write_json, safe_read_json


STOP_WORDS = set([
    "的", "了", "在", "是", "我", "你", "他", "它", "们", "这", "那", "之",
    "与", "和", "或", "而", "且", "但", "以", "于", "就", "没有", "一些",
    "我们", "你们", "他们", "怎么", "为什么", "请问", "能否", "如何",
])


def extract_keywords(text, top_n=8):
    """从文本中提取关键词（中英文混合）。"""
    if not text:
        return []

    text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text)
    tokens = []

    for part in text.split():
        if re.match(r'^[a-zA-Z0-9_]+$', part):
            tokens.append(part.lower())
        else:
            for i in range(len(part)):
                for n in (2, 3):
                    if i + n <= len(part):
                        tokens.append(part[i:i+n])

    keywords = [
        t for t in tokens
        if t not in STOP_WORDS and len(t) >= 2
    ]

    freq = {}
    for k in keywords:
        freq[k] = freq.get(k, 0) + 1

    sorted_kw = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [k for k, _ in sorted_kw[:top_n]]


def jaccard_similarity(set_a, set_b):
    """计算两个集合的 Jaccard 相似度。"""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / max(union, 1)


class ContextLinker:
    """跨会话上下文关联。"""

    def __init__(self, context_path=None):
        self.context_path = str(context_path or BRIDGE_DIR / "task_context.json")
        self._lock = threading.Lock()
        self.contexts = {}
        self._load()

    def _load(self):
        data = safe_read_json(self.context_path, {})
        self.contexts = data.get("contexts", {}) if isinstance(data, dict) else {}

    def _save(self):
        with self._lock:
            sorted_ctx = dict(sorted(
                self.contexts.items(),
                key=lambda x: x[1].get("time", ""),
                reverse=True,
            )[:200])
            data = {
                "contexts": sorted_ctx,
                "updated_at": datetime.now().isoformat(),
            }
        atomic_write_json(self.context_path, data)

    def record_task(self, task_id, message, response="", task_type="", model_used=""):
        """记录一次任务上下文。"""
        if not message:
            return
        keywords = extract_keywords(message)

        response_keywords = extract_keywords(response[:300]) if response else []
        all_keywords = list(set(keywords + response_keywords))[:15]

        with self._lock:
            self.contexts[task_id] = {
                "task_id": task_id,
                "message": message[:500],
                "message_keywords": keywords,
                "response_preview": response[:200] if response else "",
                "all_keywords": all_keywords,
                "task_type": task_type,
                "model_used": model_used,
                "time": datetime.now().isoformat(),
            }
        self._save()

    def find_related(self, message, top_n=5, threshold=0.15):
        """查找与消息相关的上下文。"""
        query_keywords = set(extract_keywords(message))
        if not query_keywords:
            return []

        results = []
        with self._lock:
            for ctx in self.contexts.values():
                ctx_keywords = set(ctx.get("all_keywords", []))
                if not ctx_keywords:
                    continue
                sim = jaccard_similarity(query_keywords, ctx_keywords)
                if sim >= threshold:
                    results.append((sim, ctx))

        results.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "task_id": ctx["task_id"],
                "message_preview": ctx["message"][:80],
                "model_used": ctx.get("model_used", ""),
                "task_type": ctx.get("task_type", ""),
                "time": ctx.get("time", ""),
                "similarity": round(sim, 3),
                "shared_keywords": list(query_keywords & set(ctx.get("message_keywords", []))),
            }
            for sim, ctx in results[:top_n]
        ]

    def get_by_id(self, task_id):
        """按 ID 获取上下文。"""
        with self._lock:
            return self.contexts.get(task_id)

    def get_recent(self, top_n=20):
        """获取最近的上下文。"""
        with self._lock:
            sorted_ctx = sorted(
                self.contexts.values(),
                key=lambda x: x.get("time", ""),
                reverse=True,
            )
            return sorted_ctx[:top_n]

    def get_stats(self):
        """获取统计信息。"""
        with self._lock:
            return {
                "total_contexts": len(self.contexts),
                "by_task_type": self._count_by_field("task_type"),
                "by_model": self._count_by_field("model_used"),
            }

    def _count_by_field(self, field):
        count = {}
        for ctx in self.contexts.values():
            val = ctx.get(field, "unknown")
            count[val] = count.get(val, 0) + 1
        return count

    def clear(self):
        """清空所有上下文。"""
        with self._lock:
            self.contexts = {}
        self._save()


class FailureClusterer:
    """失败模式聚类分析。"""

    def __init__(self, memory_path=None):
        self.memory_path = str(memory_path or BRIDGE_DIR / "failure_clusters.json")
        self._lock = threading.Lock()
        self.clusters = []
        self._load()

    def _load(self):
        data = safe_read_json(self.memory_path, [])
        self.clusters = data if isinstance(data, list) else []

    def _save(self):
        atomic_write_json(self.memory_path, self.clusters)

    def cluster_failures(self, failure_memories):
        """对失败记录进行聚类。"""
        annotated = []
        for entry in failure_memories:
            kws = set()
            kws.add(entry.get("failure_type", ""))
            kws.add(entry.get("task_type", ""))
            err = entry.get("last_error", "")
            if err:
                for kw in extract_keywords(err, top_n=5):
                    kws.add(kw)
            kws.discard("")
            kws.discard("*")
            annotated.append({
                "fingerprint": f"{entry['model_key']}::{entry['task_type']}::{entry['failure_type']}",
                "keywords": kws,
                "entry": entry,
            })

        new_clusters = []
        for ann in annotated:
            placed = False
            for cluster in new_clusters:
                cluster_kws = set(cluster.get("keyword_signature", []))
                sim = jaccard_similarity(ann["keywords"], cluster_kws)
                if sim >= 0.3:
                    cluster["members"].append(ann["fingerprint"])
                    cluster["total_count"] = cluster.get("total_count", 0) + ann["entry"].get("count", 1)
                    merged = list((cluster_kws | ann["keywords"]))[:10]
                    cluster["keyword_signature"] = merged
                    placed = True
                    break
            if not placed:
                new_clusters.append({
                    "cluster_id": f"cluster_{len(new_clusters) + 1}",
                    "keyword_signature": list(ann["keywords"])[:10],
                    "members": [ann["fingerprint"]],
                    "total_count": ann["entry"].get("count", 1),
                    "suggested_workaround": self._suggest_workaround(
                        ann["entry"].get("failure_type", ""),
                        ann["keywords"],
                    ),
                })

        self.clusters = new_clusters
        self._save()
        return new_clusters

    def _suggest_workaround(self, failure_type, keywords):
        """根据失败类型建议 workaround。"""
        suggestions = {
            "timeout": "缩短单请求长度 / 分步处理",
            "rate_limit": "延迟重试 / 降低频率",
            "auth_error": "检查并更新 API key",
            "connection": "检查服务端口 (5000) 和进程状态",
            "wrong_answer": "增加 prompt 上下文，明确输出要求",
            "model_says_no": "拆分任务 / 换用其他模型",
            "partial": "要求模型给出完整答案",
            "crash": "清理输入中的特殊字符 / 简化任务",
        }
        return suggestions.get(failure_type, "检查失败原因后调整 prompt")

    def get_clusters(self):
        """获取所有聚类。"""
        return self.clusters

    def clear(self):
        """清空聚类。"""
        with self._lock:
            self.clusters = []
        self._save()


_context_linker = None
_failure_clusterer = None


def get_context_linker():
    global _context_linker
    if _context_linker is None:
        _context_linker = ContextLinker()
    return _context_linker


def get_failure_clusterer():
    global _failure_clusterer
    if _failure_clusterer is None:
        _failure_clusterer = FailureClusterer()
    return _failure_clusterer

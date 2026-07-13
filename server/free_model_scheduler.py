""

import re
import os
import time
import threading
from json_utils import safe_read_json, safe_write_json
from datetime import datetime



MODEL_REGISTRY = {

    "xiaomengling": {
        "tier": "free",
        "level": 1,
        "cost": 0,
        "provider": "minimax",
        "model_id": "minimax-m3",
        "api_url": "https://api.minimax.chat/v1/chat/completions",
        "api_key": os.environ.get("MINIMAX_API_KEY", ""),
        "caps": ["chat", "qa", "summary", "simple_code", "translate"],
        "description": "Aide MiniMax-M3（免费云端）",
    },

    "oc-free-deepseek": {
        "tier": "free",
        "level": 2,
        "cost": 0,
        "provider": "opencode",
        "model_id": "opencode/deepseek-v4-flash-free",
        "api_url": None,
        "caps": ["code", "file_op", "debug", "refactor", "simple_arch"],
        "description": "OpenCode DeepSeek V4 Flash（免费）",
    },
    "oc-free-mimo": {
        "tier": "free",
        "level": 2,
        "cost": 0,
        "provider": "opencode",
        "model_id": "opencode/mimo-v2.5-free",
        "api_url": None,
        "caps": ["code", "file_op", "debug", "refactor"],
        "description": "OpenCode MiMo V2.5（免费）",
    },
    "oc-free-nemotron": {
        "tier": "free",
        "level": 2,
        "cost": 0,
        "provider": "opencode",
        "model_id": "opencode/nemotron-3-ultra-free",
        "api_url": None,
        "caps": ["code", "qa", "summary", "simple_arch"],
        "description": "OpenCode Nemotron 3 Ultra（免费）",
    },

    "mimo-free-auto": {
        "tier": "free",
        "level": 2,
        "cost": 0,
        "provider": "mimocode",
        "model_id": "mimo-auto",
        "api_url": None,
        "caps": ["code", "file_op", "debug", "refactor", "simple_arch"],
        "description": "MiMoCode MiMo Auto (Free tier)",
    },
    "mimo-free-deepseek": {
        "tier": "free",
        "level": 2,
        "cost": 0,
        "provider": "mimocode",
        "model_id": "deepseek",
        "api_url": None,
        "caps": ["code", "file_op", "debug", "refactor"],
        "description": "MiMoCode DeepSeek (Free tier)",
    },

    "oc-paid": {
        "tier": "paid",
        "level": 3,
        "cost": 1,
        "provider": "opencode",
        "model_id": None,
        "api_url": None,
        "caps": ["complex_code", "architecture", "debug_hard", "full_stack", "security_audit"],
        "description": "OpenCode 默模型（付费）",
    },
    "mimo-paid": {
        "tier": "paid",
        "level": 3,
        "cost": 1,
        "provider": "mimocode",
        "model_id": None,
        "api_url": None,
        "caps": ["complex_code", "architecture", "debug_hard", "full_stack"],
        "description": "MiMoCode 默模型（付费）",
    },

    "trae": {
        "tier": "gui",
        "level": 4,
        "cost": 0,
        "provider": "trae",
        "caps": ["ide_interaction", "ide_code", "ide_debug"],
        "description": "Trae Solo（GUI 注入）",
    },
    "agy": {
        "tier": "gui",
        "level": 4,
        "cost": 0,
        "provider": "antigravity",
        "caps": ["ide_interaction", "ide_code", "ide_debug"],
        "description": "Antigravity（GUI 注入）",
    },
}




TASK_PATTERNS = {
    "time": {
        "keywords": ["现在几点", "当前时间", "现在时间", "几点", "日期", "今天几号", "时间"],
        "complexity": "trivial",
        "level": 0,
        "type": "local",
    },
    "calc": {
        "keywords": [],
        "level": 0,
        "type": "local",
    },
    "system_status": {
        "keywords": ["系统状态", "电脑状态", "运行状态", "服务状态", "cpu", "内存"],
        "complexity": "trivial",
        "level": 0,
        "type": "local",
    },
    "clipboard": {
        "keywords": ["剪贴板", "复制历史", "最近复制"],
        "complexity": "trivial",
        "level": 0,
        "type": "local",
    },
    "help": {
        "keywords": ["Aide 能做什么", "你能做什么", "功能", "help", "帮助"],
        "complexity": "trivial",
        "level": 0,
        "type": "local",
    },

    "chat": {
        "keywords": ["你好", "你是谁", "闲聊", "天气", "新闻", "笑话", "故事"],
        "complexity": "simple",
        "level": 1,
        "type": "chat",
    },
    "translate": {
        "keywords": ["翻译", "translate", "英文", "中文", "改成英文", "翻成"],
        "complexity": "simple",
        "level": 1,
        "type": "translate",
    },
    "summarize": {
        "keywords": ["总结", "摘", "概括", "归纳", "summary"],
        "complexity": "simple",
        "level": 1,
        "type": "summary",
    },
    "explain_simple": {
        "keywords": ["什么意思", "解释一下", "含义", "概念", "原理介绍", "介绍一下"],
        "complexity": "simple",
        "level": 1,
        "type": "explain",
    },

    "code_simple": {
        "keywords": ["写一个", "写个", "生成代码", "代码片段", "函数", "类", "脚本",
                      "python", "javascript", "html", "css", "sql", "json", "yaml",
                      "正则", "regex", "排序", "算法"],
        "complexity": "moderate",
        "level": 2,
        "type": "coding",
    },
    "debug_simple": {
        "keywords": ["报错", "错误", "bug", "调试", "为什么不行", "出错了", "exception",
                      "traceback", "fix this", "修复"],
        "complexity": "moderate",
        "level": 2,
        "type": "debug",
    },
    "refactor": {
        "keywords": ["重构", "优化代码", "改进", "重写", "refactor", "clean code"],
        "complexity": "moderate",
        "level": 2,
        "type": "refactor",
    },
    "file_op": {
        "keywords": ["创建文件", "删除文件", "读取文件", "写入文件", "文件操作",
                      "新建", "保存", "导入", "export"],
        "complexity": "moderate",
        "level": 2,
        "type": "file_op",
    },

    "architecture": {
        "keywords": ["架构", "设模式", "系统架构", "模块划分", "数据库",
                      "api设计", "接口设计", "设计模式", "架构设计"],
        "complexity": "complex",
        "level": 3,
        "type": "architecture",
    },
    "complex_debug": {
        "keywords": ["性能优化", "内存泄漏", "死锁", "并发", "异",
                      "race condition", "crash", "崩溃"],
        "complexity": "complex",
        "level": 3,
        "type": "debug_hard",
    },
    "security": {
        "keywords": ["安全", "漏洞", "加密", "认证", "授权", "xss", "sql注入",
                      "security", "auth"],
        "complexity": "complex",
        "level": 3,
        "type": "security",
    },
    "full_stack": {
        "keywords": ["完整项目", "全栈", "前后端", "部署", "docker", "ci/cd",
                      "数据库", "前后端", "完整系统"],
        "complexity": "complex",
        "level": 3,
        "type": "full_stack",
    },

    "ide_interaction": {
        "keywords": ["在trae", "在antigravity", "在ide", "在编辑器"],
        "complexity": "moderate",
        "level": 4,
        "type": "ide",
    },
}



PATTERNS = [
    (re.compile(r'^\s*[\d\+\-\*/().\s]+\s*=\s*\??\s*$'), "calc"),

    (re.compile(r'^(write|create|make|build|generate)\s+(a\s+)?(function|class|script|program|app|api|module|component)', re.I), "code_simple"),
    (re.compile(r'^(how to|how do i)\s', re.I), "explain_simple"),

    (re.compile(r'^(translate|翻译)\s+(this|以下|这个)', re.I), "translate"),
]


class TaskClassifier:
    """任务分类器 - 返回分类结果"""

    def __init__(self):
        pass

    def classify(self, text):
        return {
            "level": 1,
            "complexity": "simple",
            "type": "chat",
            "matched_keywords": [],
            "needs_code": False,
            "needs_ide": False,
        }


class FreeModelScheduler:
    """免费模型优先调度"""

    def __init__(self, bridge_dir=None):
        from paths import BRIDGE_DIR
        self.bridge_dir = str(bridge_dir or BRIDGE_DIR)
        self.state_file = os.path.join(self.bridge_dir, "scheduler_state.json")
        self.classifier = TaskClassifier()
        self._lock = threading.Lock()


        self.free_model_stats = {}
        self.escalation_history = []
        self.delegated_tasks = {}

        self._load_state()

    def _load_state(self):
        """加载状态"""
        data = safe_read_json(self.state_file, default={})
        self.delegated_tasks = data.get("delegated_tasks", {})
        self.free_model_stats = data.get("free_model_stats", {})
        self.escalation_history = data.get("escalation_history", [])

    def _save_state(self):
        """保存状态"""
        try:
            with self._lock:
                data = {
                    "delegated_tasks": {k: v for k, v in list(self.delegated_tasks.items())[-50:]},
                    "free_model_stats": self.free_model_stats,
                    "escalation_history": self.escalation_history[-20:],
                    "updated_at": datetime.now().isoformat(),
                }
            safe_write_json(self.state_file, data)
        except Exception:
            pass

    def reset_stats(self):
        """重置统计"""
        with self._lock:
            self.free_model_stats = {}
            self.escalation_history = []
            self.delegated_tasks = {}
        self._save_state()

    def get_stats(self):
        """获取统计"""
        with self._lock:
            return {
                "delegated_count": len(self.delegated_tasks),
                "free_model_stats": dict(self.free_model_stats),
                "escalation_count": len(self.escalation_history),
                "recent_escalations": self.escalation_history[-5:],
            }



    def route_message(self, text, image=False):
        """路由消息"""
        classification = self.classifier.classify(text)
        level = classification["level"]
        complexity = classification["complexity"]
        task_type = classification["type"]
        needs_code = classification["needs_code"]


        if level == 0:
            return {
                "action": "local",
                "target": "local",
                "model_key": None,
                "model_id": None,
                "reason": f"本地直接处理（{task_type}）",
                "level": 0,
                "complexity": complexity,
                "task_type": task_type,
                "can_escalate": False,
                "escalate_to": None,
            }


            return {
                "action": "chat",
                "target": "aide",
                "model_key": "xiaomengling",
                "model_id": None,
                "reason": f"简单对话，走免费云模型（{task_type}）",
                "level": 1,
                "complexity": complexity,
                "task_type": task_type,
                "can_escalate": True,
                "escalate_to": "oc-free-deepseek",
            }


        if level == 2:
            target, model_key, model_id = self._select_free_ide_model(classification)
            return {
                "action": "free_ide",
                "target": target,
                "model_key": model_key,
                "model_id": model_id,
                "reason": f"代码/文件任务，优先免费IDE模型（{task_type}）",
                "level": 2,
                "complexity": complexity,
                "task_type": task_type,
                "can_escalate": True,
                "escalate_to": "oc-paid" if target == "oc" else "mimo-paid",
            }


        if level == 3:
            target, model_key, model_id = self._select_free_ide_model(classification)
            return {
                "action": "free_ide",
                "target": target,
                "model_key": model_key,
                "model_id": model_id,
                "reason": f"复杂任务，先尝试免费模型，失败再升级付费（{task_type}）",
                "level": 3,
                "complexity": complexity,
                "task_type": task_type,
                "can_escalate": True,
                "escalate_to": "oc-paid" if target == "oc" else "mimo-paid",
            }


        if level == 4:
            return {
                "action": "gui_inject",
                "target": "agy",
                "model_key": "agy",
                "model_id": None,
                "reason": "GUI IDE 交互",
                "level": 4,
                "complexity": complexity,
                "task_type": task_type,
                "can_escalate": False,
                "escalate_to": None,
            }


        return {
            "action": "chat",
            "target": "aide",
            "model_key": "xiaomengling",
            "model_id": None,
            "reason": "默认到 Aide",
            "level": 1,
            "complexity": complexity,
            "task_type": task_type,
            "can_escalate": True,
            "escalate_to": "oc-free-deepseek",
        }

    def _select_free_ide_model(self, classification):
        """选择免费IDE模型"""
        text = classification.get("matched_keywords", [])
        needs_code = classification.get("needs_code", False)

        candidates = []
        for key, info in MODEL_REGISTRY.items():
            if info["tier"] == "free" and info["level"] == 2:
                stats = self.free_model_stats.get(key, {})
                total = stats.get("success", 0) + stats.get("fail", 0)
                success_rate = stats.get("success", 0) / max(total, 1)
                candidates.append((key, info, success_rate))

        if not candidates:
            return "oc", "oc-free-deepseek", "opencode/deepseek-v4-flash-free"


        candidates.sort(key=lambda x: x[2], reverse=True)

        best_key, best_info, _ = candidates[0]

        if best_info["provider"] == "opencode":
            return "oc", best_key, best_info["model_id"]
        else:
            return "mimo", best_key, best_info["model_id"]

    def record_delegation(self, task_id, target, model_key, status, result_summary=""):
        """记录委派"""
        with self._lock:
            self.delegated_tasks[task_id] = {
                "target": target,
                "model_key": model_key,
                "status": status,
                "result_summary": result_summary,
                "time": datetime.now().isoformat(),
            }


            if model_key not in self.free_model_stats:
                self.free_model_stats[model_key] = {"success": 0, "fail": 0}
            if status == "success":
                self.free_model_stats[model_key]["success"] += 1
            elif status in ("failed", "escalated"):
                self.free_model_stats[model_key]["fail"] += 1

        self._save_state()

    def record_escalation(self, task_id, from_model, to_model, reason):
        """记录升级"""
        with self._lock:
            self.escalation_history.append({
                "task_id": task_id,
                "from": from_model,
                "to": to_model,
                "reason": reason,
                "time": datetime.now().isoformat(),
            })

            self.delegated_tasks[task_id]["status"] = "escalated"
            self.delegated_tasks[task_id]["escalated_to"] = to_model

        self._save_state()

    def check_duplication(self, text, threshold=0.7):
        """检查重复任务"""
        text_simple = re.sub(r'\s+', ' ', text.lower().strip())

        with self._lock:
            for task_id, info in self.delegated_tasks.items():
                if info["status"] in ("pending",):
                    task_text = info.get("text", "")
                    if task_text and (task_text in text_simple or text_simple in task_text):
                        return True, info

        return False, None

    def get_routing_decision(self, text, image=False):
        """获取路由决策"""
        is_dup, existing = self.check_duplication(text)

        if is_dup:
            return {
                "action": "duplicate_wait",
                "target": existing["target"],
                "model_key": existing["model_key"],
                "reason": f"类似任务正在处理（{existing['target']}），等待结果",
                "level": existing.get("level", 2),
                "complexity": "moderate",
                "task_type": "duplicate",
                "can_escalate": False,
                "escalate_to": None,
                "existing_task": existing,
            }, True

        route = self.route_message(text, image)
        return route, False



_scheduler = None


def get_scheduler():
    """获取调度器"""
    global _scheduler
    if _scheduler is None:
        _scheduler = FreeModelScheduler()
    return _scheduler


def reset_scheduler():
    """重置调度器"""
    global _scheduler
    if _scheduler:
        _scheduler.reset_stats()
    _scheduler = FreeModelScheduler()
    return _scheduler

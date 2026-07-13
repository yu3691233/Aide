import json
import logging
from pathlib import Path
from call_assistant import ask_assistant

logger = logging.getLogger('manager')
BASE_DIR = Path(__file__).parent

SYSTEM_PROMPT = """你是一个高效率的任务拆解与分配助理（Task Orchestrator）。
你的目标是把用户的原始任务描述分析，并进行智能分流，以降低主开发 Agent 的 token 消耗与工作量。

请按以下规则执行：
1. 识别任务中是否包含以下可以“委派”给副 IDE（如写测试、写文档、格式化、运行测试）的工作。
2. 如果有，将其拆分为一个主开发任务（Main Task）和一个或多个子测试/文档任务（Sub Tasks）。
3. 在主任务的 Prompt 末尾，强行加入明确的禁令规范（例如：禁止自己编写测试，告知用户这部分已委派别人处理）。
4. 必须输出为 JSON 格式，不要包含任何 markdown 或 think 标签。

JSON 结构示例：
{
  "has_subtasks": true,
  "main_task": {
    "title": "任务核心标题",
    "prompt": "包含禁令的最终提示词内容"
  },
  "sub_tasks": [
    {
      "title": "测试/文档子任务标题",
      "prompt": "子任务描述，提示它需要基于主任务产物来写"
    }
  ]
}
"""

def split_task(user_message):
    """
    使用 Aide 分析并拆解任务
    """
    try:
        res = ask_assistant(user_message, SYSTEM_PROMPT)
        # 去掉可能的 markdown 格式
        clean_res = res.strip()
        if clean_res.startswith("```json"):
            clean_res = clean_res[7:]
        if clean_res.endswith("```"):
            clean_res = clean_res[:-3]
        clean_res = clean_res.strip()
        
        parsed = json.loads(clean_res)
        return parsed
    except Exception as e:
        logger.error(f"Task splitting failed: {e}")
        # 降级兜底：不拆分
        return {
            "has_subtasks": False,
            "main_task": {
                "title": user_message[:30],
                "prompt": user_message
            },
            "sub_tasks": []
        }

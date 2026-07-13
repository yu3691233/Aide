import sys
import os
import json
import io

# 强制 sys.stdout 和 sys.stderr 输出为 utf-8，解决 Windows 下 GBK 编码引发的 UnicodeEncodeError
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 确保能导入同目录下的 call_assistant
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from call_assistant import ask_assistant

def run_co_workers(task_description):
    print("=" * 60)
    print(f"🚀 任务启动: {task_description}")
    print("=" * 60)
    
    # 1. Coder writes initial code
    coder_system = (
        "你是一名优秀的资深软件工程师（Coder Agent）。你的任务是根据用户的需求，编写出结构清晰、"
        "高效且鲁棒的Python代码。请直接给出完整的代码，并附带简短的思路说明。"
    )
    coder_prompt = f"请为以下需求编写Python代码：\n\n{task_description}"
    
    print("\n[🤖 Coder] 正在编写第一版代码...")
    initial_code = ask_assistant(coder_prompt, coder_system)
    print("\n--- [🤖 Coder 第一版输出] ---")
    print(initial_code)
    
    # 2. Reviewer reviews code
    reviewer_system = (
        "你是一名挑剔的代码审计专家（Reviewer Agent）。你的工作是审查Coder编写的代码，寻找潜在的Bug、"
        "性能瓶颈、代码规范问题，并给出具体的修改意见和优化建议。"
    )
    reviewer_prompt = f"请评估并审计以下代码的质量，指出不足之处和修改意见：\n\n{initial_code}"
    
    print("\n[🤖 Reviewer] 正在评估与审查代码...")
    review_comments = ask_assistant(reviewer_prompt, reviewer_system)
    print("\n--- [🤖 Reviewer 审查意见] ---")
    print(review_comments)
    
    # 3. Coder refactors code based on comments
    refactor_system = (
        "你是一名追求完美的重构大师（Coder Refactor Agent）。你需要根据Reviewer的审查意见，"
        "对第一版代码进行修改和重构，直接输出修复且优化后的最终完整代码。"
    )
    refactor_prompt = (
        f"这是第一版代码：\n{initial_code}\n\n"
        f"这是Reviewer的意见：\n{review_comments}\n\n"
        "请根据上述意见，输出修改和重构后的最终完整Python代码。"
    )
    
    print("\n[🤖 Coder] 正在根据审查意见进行重构与修复...")
    final_code = ask_assistant(refactor_prompt, refactor_system)
    print("\n--- [🤖 Coder 最终优化代码] ---")
    print(final_code)
    return final_code

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python call_co_workers.py <task_description>")
        sys.exit(1)
        
    task_desc = sys.argv[1]
    result = run_co_workers(task_desc)
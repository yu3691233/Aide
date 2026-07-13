import sys
import os
import requests
import re

url = "https://api.minimax.chat/v1/chat/completions"

def clean_think_tags(text):
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

def ask_assistant(prompt, system_prompt=None):
    # 优先从 model_registry（模型管理页面）读取，其次环境变量兜底
    api_key = None
    try:
        from model_registry import get_model
        m = get_model("minimax-m3")
        if m:
            api_key = m.get("api_key")
    except Exception:
        pass
    if not api_key:
        api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": "minimax-m3",
        "messages": messages
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            res_json = response.json()
            content = res_json["choices"][0]["message"]["content"]
            return clean_think_tags(content)
        else:
            return f"Error: API returned status code {response.status_code}. Detail: {response.text}"
    except Exception as e:
        return f"Exception during API call: {e}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python call_assistant.py <prompt_text> [system_prompt_text]")
        sys.exit(1)
        
    user_prompt = sys.argv[1]
    sys_prompt = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = ask_assistant(user_prompt, sys_prompt)
    sys.stdout.buffer.write(result.encode('utf-8'))
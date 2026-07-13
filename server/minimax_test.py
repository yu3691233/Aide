import os
import requests
import json

api_key = os.environ.get("MINIMAX_API_KEY", "")
if not api_key:
    print("Error: MINIMAX_API_KEY environment variable not set")
    exit(1)

url = "https://api.minimax.chat/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "model": "abab6.5g-chat",
    "messages": [
        {"role": "user", "content": "你好，请回复'测试成功'"}
    ]
}

try:
    response = requests.post(url, headers=headers, json=payload)
    print("Status Code:", response.status_code)
    print("Response JSON:", json.dumps(response.json(), ensure_ascii=False, indent=2))
except Exception as e:
    print("Error:", e)

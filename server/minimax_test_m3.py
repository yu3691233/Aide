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
    "model": "minimax-m3",
    "messages": [
        {"role": "user", "content": "你好"}
    ]
}

try:
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    with open("m3_res.txt", "w", encoding="utf-8") as f:
        f.write(response.text)
    print("Succeeded writing response to file.")
except Exception as e:
    print("Error:", e)

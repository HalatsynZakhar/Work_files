import requests
import json

API_KEY = ""
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={API_KEY}"

data = {
    "contents": [
        {
            "parts": [
                {"text": "Привет. Ты работаешь?"}
            ]
        }
    ]
}

response = requests.post(URL, headers={"Content-Type": "application/json"}, data=json.dumps(data))

if response.status_code == 200:
    result = response.json()
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    print("Gemini says:", text)
else:
    print("Error:", response.status_code, response.text)

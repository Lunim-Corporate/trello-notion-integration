"""
One-off check: asks Notion which integration a token belongs to.
Usage: python3 check_integration_name.py
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

resp = requests.get(
    "https://api.notion.com/v1/users/me",
    headers={
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": "2026-03-11",
    },
)
data = resp.json()
print("HTTP", resp.status_code)
print("Integration name:", data.get("name"))
print("Bot info:", data.get("bot"))

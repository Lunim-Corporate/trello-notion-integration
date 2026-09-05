"""
Fetches the real name of every data_source object the integration can see
-- the full_diagnostic search found 4 of these but printed '?' for their
titles since data_source objects weren't handled. This checks if any of
them is actually the real Projects/Issues data.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
HEADERS = {
    "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
    "Notion-Version": "2026-03-11",
}

DATA_SOURCE_IDS = [
    "3cf64be3-aa8c-804b-9bde-000bcb5c68f7",
    "d9464be3-aa8c-82bb-aa20-07e3f4dd8c20",
    "06c64be3-aa8c-8393-b5c0-07c54a7be847",
    "3b864be3-aa8c-802b-a2f1-000b518a5c9a",
]

for ds_id in DATA_SOURCE_IDS:
    resp = requests.get(f"https://api.notion.com/v1/data_sources/{ds_id}", headers=HEADERS)
    print(f"\n{ds_id}: HTTP {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        title = "".join(t["plain_text"] for t in data.get("title", [])) or "(no title)"
        props = list(data.get("properties", {}).keys())
        print(f"  Title: {title}")
        print(f"  Properties: {props}")
    else:
        print(f"  {resp.text[:200]}")

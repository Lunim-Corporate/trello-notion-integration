import os
import requests
from dotenv import load_dotenv

load_dotenv()
HEADERS = {
    "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
    "Notion-Version": "2026-03-11",
}

SOURCES = {
    "Issue": "d9464be3-aa8c-82bb-aa20-07e3f4dd8c20",
    "Projects": "06c64be3-aa8c-8393-b5c0-07c54a7be847",
}

for name, ds_id in SOURCES.items():
    resp = requests.get(f"https://api.notion.com/v1/data_sources/{ds_id}", headers=HEADERS)
    data = resp.json()
    print(f"\n{name} ({ds_id}):")
    for prop_name, prop_info in data.get("properties", {}).items():
        print(f"  {prop_name}: {prop_info.get('type')}")

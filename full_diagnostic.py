"""
Full diagnostic: asks the Notion API directly what this integration can see,
bypassing the Notion UI's Connections panel entirely (which we now know is
unreliable to read as a guest).
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["NOTION_TOKEN"]
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2026-03-11",
    "Content-Type": "application/json",
}

KNOWN_IDS = {
    "Projects page (from URL)": "28d64be3-aa8c-8324-88f9-015aa7a480df",
    "Issues page (from URL)": "8aa64be3-aa8c-82f4-910a-0127f7bfe003",
    "Projects database (resolved)": "13b64be3-aa8c-8209-a908-8169c754c868",
    "Issues database (resolved)": "88664be3-aa8c-8296-9dda-013dff72a8e9",
}

print("=" * 60)
print("STEP 1: Who is this integration, and what workspace?")
print("=" * 60)
me = requests.get("https://api.notion.com/v1/users/me", headers=HEADERS).json()
print(f"Name: {me.get('name')} | Workspace: {me.get('bot', {}).get('workspace_name')}")

print()
print("=" * 60)
print("STEP 2: Full search -- everything this integration can currently see")
print("=" * 60)
search = requests.post("https://api.notion.com/v1/search", headers=HEADERS, json={}).json()
results = search.get("results", [])
print(f"Total objects visible to this integration: {len(results)}")
seen_ids = set()
for r in results:
    obj_type = r["object"]
    obj_id = r["id"]
    seen_ids.add(obj_id)
    title = "?"
    if obj_type == "page":
        props = r.get("properties", {})
        title_prop = next((v for v in props.values() if v.get("type") == "title"), None)
        if title_prop:
            title = "".join(t["plain_text"] for t in title_prop.get("title", [])) or "(untitled)"
    elif obj_type == "database":
        title = "".join(t["plain_text"] for t in r.get("title", [])) or "(untitled)"
    print(f"  [{obj_type}] {obj_id}  -- {title}")

print()
print("=" * 60)
print("STEP 3: Do our known ids show up in that search?")
print("=" * 60)
for name, id_ in KNOWN_IDS.items():
    found = id_ in seen_ids
    print(f"  {'FOUND' if found else 'NOT FOUND'}: {name} ({id_})")

print()
print("=" * 60)
print("STEP 4: Raw block-level fetch of each known id (bypasses /databases entirely)")
print("=" * 60)
for name, id_ in KNOWN_IDS.items():
    resp = requests.get(f"https://api.notion.com/v1/blocks/{id_}", headers=HEADERS)
    print(f"\n{name} ({id_}): HTTP {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  type: {data.get('type')}")
        if data.get("type") == "child_database":
            print(f"  child_database.title: {data['child_database'].get('title')}")
    else:
        print(f"  {resp.text[:300]}")

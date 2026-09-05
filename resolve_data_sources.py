"""
Run this once, locally, after filling NOTION_TOKEN into your .env file.

A database's id (the one in its Notion URL) isn't always the same as its
data_source_id -- Notion's API separates a database "container" from its
data source(s). This resolves the real ids so .env has the right values.

Usage:
    python resolve_data_sources.py
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["NOTION_TOKEN"]
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2026-03-11",
}

# Database ids parsed from the URLs Peter sent.
DATABASES = {
    "Projects": "28d64be3-aa8c-8324-88f9-015aa7a480df",
    "Issues": "8aa64be3-aa8c-82f4-910a-0127f7bfe003",
}

def resolve_database_id(id_from_url: str) -> str:
    """The id in a Notion URL is sometimes a page that CONTAINS the database
    as a child block, not the database object itself. Detect that case and
    find the real database id among the page's children."""
    resp = requests.get(f"https://api.notion.com/v1/databases/{id_from_url}", headers=HEADERS)
    if resp.status_code == 200:
        return id_from_url

    is_page_not_database = (
        resp.status_code == 400 and "is a page, not a database" in resp.text
    )
    if not is_page_not_database:
        resp.raise_for_status()

    children_resp = requests.get(
        f"https://api.notion.com/v1/blocks/{id_from_url}/children", headers=HEADERS
    )
    children_resp.raise_for_status()
    child_databases = [
        b["id"] for b in children_resp.json().get("results", []) if b["type"] == "child_database"
    ]
    if not child_databases:
        raise RuntimeError(
            f"{id_from_url} is a page with no child database found in its direct children. "
            "It may be nested deeper, or the integration may not have access to see it."
        )
    if len(child_databases) > 1:
        print(f"  Note: found {len(child_databases)} databases on this page, using the first.")
    return child_databases[0]


if __name__ == "__main__":
    for name, id_from_url in DATABASES.items():
        try:
            database_id = resolve_database_id(id_from_url)
        except requests.HTTPError as e:
            print(f"\n{name}: failed to resolve database id -- {e}")
            continue

        resp = requests.get(f"https://api.notion.com/v1/databases/{database_id}", headers=HEADERS)
        print(f"\n{name} database ({database_id}): HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"  {resp.text}")
            print("  If this is a 404, the integration likely hasn't been shared with this database yet.")
            continue

        data = resp.json()
        data_sources = data.get("data_sources", [])
        if not data_sources:
            print("  No data_sources key found. Raw response keys:", list(data.keys()))
            print("  Full response:", data)
        for ds in data_sources:
            print(f"  -> NOTION_{name.upper()}_DATA_SOURCE_ID = {ds['id']}  (name: {ds.get('name')})")

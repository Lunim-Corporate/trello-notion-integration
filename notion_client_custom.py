import requests

from config import (
    NOTION_API_VERSION,
    NOTION_ISSUES_DATA_SOURCE_ID,
    NOTION_PROJECTS_DATA_SOURCE_ID,
    NOTION_TOKEN,
)

BASE_URL = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_API_VERSION,
    "Content-Type": "application/json",
}


def query_data_source(data_source_id: str, filter_: dict = None) -> list:
    payload = {"filter": filter_} if filter_ else {}
    resp = requests.post(
        f"{BASE_URL}/data_sources/{data_source_id}/query",
        headers=HEADERS,
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()["results"]


def get_projects() -> dict:
    """Returns {project_name: page_id} for every row in the Projects
    database. Used to resolve Trello Project labels to the real Notion
    relation target, since Issues.Project is a relation, not a select.

    Names are stripped of leading/trailing whitespace -- a trailing space in
    a Notion title is invisible in the UI but breaks an exact-string match
    against a Trello label name that doesn't have one (discovered 9 Sep
    2026: "Psychological Profiling " with a trailing space silently failed
    to match the clean "Psychological Profiling" Trello label)."""
    results = query_data_source(NOTION_PROJECTS_DATA_SOURCE_ID)
    projects = {}
    for page in results:
        title = page["properties"].get("Project", {}).get("title", [])
        name = "".join(t["plain_text"] for t in title).strip() if title else None
        if name:
            projects[name] = page["id"]
    return projects


def get_page(page_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/pages/{page_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def create_issue_page(properties: dict) -> dict:
    """Creates a new row in the Issues database specifically -- Trello cards
    only ever create Issues, never Projects."""
    resp = requests.post(
        f"{BASE_URL}/pages",
        headers=HEADERS,
        json={
            "parent": {"data_source_id": NOTION_ISSUES_DATA_SOURCE_ID},
            "properties": properties,
        },
    )
    resp.raise_for_status()
    return resp.json()


def update_page(page_id: str, properties: dict) -> dict:
    resp = requests.patch(
        f"{BASE_URL}/pages/{page_id}",
        headers=HEADERS,
        json={"properties": properties},
    )
    resp.raise_for_status()
    return resp.json()

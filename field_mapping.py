"""
Pure translation functions between Trello card fields and Notion Issue page
properties. No network calls here on purpose -- it's what makes this file
testable without hitting either API.

Schema notes (confirmed via live API check, 6 Sep 2026):
- The Issues database's title property is called "Issue", not "Name".
- Status is Notion's "status" property TYPE, not "select" -- these use
  different API shapes ({"status": {...}} vs {"select": {...}}). Confirmed
  via GET on the real data source.
- "Project" is a RELATION to the Projects database -- every value here is a
  Notion page_id, resolved via a name->page_id map built from
  notion_client_custom.get_projects().
- Assignee (the real property is called "Owner", type people) and
  Description are NOT YET implemented -- gated behind config flags so we
  don't silently write to something unverified.
"""

def trello_to_notion_properties(
    card: dict,
    *,
    list_name: str,
    project_page_ids: list,
    sync_description: bool = False,
) -> dict:
    """Build a Notion 'properties' payload from a Trello card dict (as
    returned by trello_client.get_card) plus the resolved list name and
    Project relation target(s)."""
    properties = {
        "Issue": {"title": [{"text": {"content": card["name"]}}]},
        "Status": {"status": {"name": list_name}} if list_name else {"status": None},
    }

    if card.get("due"):
        properties["Due Date"] = {"date": {"start": card["due"][:10]}}
    else:
        properties["Due Date"] = {"date": None}

    # Relation properties take a list of {"id": page_id} -- a card's Project
    # label(s) resolve to one or more Project page ids. Usually just one.
    properties["Project"] = {"relation": [{"id": pid} for pid in project_page_ids]}

    if sync_description:
        properties["Description"] = {"rich_text": [{"text": {"content": card.get("desc") or ""}}]}

    return properties


def notion_page_to_trello_fields(
    page: dict,
    *,
    list_name_to_id: dict,
    project_page_id_to_label_id: dict,
    sync_description: bool = False,
) -> dict:
    """Build a dict of Trello update fields from a Notion Issue page's
    properties."""
    props = page["properties"]
    fields = {}

    title = props.get("Issue", {}).get("title", [])
    fields["name"] = "".join(t["plain_text"] for t in title) if title else "Untitled"

    if sync_description:
        desc = props.get("Description", {}).get("rich_text", [])
        fields["desc"] = "".join(t["plain_text"] for t in desc) if desc else ""

    date_prop = props.get("Due Date", {}).get("date")
    fields["due"] = date_prop["start"] if date_prop else None

    status = props.get("Status", {}).get("status")
    if status and status["name"] in list_name_to_id:
        fields["id_list"] = list_name_to_id[status["name"]]

    project_relations = props.get("Project", {}).get("relation", [])
    label_ids = [
        project_page_id_to_label_id[r["id"]]
        for r in project_relations
        if r["id"] in project_page_id_to_label_id
    ]
    if label_ids:
        fields["id_labels"] = label_ids

    return fields


def extract_project_page_ids(card: dict, label_id_to_name: dict, project_name_to_page_id: dict) -> list:
    """Trello card's Project labels -> matching Notion Project page ids.
    A label with no matching Notion project (name mismatch, or project not
    yet created in Notion) is silently skipped -- callers should log this
    upstream so mismatches surface instead of disappearing quietly."""
    label_names = [label_id_to_name[lid] for lid in card.get("idLabels", []) if lid in label_id_to_name]
    return [project_name_to_page_id[name] for name in label_names if name in project_name_to_page_id]

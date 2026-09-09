"""
One-off backfill: creates a Trello card for every existing Notion Issue that
doesn't already have one linked -- covers the Issues that predate this sync
tool.

SAFE BY DEFAULT: runs as a dry run and creates nothing unless you pass
--live. Always run the dry run first and read the summary before going live.
Safe to re-run -- already-linked Issues (including ones this script already
created or linked in an earlier run) are skipped automatically.

Duplicate protection: before creating anything, every Issue's title is
checked against ALL existing open Trello card names on the board. If a
matching card already exists (e.g. someone created it manually while
testing, before this tool tracked the link), that Issue gets LINKED to the
existing card instead of spawning a duplicate.

Usage:
    python backfill_existing_issues.py            # dry run, creates nothing
    python backfill_existing_issues.py --live      # actually creates/links
"""
import sys
import time

import requests

import mapping_store
import notion_client_custom as notion_client
import trello_client
from config import DEFAULT_LIST_NAME, DESCRIPTION_PROPERTY_CONFIRMED, NOTION_ISSUES_DATA_SOURCE_ID
from field_mapping import canonical_fingerprint, notion_page_fingerprint, notion_page_to_trello_fields

# Seconds to wait between items -- keeps us comfortably under both APIs'
# rate limits (Notion: 3 req/sec) even though this volume wouldn't strictly
# need this much caution.
PACE_SECONDS = 0.5


def get_all_issue_pages() -> list:
    """Fetches every page in the Issues database, following pagination."""
    pages = []
    payload = {}
    while True:
        resp = requests.post(
            f"{notion_client.BASE_URL}/data_sources/{NOTION_ISSUES_DATA_SOURCE_ID}/query",
            headers=notion_client.HEADERS,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data["results"])
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]
    return pages


def main():
    live = "--live" in sys.argv

    print("=" * 60)
    print("LIVE RUN -- cards will be created/linked" if live else "DRY RUN -- nothing will be created/linked")
    print("=" * 60)

    lists = trello_client.get_lists()
    labels = trello_client.get_labels()
    projects = notion_client.get_projects()
    existing_cards_by_name = trello_client.get_all_cards()
    project_page_id_to_label_id = {pid: labels[name] for name, pid in projects.items() if name in labels}

    default_list_id = lists.get(DEFAULT_LIST_NAME)
    if not default_list_id:
        print(f"ERROR: DEFAULT_LIST_NAME ({DEFAULT_LIST_NAME!r}) not found on the board. Aborting.")
        return

    pages = get_all_issue_pages()
    print(f"\nFound {len(pages)} total Issues in Notion.")
    print(f"Found {len(existing_cards_by_name)} existing open cards on the Trello board.\n")

    created, linked_existing, skipped_linked, errors = 0, 0, 0, []

    for page in pages:
        page_id = page["id"]
        title_prop = page["properties"].get("Issue", {}).get("title", [])
        title = "".join(t["plain_text"] for t in title_prop) if title_prop else "(untitled)"

        if mapping_store.get_trello_id(page_id):
            skipped_linked += 1
            continue

        try:
            # Duplicate check: does a Trello card with this exact name
            # already exist on the board (e.g. created manually during
            # testing, before the mapping table knew about it)?
            matching_card_id = existing_cards_by_name.get(title)

            if matching_card_id:
                if live:
                    mapping_store.link_ids(matching_card_id, page_id)
                    print(f"  LINKED (already existed): {title!r} -> Trello card {matching_card_id}")
                else:
                    print(f"  WOULD LINK (already existed): {title!r} -> Trello card {matching_card_id}")
                linked_existing += 1
                time.sleep(PACE_SECONDS)
                continue

            fields = notion_page_to_trello_fields(
                page,
                list_name_to_id=lists,
                project_page_id_to_label_id=project_page_id_to_label_id,
                sync_description=DESCRIPTION_PROPERTY_CONFIRMED,
            )
            id_list = fields.get("id_list") or default_list_id

            if live:
                created_card = trello_client.create_card(
                    id_list=id_list,
                    name=fields["name"],
                    desc=fields.get("desc"),
                    due=fields.get("due"),
                    id_labels=fields.get("id_labels"),
                )
                mapping_store.link_ids(created_card["id"], page_id)
                fingerprint = notion_page_fingerprint(page)
                mapping_store.mark_written(page_id, fingerprint)
                mapping_store.mark_written(created_card["id"], fingerprint)
                print(f"  CREATED: {title!r} -> Trello card {created_card['id']}")
            else:
                list_name = next((n for n, i in lists.items() if i == id_list), "?")
                print(f"  WOULD CREATE: {title!r} -> list {list_name!r}")

            created += 1
        except Exception as e:
            errors.append((title, str(e)))
            print(f"  ERROR on {title!r}: {e}")

        time.sleep(PACE_SECONDS)

    verb = "" if live else "would be "
    print("\n" + "=" * 60)
    print(
        f"Summary: {created} {verb}created new, {linked_existing} {verb}linked to existing cards, "
        f"{skipped_linked} already linked (skipped), {len(errors)} errors"
    )
    print("=" * 60)
    if errors:
        print("\nErrors:")
        for title, err in errors:
            print(f"  - {title}: {err}")

    if not live and (created > 0 or linked_existing > 0):
        print(f"\nThis was a dry run. Re-run with --live to actually apply these changes.")


if __name__ == "__main__":
    main()

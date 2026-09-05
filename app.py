import logging

from flask import Flask, jsonify, request

import mapping_store
import trello_client
import notion_client_custom as notion_client
from config import DESCRIPTION_PROPERTY_CONFIRMED
from field_mapping import (
    extract_project_page_ids,
    notion_page_to_trello_fields,
    trello_to_notion_properties,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sync")

app = Flask(__name__)
mapping_store.init_db()

# In-memory caches: Trello list/label name<->id, and Notion Project name<->page_id.
_lists_cache = {}
_labels_cache = {}
_projects_cache = {}


def refresh_trello_metadata():
    global _lists_cache, _labels_cache
    _lists_cache = trello_client.get_lists()
    _labels_cache = trello_client.get_labels()
    log.info("Refreshed Trello metadata: %d lists, %d labels", len(_lists_cache), len(_labels_cache))


def refresh_projects_metadata():
    global _projects_cache
    _projects_cache = notion_client.get_projects()
    log.info("Refreshed Notion Projects: %d projects", len(_projects_cache))
    missing = [name for name in _labels_cache if name not in _projects_cache]
    if missing:
        log.warning(
            "%d Trello Project label(s) have no matching Notion Project row: %s",
            len(missing), missing,
        )


@app.route("/health")
def health():
    return {"status": "ok"}


@app.route("/trello-webhook", methods=["HEAD", "POST"])
def trello_webhook():
    # Trello sends a HEAD request when the webhook is first registered -- just 200 it.
    if request.method == "HEAD":
        return "", 200

    payload = request.get_json(silent=True) or {}
    action = payload.get("action", {})
    action_type = action.get("type")

    if action_type not in {"updateCard", "createCard", "changeCard", "moveCardToBoard"}:
        return jsonify({"skipped": action_type}), 200

    card_id = action.get("data", {}).get("card", {}).get("id")
    if not card_id:
        return jsonify({"skipped": "no card id"}), 200

    try:
        sync_trello_card_to_notion(card_id)
    except Exception:
        log.exception("Failed syncing Trello card %s to Notion", card_id)
        return jsonify({"error": "sync failed"}), 500

    return jsonify({"ok": True}), 200


@app.route("/notion-webhook", methods=["POST"])
def notion_webhook():
    payload = request.get_json(silent=True) or {}

    # Notion's webhook verification handshake: on first setup it POSTs a
    # verification_token you paste into the Developer portal to confirm the
    # endpoint. Log it, don't try to process it as an event.
    if "verification_token" in payload:
        log.info("Notion webhook verification token: %s", payload["verification_token"])
        return jsonify({"received": True}), 200

    event_type = payload.get("type")
    if event_type not in {"page.properties_updated", "page.created"}:
        return jsonify({"skipped": event_type}), 200

    page_id = payload.get("entity", {}).get("id")
    if not page_id:
        return jsonify({"skipped": "no page id"}), 200

    try:
        sync_notion_page_to_trello(page_id)
    except Exception:
        log.exception("Failed syncing Notion page %s to Trello", page_id)
        return jsonify({"error": "sync failed"}), 500

    return jsonify({"ok": True}), 200


def sync_trello_card_to_notion(card_id: str):
    if not _lists_cache or not _labels_cache:
        refresh_trello_metadata()
    if not _projects_cache:
        refresh_projects_metadata()

    card = trello_client.get_card(card_id)
    label_id_to_name = {v: k for k, v in _labels_cache.items()}
    list_id_to_name = {v: k for k, v in _lists_cache.items()}

    list_name = list_id_to_name.get(card.get("idList"))
    project_page_ids = extract_project_page_ids(card, label_id_to_name, _projects_cache)
    properties = trello_to_notion_properties(
        card,
        list_name=list_name,
        project_page_ids=project_page_ids,
        sync_description=DESCRIPTION_PROPERTY_CONFIRMED,
    )

    if mapping_store.is_echo(card_id, properties):
        log.info("Skipping echo for Trello card %s", card_id)
        return

    notion_page_id = mapping_store.get_notion_id(card_id)
    if notion_page_id:
        notion_client.update_page(notion_page_id, properties)
    else:
        created = notion_client.create_issue_page(properties)
        notion_page_id = created["id"]
        mapping_store.link_ids(card_id, notion_page_id)

    mapping_store.mark_written(notion_page_id, properties)
    log.info("Synced Trello card %s -> Notion page %s", card_id, notion_page_id)


def sync_notion_page_to_trello(page_id: str):
    if not _lists_cache or not _labels_cache:
        refresh_trello_metadata()
    if not _projects_cache:
        refresh_projects_metadata()

    page = notion_client.get_page(page_id)
    project_page_id_to_label_id = {
        pid: _labels_cache[name] for name, pid in _projects_cache.items() if name in _labels_cache
    }
    fields = notion_page_to_trello_fields(
        page,
        list_name_to_id=_lists_cache,
        project_page_id_to_label_id=project_page_id_to_label_id,
        sync_description=DESCRIPTION_PROPERTY_CONFIRMED,
    )

    if mapping_store.is_echo(page_id, fields):
        log.info("Skipping echo for Notion page %s", page_id)
        return

    trello_card_id = mapping_store.get_trello_id(page_id)
    if not trello_card_id:
        # V1 only syncs Notion -> existing linked Trello cards. A row created
        # directly in Notion won't auto-create a Trello card until this is
        # extended -- see README "Known limitations".
        log.warning("No linked Trello card for Notion page %s yet -- skipping", page_id)
        return

    trello_client.update_card(trello_card_id, **fields)
    mapping_store.mark_written(trello_card_id, fields)
    log.info("Synced Notion page %s -> Trello card %s", page_id, trello_card_id)


if __name__ == "__main__":
    refresh_trello_metadata()
    app.run(host="0.0.0.0", port=5000)

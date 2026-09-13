import logging
import time

import requests
from flask import Flask, jsonify, request

import mapping_store
import trello_client
import notion_client_custom as notion_client
from config import DEFAULT_LIST_NAME, DESCRIPTION_PROPERTY_CONFIRMED
from field_mapping import (
    canonical_fingerprint,
    extract_project_page_ids,
    notion_page_fingerprint,
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
_trello_cache_refreshed_at = 0
_projects_cache_refreshed_at = 0

# Bug fixed 9 Sep 2026: caches previously only refreshed once, when empty --
# meaning a list/label/project added to Trello or Notion AFTER the app
# started was invisible to it until the next dyno restart. A card moved to
# an unrecognized list would get mishandled (its Status silently cleared
# instead of set), which combined with a separate echo-detection bug could
# make cards appear to move back on their own. Refreshing periodically
# fixes this without needing a manual restart every time the board changes.
CACHE_TTL_SECONDS = 300


def refresh_trello_metadata():
    global _lists_cache, _labels_cache, _trello_cache_refreshed_at
    _lists_cache = trello_client.get_lists()
    _labels_cache = trello_client.get_labels()
    _trello_cache_refreshed_at = time.time()
    log.info("Refreshed Trello metadata: %d lists, %d labels", len(_lists_cache), len(_labels_cache))


def refresh_projects_metadata():
    global _projects_cache, _projects_cache_refreshed_at
    _projects_cache = notion_client.get_projects()
    _projects_cache_refreshed_at = time.time()
    log.info("Refreshed Notion Projects: %d projects", len(_projects_cache))
    missing = [name for name in _labels_cache if name.strip() not in _projects_cache]
    if missing:
        log.warning(
            "%d Trello Project label(s) have no matching Notion Project row: %s",
            len(missing), missing,
        )


def ensure_trello_metadata_fresh():
    if not _lists_cache or not _labels_cache or (time.time() - _trello_cache_refreshed_at) > CACHE_TTL_SECONDS:
        refresh_trello_metadata()


def ensure_projects_metadata_fresh():
    if not _projects_cache or (time.time() - _projects_cache_refreshed_at) > CACHE_TTL_SECONDS:
        refresh_projects_metadata()


@app.route("/health")
def health():
    return {"status": "ok"}


@app.route("/trello-webhook", methods=["HEAD", "POST"])
def trello_webhook():
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
        sync_notion_page_to_trello(page_id, event_type=event_type)
    except Exception:
        log.exception("Failed syncing Notion page %s to Trello", page_id)
        return jsonify({"error": "sync failed"}), 500

    return jsonify({"ok": True}), 200


def sync_trello_card_to_notion(card_id: str):
    ensure_trello_metadata_fresh()
    ensure_projects_metadata_fresh()

    card = trello_client.get_card(card_id)
    label_id_to_name = {v: k for k, v in _labels_cache.items()}
    list_id_to_name = {v: k for k, v in _lists_cache.items()}

    list_name = list_id_to_name.get(card.get("idList"))
    if list_name is None:
        log.warning("Unrecognized Trello list id %s -- forcing a metadata refresh and retrying", card.get("idList"))
        refresh_trello_metadata()
        list_id_to_name = {v: k for k, v in _lists_cache.items()}
        list_name = list_id_to_name.get(card.get("idList"))
        if list_name is None:
            log.error("Still unrecognized after refresh -- list may have been deleted. Skipping sync for card %s", card_id)
            return

    project_page_ids = extract_project_page_ids(card, label_id_to_name, _projects_cache)
    properties = trello_to_notion_properties(
        card,
        list_name=list_name,
        project_page_ids=project_page_ids,
        sync_description=DESCRIPTION_PROPERTY_CONFIRMED,
    )

    fingerprint = canonical_fingerprint(
        status_name=list_name,
        due_date=card["due"][:10] if card.get("due") else None,
        project_page_ids=project_page_ids,
    )
    if mapping_store.is_echo(card_id, fingerprint):
        log.info("Skipping echo for Trello card %s", card_id)
        return

    notion_page_id = mapping_store.get_notion_id(card_id)
    if notion_page_id:
        try:
            notion_client.update_page(notion_page_id, properties)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status is not None and 400 <= status < 500:
                # The linked Notion page is gone -- deleted or archived.
                # Clear the stale link and fall through to create a fresh
                # page, rather than crashing on every retry forever.
                log.warning(
                    "Linked Notion page %s for card %s returned %s -- "
                    "likely deleted/archived. Clearing stale link and creating a fresh page.",
                    notion_page_id, card_id, status,
                )
                mapping_store.unlink_by_trello_id(card_id)
                notion_page_id = None
            else:
                raise  # genuine server/network error -- let it propagate and retry normally

    if not notion_page_id:
        created = notion_client.create_issue_page(properties)
        notion_page_id = created["id"]
        mapping_store.link_ids(card_id, notion_page_id)

    mapping_store.mark_written(card_id, fingerprint)
    mapping_store.mark_written(notion_page_id, fingerprint)
    log.info("Synced Trello card %s -> Notion page %s", card_id, notion_page_id)


def sync_notion_page_to_trello(page_id: str, *, event_type: str = None):
    ensure_trello_metadata_fresh()
    ensure_projects_metadata_fresh()

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

    fingerprint = notion_page_fingerprint(page)
    if mapping_store.is_echo(page_id, fingerprint):
        log.info("Skipping echo for Notion page %s", page_id)
        return

    trello_card_id = mapping_store.get_trello_id(page_id)

    if not trello_card_id:
        # Safety gate: only CREATE a Trello card for a genuinely new page
        # (event_type == "page.created"). An unlinked page seen via
        # page.properties_updated is almost always one of the ~70 Issues
        # that existed before this tool went live -- editing those must
        # keep doing nothing, not silently spawn a duplicate Trello card
        # the first time anyone touches them. This distinction is the
        # entire point of checking event_type here rather than just
        # "is there a link yet."
        if event_type != "page.created":
            log.warning("No linked Trello card for Notion page %s yet -- skipping", page_id)
            return

        id_list = fields.get("id_list") or _lists_cache.get(DEFAULT_LIST_NAME)
        if not id_list:
            log.error(
                "Cannot create Trello card for new Notion page %s -- no Status set and "
                "DEFAULT_LIST_NAME (%r) not found on the board", page_id, DEFAULT_LIST_NAME,
            )
            return

        created = trello_client.create_card(
            id_list=id_list,
            name=fields["name"],
            desc=fields.get("desc"),
            due=fields.get("due"),
            id_labels=fields.get("id_labels"),
        )
        trello_card_id = created["id"]
        mapping_store.link_ids(trello_card_id, page_id)
        mapping_store.mark_written(page_id, fingerprint)
        mapping_store.mark_written(trello_card_id, fingerprint)
        log.info("Created new Trello card %s from Notion page %s", trello_card_id, page_id)
        return

    trello_client.update_card(trello_card_id, **fields)
    mapping_store.mark_written(page_id, fingerprint)
    mapping_store.mark_written(trello_card_id, fingerprint)
    log.info("Synced Notion page %s -> Trello card %s", page_id, trello_card_id)


if __name__ == "__main__":
    refresh_trello_metadata()
    app.run(host="0.0.0.0", port=5000)

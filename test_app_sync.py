"""
Tests for the Notion -> Trello card-creation safety gate in app.py.

The critical property being tested: an unlinked Notion page must ONLY ever
trigger Trello card creation when the webhook event was genuinely
"page.created". If a pre-existing Issue (one of the ~70 that existed before
this feature was built) gets edited and happens to be unlinked, that must
keep doing nothing -- not silently spawn a duplicate Trello card. Getting
this wrong would be a real, damaging bug (uncontrolled duplicate creation
across old issues the first time anyone touches them), so this is tested
directly with mocks rather than left to manual reasoning.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

import requests

os.environ.setdefault("TRELLO_API_KEY", "dummy")
os.environ.setdefault("TRELLO_TOKEN", "dummy")
os.environ.setdefault("TRELLO_BOARD_ID", "dummy")
os.environ.setdefault("NOTION_TOKEN", "dummy")
os.environ.setdefault("NOTION_ISSUES_DATA_SOURCE_ID", "dummy")
os.environ.setdefault("NOTION_PROJECTS_DATA_SOURCE_ID", "dummy")

import app as app_module


def _fake_page(name="New task", status=None):
    props = {"Issue": {"title": [{"plain_text": name}]}}
    if status:
        props["Status"] = {"status": {"name": status}}
    return {"properties": props}


class TestNotionToTrelloCreationGate(unittest.TestCase):
    def setUp(self):
        # Give the app a known, populated cache so it doesn't try to hit
        # the real Trello/Notion APIs during these tests.
        app_module._lists_cache = {"Backlog": "list_backlog_id", "In Progress": "list_ip_id"}
        app_module._labels_cache = {"Decision Intelligence": "label_di_id"}
        app_module._projects_cache = {"Decision Intelligence": "proj_page_id"}
        app_module._trello_cache_refreshed_at = 9999999999  # far future -> never stale in these tests
        app_module._projects_cache_refreshed_at = 9999999999

    @patch("app.trello_client")
    @patch("app.notion_client")
    @patch("app.mapping_store")
    def test_page_created_event_with_no_link_creates_a_card(self, mock_store, mock_notion, mock_trello):
        mock_store.is_echo.return_value = False
        mock_store.get_trello_id.return_value = None
        mock_notion.get_page.return_value = _fake_page(status="Backlog")
        mock_trello.create_card.return_value = {"id": "new_card_123"}

        app_module.sync_notion_page_to_trello("new_page_id", event_type="page.created")

        mock_trello.create_card.assert_called_once()
        mock_trello.update_card.assert_not_called()
        mock_store.link_ids.assert_called_once_with("new_card_123", "new_page_id")

    @patch("app.trello_client")
    @patch("app.notion_client")
    @patch("app.mapping_store")
    def test_properties_updated_event_with_no_link_does_not_create_a_card(self, mock_store, mock_notion, mock_trello):
        # This is the critical case: an OLD, pre-existing Issue gets edited
        # (not created) and has no Trello link. Must NOT create anything.
        mock_store.is_echo.return_value = False
        mock_store.get_trello_id.return_value = None
        mock_notion.get_page.return_value = _fake_page(status="In Progress")

        app_module.sync_notion_page_to_trello("old_preexisting_page_id", event_type="page.properties_updated")

        mock_trello.create_card.assert_not_called()
        mock_trello.update_card.assert_not_called()
        mock_store.link_ids.assert_not_called()

    @patch("app.trello_client")
    @patch("app.notion_client")
    @patch("app.mapping_store")
    def test_missing_event_type_with_no_link_does_not_create_a_card(self, mock_store, mock_notion, mock_trello):
        # Defensive default: if event_type is somehow missing/None, treat it
        # the same as "not a creation event" -- never create on ambiguity.
        mock_store.is_echo.return_value = False
        mock_store.get_trello_id.return_value = None
        mock_notion.get_page.return_value = _fake_page()

        app_module.sync_notion_page_to_trello("some_page_id", event_type=None)

        mock_trello.create_card.assert_not_called()

    @patch("app.trello_client")
    @patch("app.notion_client")
    @patch("app.mapping_store")
    def test_already_linked_page_updates_not_creates_even_on_created_event(self, mock_store, mock_notion, mock_trello):
        # A redelivered/duplicate page.created event for an already-linked
        # page must update, not create a second card.
        mock_store.is_echo.return_value = False
        mock_store.get_trello_id.return_value = "existing_card_id"
        mock_notion.get_page.return_value = _fake_page(status="In Progress")

        app_module.sync_notion_page_to_trello("linked_page_id", event_type="page.created")

        mock_trello.create_card.assert_not_called()
        mock_trello.update_card.assert_called_once()

    @patch("app.trello_client")
    @patch("app.notion_client")
    @patch("app.mapping_store")
    def test_new_page_with_no_status_falls_back_to_default_list(self, mock_store, mock_notion, mock_trello):
        mock_store.is_echo.return_value = False
        mock_store.get_trello_id.return_value = None
        mock_notion.get_page.return_value = _fake_page(status=None)  # no Status set yet
        mock_trello.create_card.return_value = {"id": "new_card_456"}

        app_module.sync_notion_page_to_trello("brand_new_page_id", event_type="page.created")

        _, kwargs = mock_trello.create_card.call_args
        self.assertEqual(kwargs["id_list"], app_module._lists_cache[app_module.DEFAULT_LIST_NAME])

    @patch("app.trello_client")
    @patch("app.notion_client")
    @patch("app.mapping_store")
    def test_echo_is_still_skipped_before_any_creation_logic(self, mock_store, mock_notion, mock_trello):
        mock_store.is_echo.return_value = True
        mock_notion.get_page.return_value = _fake_page(status="Backlog")

        app_module.sync_notion_page_to_trello("echoed_page_id", event_type="page.created")

        mock_trello.create_card.assert_not_called()
        mock_store.get_trello_id.assert_not_called()


def _fake_response(status_code):
    resp = MagicMock()
    resp.status_code = status_code
    return resp


def _fake_card(name="Some card", list_id="list_backlog_id", due=None, labels=None):
    return {"name": name, "idList": list_id, "due": due, "idLabels": labels or [], "desc": ""}


class TestTrelloToNotionSelfHealing(unittest.TestCase):
    """Regression tests for the 13 Sep 2026 incident: a Trello card linked to
    a Notion page that had since been deleted/archived crashed the sync on
    every single update to that card, forever, since Notion's update call
    fails with a 4xx error for a page that's gone. The fix: treat that
    specific failure as "the link is stale," clear it, and create a fresh
    Notion page instead of crashing."""

    def setUp(self):
        app_module._lists_cache = {"Backlog": "list_backlog_id"}
        app_module._labels_cache = {"Placeholder": "placeholder_label_id"}
        app_module._projects_cache = {"Placeholder": "placeholder_project_id"}
        app_module._trello_cache_refreshed_at = 9999999999
        app_module._projects_cache_refreshed_at = 9999999999

    @patch("app.trello_client")
    @patch("app.notion_client")
    @patch("app.mapping_store")
    def test_deleted_linked_page_is_recreated_not_crashed(self, mock_store, mock_notion, mock_trello):
        mock_trello.get_card.return_value = _fake_card()
        mock_store.is_echo.return_value = False
        mock_store.get_notion_id.return_value = "deleted_page_id"

        error = requests.exceptions.HTTPError(response=_fake_response(400))
        mock_notion.update_page.side_effect = error
        mock_notion.create_issue_page.return_value = {"id": "fresh_page_id"}

        app_module.sync_trello_card_to_notion("card_with_deleted_page")

        mock_store.unlink_by_trello_id.assert_called_once_with("card_with_deleted_page")
        mock_notion.create_issue_page.assert_called_once()
        mock_store.link_ids.assert_called_once_with("card_with_deleted_page", "fresh_page_id")

    @patch("app.trello_client")
    @patch("app.notion_client")
    @patch("app.mapping_store")
    def test_404_on_update_also_triggers_recreation(self, mock_store, mock_notion, mock_trello):
        mock_trello.get_card.return_value = _fake_card()
        mock_store.is_echo.return_value = False
        mock_store.get_notion_id.return_value = "deleted_page_id"

        mock_notion.update_page.side_effect = requests.exceptions.HTTPError(response=_fake_response(404))
        mock_notion.create_issue_page.return_value = {"id": "fresh_page_id"}

        app_module.sync_trello_card_to_notion("card_with_404_page")

        mock_store.unlink_by_trello_id.assert_called_once()
        mock_notion.create_issue_page.assert_called_once()

    @patch("app.trello_client")
    @patch("app.notion_client")
    @patch("app.mapping_store")
    def test_server_error_on_update_still_raises_not_swallowed(self, mock_store, mock_notion, mock_trello):
        # A genuine 500 from Notion (their outage, not a deleted page) must
        # NOT be treated as "recreate" -- that would risk creating a
        # duplicate every time Notion has a bad moment. It should propagate
        # so Trello's normal retry behavior handles it instead.
        mock_trello.get_card.return_value = _fake_card()
        mock_store.is_echo.return_value = False
        mock_store.get_notion_id.return_value = "some_page_id"

        mock_notion.update_page.side_effect = requests.exceptions.HTTPError(response=_fake_response(500))

        with self.assertRaises(requests.exceptions.HTTPError):
            app_module.sync_trello_card_to_notion("card_hitting_server_error")

        mock_store.unlink_by_trello_id.assert_not_called()
        mock_notion.create_issue_page.assert_not_called()

    @patch("app.trello_client")
    @patch("app.notion_client")
    @patch("app.mapping_store")
    def test_successful_update_does_not_touch_unlink_or_create(self, mock_store, mock_notion, mock_trello):
        mock_trello.get_card.return_value = _fake_card()
        mock_store.is_echo.return_value = False
        mock_store.get_notion_id.return_value = "healthy_page_id"
        mock_notion.update_page.return_value = {"id": "healthy_page_id"}

        app_module.sync_trello_card_to_notion("normal_card")

        mock_store.unlink_by_trello_id.assert_not_called()
        mock_notion.create_issue_page.assert_not_called()


if __name__ == "__main__":
    unittest.main()

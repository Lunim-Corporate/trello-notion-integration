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


if __name__ == "__main__":
    unittest.main()

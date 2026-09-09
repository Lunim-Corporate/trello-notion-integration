"""
Tests for backfill_existing_issues.py -- proving the safety properties that
matter most for a script that creates real, hard-to-undo objects on a
shared team board: dry-run must create nothing, one item's error must not
stop the rest of the batch, already-linked items must be skipped, and --
critically -- an Issue whose title matches an EXISTING Trello card must be
linked to it, never duplicated. This last one was a real incident: cards
created manually during testing (before this script existed) would have
been silently duplicated without this check.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("TRELLO_API_KEY", "dummy")
os.environ.setdefault("TRELLO_TOKEN", "dummy")
os.environ.setdefault("TRELLO_BOARD_ID", "dummy")
os.environ.setdefault("NOTION_TOKEN", "dummy")
os.environ.setdefault("NOTION_ISSUES_DATA_SOURCE_ID", "dummy")
os.environ.setdefault("NOTION_PROJECTS_DATA_SOURCE_ID", "dummy")

import backfill_existing_issues as backfill


def _page(page_id, name, status=None):
    props = {"Issue": {"title": [{"plain_text": name}]}}
    if status:
        props["Status"] = {"status": {"name": status}}
    return {"id": page_id, "properties": props}


class TestBackfillDryRun(unittest.TestCase):
    def setUp(self):
        self.pages = [
            _page("page1", "Old task 1", status="Backlog"),
            _page("page2", "Old task 2", status="Done"),
        ]

    def _base_mocks(self, mock_trello, mock_notion):
        mock_trello.get_lists.return_value = {"Backlog": "list_id_1", "Done": "list_id_2"}
        mock_trello.get_labels.return_value = {}
        mock_trello.get_all_cards.return_value = {}  # no existing cards by default
        mock_notion.get_projects.return_value = {}

    @patch("backfill_existing_issues.get_all_issue_pages")
    @patch("backfill_existing_issues.mapping_store")
    @patch("backfill_existing_issues.notion_client")
    @patch("backfill_existing_issues.trello_client")
    def test_dry_run_creates_nothing(self, mock_trello, mock_notion, mock_store, mock_get_pages):
        mock_get_pages.return_value = self.pages
        self._base_mocks(mock_trello, mock_notion)
        mock_store.get_trello_id.return_value = None

        sys.argv = ["backfill_existing_issues.py"]  # no --live
        backfill.main()

        mock_trello.create_card.assert_not_called()
        mock_store.link_ids.assert_not_called()

    @patch("backfill_existing_issues.get_all_issue_pages")
    @patch("backfill_existing_issues.mapping_store")
    @patch("backfill_existing_issues.notion_client")
    @patch("backfill_existing_issues.trello_client")
    def test_live_run_creates_cards_for_unlinked_pages(self, mock_trello, mock_notion, mock_store, mock_get_pages):
        mock_get_pages.return_value = self.pages
        self._base_mocks(mock_trello, mock_notion)
        mock_store.get_trello_id.return_value = None
        mock_trello.create_card.side_effect = [{"id": "new1"}, {"id": "new2"}]

        sys.argv = ["backfill_existing_issues.py", "--live"]
        backfill.main()

        self.assertEqual(mock_trello.create_card.call_count, 2)
        self.assertEqual(mock_store.link_ids.call_count, 2)

    @patch("backfill_existing_issues.get_all_issue_pages")
    @patch("backfill_existing_issues.mapping_store")
    @patch("backfill_existing_issues.notion_client")
    @patch("backfill_existing_issues.trello_client")
    def test_already_linked_pages_are_skipped(self, mock_trello, mock_notion, mock_store, mock_get_pages):
        mock_get_pages.return_value = self.pages
        self._base_mocks(mock_trello, mock_notion)
        mock_store.get_trello_id.return_value = "already_linked_card_id"

        sys.argv = ["backfill_existing_issues.py", "--live"]
        backfill.main()

        mock_trello.create_card.assert_not_called()

    @patch("backfill_existing_issues.get_all_issue_pages")
    @patch("backfill_existing_issues.mapping_store")
    @patch("backfill_existing_issues.notion_client")
    @patch("backfill_existing_issues.trello_client")
    def test_one_item_error_does_not_stop_the_batch(self, mock_trello, mock_notion, mock_store, mock_get_pages):
        mock_get_pages.return_value = self.pages
        self._base_mocks(mock_trello, mock_notion)
        mock_store.get_trello_id.return_value = None
        mock_trello.create_card.side_effect = [Exception("Trello API error"), {"id": "new2"}]

        sys.argv = ["backfill_existing_issues.py", "--live"]
        backfill.main()  # should not raise

        self.assertEqual(mock_trello.create_card.call_count, 2)
        mock_store.link_ids.assert_called_once()

    @patch("backfill_existing_issues.get_all_issue_pages")
    @patch("backfill_existing_issues.mapping_store")
    @patch("backfill_existing_issues.notion_client")
    @patch("backfill_existing_issues.trello_client")
    def test_missing_default_list_aborts_before_touching_anything(self, mock_trello, mock_notion, mock_store, mock_get_pages):
        mock_trello.get_lists.return_value = {"SomeOtherList": "id1"}  # no "Backlog"
        mock_trello.get_labels.return_value = {}
        mock_trello.get_all_cards.return_value = {}
        mock_notion.get_projects.return_value = {}

        sys.argv = ["backfill_existing_issues.py", "--live"]
        backfill.main()

        mock_get_pages.assert_not_called()
        mock_trello.create_card.assert_not_called()

    @patch("backfill_existing_issues.get_all_issue_pages")
    @patch("backfill_existing_issues.mapping_store")
    @patch("backfill_existing_issues.notion_client")
    @patch("backfill_existing_issues.trello_client")
    def test_matching_existing_card_is_linked_not_duplicated(self, mock_trello, mock_notion, mock_store, mock_get_pages):
        # The critical regression test: "Old task 1" already has a real
        # Trello card (created manually, e.g. during testing) that the
        # mapping table doesn't know about yet. Must link to it, not
        # create a second, duplicate card.
        mock_get_pages.return_value = [self.pages[0]]  # just "Old task 1"
        self._base_mocks(mock_trello, mock_notion)
        mock_trello.get_all_cards.return_value = {"Old task 1": "existing_card_abc"}
        mock_store.get_trello_id.return_value = None

        sys.argv = ["backfill_existing_issues.py", "--live"]
        backfill.main()

        mock_trello.create_card.assert_not_called()
        mock_store.link_ids.assert_called_once_with("existing_card_abc", "page1")

    @patch("backfill_existing_issues.get_all_issue_pages")
    @patch("backfill_existing_issues.mapping_store")
    @patch("backfill_existing_issues.notion_client")
    @patch("backfill_existing_issues.trello_client")
    def test_dry_run_does_not_link_matching_cards_either(self, mock_trello, mock_notion, mock_store, mock_get_pages):
        mock_get_pages.return_value = [self.pages[0]]
        self._base_mocks(mock_trello, mock_notion)
        mock_trello.get_all_cards.return_value = {"Old task 1": "existing_card_abc"}
        mock_store.get_trello_id.return_value = None

        sys.argv = ["backfill_existing_issues.py"]  # no --live
        backfill.main()

        mock_store.link_ids.assert_not_called()


if __name__ == "__main__":
    unittest.main()

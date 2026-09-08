import unittest

from field_mapping import (
    canonical_fingerprint,
    extract_project_page_ids,
    notion_page_fingerprint,
    notion_page_to_trello_fields,
    trello_to_notion_properties,
)


class TestTrelloToNotion(unittest.TestCase):
    def test_basic_card(self):
        card = {
            "name": "Fix login bug",
            "desc": "Users can't log in on Safari",
            "due": "2026-09-15T00:00:00.000Z",
            "shortUrl": "https://trello.com/c/abc123",
            "idLabels": ["label1"],
        }
        props = trello_to_notion_properties(card, list_name="In Progress", project_page_ids=["proj-page-id-3"])

        self.assertEqual(props["Issue"]["title"][0]["text"]["content"], "Fix login bug")
        self.assertEqual(props["Status"]["status"]["name"], "In Progress")
        self.assertEqual(props["Due Date"]["date"]["start"], "2026-09-15")
        self.assertEqual(props["Project"]["relation"], [{"id": "proj-page-id-3"}])

    def test_no_due_date_no_project(self):
        card = {"name": "Untitled task", "desc": "", "due": None, "shortUrl": "https://trello.com/c/xyz", "idLabels": []}
        props = trello_to_notion_properties(card, list_name="Backlog", project_page_ids=[])

        self.assertIsNone(props["Due Date"]["date"])
        self.assertEqual(props["Project"]["relation"], [])

    def test_multiple_project_labels_all_included(self):
        card = {"name": "Cross-project card", "desc": "", "due": None, "shortUrl": "https://trello.com/c/m", "idLabels": []}
        props = trello_to_notion_properties(card, list_name="Backlog", project_page_ids=["p1", "p2"])

        self.assertEqual(props["Project"]["relation"], [{"id": "p1"}, {"id": "p2"}])

    def test_description_not_synced_by_default(self):
        card = {"name": "X", "desc": "some text", "due": None, "shortUrl": "https://trello.com/c/x", "idLabels": []}
        props = trello_to_notion_properties(card, list_name="Backlog", project_page_ids=[])
        self.assertNotIn("Description", props)


class TestNotionToTrello(unittest.TestCase):
    def test_basic_page(self):
        page = {
            "properties": {
                "Issue": {"title": [{"plain_text": "Write tests"}]},
                "Due Date": {"date": {"start": "2026-09-20"}},
                "Status": {"status": {"name": "In Review"}},
                "Project": {"relation": [{"id": "proj-page-5"}]},
            }
        }
        fields = notion_page_to_trello_fields(
            page,
            list_name_to_id={"In Review": "list_review_id"},
            project_page_id_to_label_id={"proj-page-5": "label_p5_id"},
        )

        self.assertEqual(fields["name"], "Write tests")
        self.assertEqual(fields["due"], "2026-09-20")
        self.assertEqual(fields["id_list"], "list_review_id")
        self.assertEqual(fields["id_labels"], ["label_p5_id"])

    def test_empty_page(self):
        page = {"properties": {"Issue": {"title": []}}}
        fields = notion_page_to_trello_fields(page, list_name_to_id={}, project_page_id_to_label_id={})

        self.assertEqual(fields["name"], "Untitled")
        self.assertIsNone(fields["due"])
        self.assertNotIn("id_list", fields)
        self.assertNotIn("id_labels", fields)

    def test_unmapped_status_is_skipped(self):
        page = {
            "properties": {
                "Issue": {"title": [{"plain_text": "X"}]},
                "Status": {"status": {"name": "Some New Status"}},
            }
        }
        fields = notion_page_to_trello_fields(page, list_name_to_id={"Backlog": "id1"}, project_page_id_to_label_id={})
        self.assertNotIn("id_list", fields)

    def test_project_relation_with_no_trello_label_match_is_skipped(self):
        page = {
            "properties": {
                "Issue": {"title": [{"plain_text": "X"}]},
                "Project": {"relation": [{"id": "unmatched-project-id"}]},
            }
        }
        fields = notion_page_to_trello_fields(page, list_name_to_id={}, project_page_id_to_label_id={})
        self.assertNotIn("id_labels", fields)


class TestExtractProjectPageIds(unittest.TestCase):
    def test_matches_known_project(self):
        card = {"idLabels": ["l1", "l2"]}
        label_id_to_name = {"l1": "Decision Intelligence", "l2": "Unrelated Label"}
        project_name_to_page_id = {"Decision Intelligence": "page-abc"}

        result = extract_project_page_ids(card, label_id_to_name, project_name_to_page_id)
        self.assertEqual(result, ["page-abc"])

    def test_label_with_no_matching_project_is_skipped(self):
        card = {"idLabels": ["l1"]}
        label_id_to_name = {"l1": "Some Label With No Notion Project"}
        result = extract_project_page_ids(card, label_id_to_name, project_name_to_page_id={})
        self.assertEqual(result, [])

    def test_no_labels(self):
        result = extract_project_page_ids({"idLabels": []}, {}, {})
        self.assertEqual(result, [])


class TestCanonicalFingerprint(unittest.TestCase):
    """Regression tests for the 9 Sep 2026 echo-detection bug: mark_written and
    is_echo were being called with structurally different dicts depending on
    sync direction (raw Notion properties vs raw Trello fields), so echoes
    were never actually recognized. These prove the fix: both directions must
    now produce an IDENTICAL fingerprint for the same underlying state."""

    def test_trello_and_notion_directions_produce_identical_fingerprint(self):
        trello_side = canonical_fingerprint(
            status_name="In Review",
            due_date="2026-09-20",
            project_page_ids=["proj-page-5"],
        )

        notion_page = {
            "properties": {
                "Status": {"status": {"name": "In Review"}},
                "Due Date": {"date": {"start": "2026-09-20"}},
                "Project": {"relation": [{"id": "proj-page-5"}]},
            }
        }
        notion_side = notion_page_fingerprint(notion_page)

        self.assertEqual(trello_side, notion_side)

    def test_fingerprint_ignores_project_order(self):
        fp1 = canonical_fingerprint(status_name="Backlog", due_date=None, project_page_ids=["a", "b"])
        fp2 = canonical_fingerprint(status_name="Backlog", due_date=None, project_page_ids=["b", "a"])
        self.assertEqual(fp1, fp2)

    def test_different_status_produces_different_fingerprint(self):
        fp1 = canonical_fingerprint(status_name="Backlog", due_date=None, project_page_ids=[])
        fp2 = canonical_fingerprint(status_name="On Hold", due_date=None, project_page_ids=[])
        self.assertNotEqual(fp1, fp2)

    def test_notion_page_fingerprint_handles_missing_properties(self):
        page = {"properties": {}}
        fp = notion_page_fingerprint(page)
        self.assertEqual(fp, {"status": None, "due": None, "projects": []})


if __name__ == "__main__":
    unittest.main()

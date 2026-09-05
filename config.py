import os

from dotenv import load_dotenv

load_dotenv()

TRELLO_API_KEY = os.environ["TRELLO_API_KEY"]
TRELLO_TOKEN = os.environ["TRELLO_TOKEN"]
TRELLO_BOARD_ID = os.environ["TRELLO_BOARD_ID"]

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_API_VERSION = "2026-03-11"

# The Lunim Project Tracker is two linked databases, not one flat table:
#   Issues   -- task-level rows; this is what Trello cards sync to
#   Projects -- one row per real project; Issues.Project is a RELATION to this
# Find each data_source_id the same way as before (via the database URL / API).
NOTION_ISSUES_DATA_SOURCE_ID = os.environ["NOTION_ISSUES_DATA_SOURCE_ID"]
NOTION_PROJECTS_DATA_SOURCE_ID = os.environ["NOTION_PROJECTS_DATA_SOURCE_ID"]

# Confirmed from the real Issues database (screenshots, 2 Sep 2026). If Lunim
# adds/renames a status, this needs updating to match exactly.
STATUS_NAMES = ["Backlog", "On Deck", "In Progress", "In Review", "Done", "Archived"]

# NOT YET CONFIRMED against the real schema -- the Table view screenshots we
# had didn't show an Assignee or Description column (they may exist further
# right, off-screen). Sync for these two fields is disabled until confirmed;
# see field_mapping.py.
ASSIGNEE_PROPERTY_CONFIRMED = False
DESCRIPTION_PROPERTY_CONFIRMED = False

# Optional: map Trello member usernames to Notion user IDs. Notion has no
# guaranteed cross-workspace username/email lookup, so this is filled in by
# hand. Only relevant once ASSIGNEE_PROPERTY_CONFIRMED is True.
TRELLO_MEMBER_TO_NOTION_USER = {
    # "trello_username": "notion_user_id",
}

# How long (seconds) a write we just made is remembered, so the webhook echo
# it triggers on the other platform can be recognized and skipped instead of
# bouncing back and forth forever.
SYNC_ECHO_WINDOW_SECONDS = 10

DATABASE_PATH = os.environ.get("MAPPING_DB_PATH", "mapping.db")

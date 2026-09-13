# Trello ↔ Notion Sync — Handover Document

**Author:** Diana Zagrebina · **Date:** September 2026 · **Status:** Live and confirmed working (both directions tested against the real Lunim Project Tracker)

---

## 1. What this is, and why it exists

This is a small, self-hosted, custom-built application that keeps a Trello board and the real Lunim **Project Tracker** in Notion in sync automatically — no manual copying of task status between the two tools.

**Why it exists:** the team works day-to-day in Trello, but Lunim's actual Project Tracker (with its Issues and Projects databases, priority tracking, and rollup reporting) lives in Notion. Before this tool, keeping both up to date meant manually updating both systems every time a task's status changed. This tool removes that manual step entirely.

**What it actually does, concretely:**
- Move a card between lists in Trello → the matching Notion Issue's Status updates automatically
- Change an Issue's Status in Notion → the matching Trello card moves lists automatically
- Change a card's Project label in Trello → the Issue's Project relation in Notion updates to point at the right project
- Create a card in Trello → a matching new Issue appears in Notion automatically
- **Create a brand-new row in Notion → a matching new card appears in Trello automatically** (added 9 Sep 2026, see 2.6 below — this direction only fires for genuinely new pages, never for edits to old pre-existing Issues)
- Runs continuously on its own, hosted on Heroku — no laptop, no manual triggering, no ongoing involvement needed from anyone once it's running

**Current status:** deployed, live, and all sync paths (both status/field updates in both directions, plus creation in both directions) have been manually tested and confirmed working against the real Issues/Projects databases (not a sandbox).

**Immediate next step for whoever inherits this:** read Section 3 below — the Trello board this currently syncs with is tied to my personal Trello account, and that needs to change before I leave. This is the single most important thing in this document.

### Recommended workflow (read this first — it's the practical summary of everything below)

**Creating a new work item works from either side now.** Create a card in Trello, or create a new row in Notion — either way, a matching item appears on the other side and the pairing is remembered from then on. Editing an already-linked item also works from either side.

**All Issues that existed before 9 September 2026 are now linked too** — see the backfill note in Section 4. This used to be the biggest limitation of this tool; it no longer is. Editing an old Issue now syncs correctly, same as any other.

### Known limitations (read before relying on this for anything important)

- **The live app's Notion→Trello direction does not check for an existing Trello card by name before creating one.** This is a real, currently-unfixed gap, discovered while building the backfill script below: if a brand-new Notion Issue is created with the *exact same title* as a card that already exists on the Trello board for some other reason, the app will create a genuine duplicate rather than linking to the existing one. The backfill script (Section 4) *does* have this protection — it was deliberately built into that one-off script, but never carried over into the always-running app itself. Worth porting that same name-matching check into `sync_notion_page_to_trello`'s creation path — estimated ~30-45 minutes, since the logic and its tests already exist in `backfill_existing_issues.py` as a reference.
- **Deleting/archiving a card or Issue on one side does not delete/archive it on the other.** Neither webhook handler currently listens for delete events at all — this simply hasn't been built yet. Estimated ~2-3 hours for both directions, plus one real decision to make first: should a delete on one side *archive* the other (safer, reversible) or *permanently delete* it (matches intent more literally, but destructive)? Archiving is the safer default recommendation.
- **Card/Issue order (position within a list or view) is not synced.** Reordering cards within a Trello list, or reordering rows in a Notion view, doesn't carry over to the other side. Worth flagging honestly: this may not just be unbuilt, it may not be *possible* — manual card order within a Notion board view doesn't appear to be exposed through Notion's public API the way properties are. This needs investigation before anyone estimates a build time for it, rather than assuming it's straightforward.
- **Assignee and Description are not synced.** These properties exist in the real schema (`Owner` for assignee, type `people`) but syncing them was never built — estimated ~2-2.5 hours combined, flagged as a possible next feature, not a bug.
- **This tool never writes to the Projects database** — only reads it, to resolve which Project a label refers to.

---

## 2. Full build history and technical documentation

### 2.1 Architecture

A Python Flask app with two webhook-receiving endpoints:
- `/trello-webhook` — Trello calls this whenever a card changes
- `/notion-webhook` — Notion calls this whenever an Issue's properties change

Both directions write through to the other platform's API, with a Postgres-backed ID-mapping table preventing infinite sync loops (a write triggers the other platform's webhook, which would otherwise trigger another write, forever).

### 2.2 Files, and what each one does

| File | Purpose |
|---|---|
| `app.py` | The Flask app itself — defines the two webhook routes and the sync logic that ties everything together |
| `config.py` | Loads all credentials and settings from environment variables |
| `field_mapping.py` | Pure, network-free translation logic between Trello card fields and Notion Issue properties. Fully unit-tested (11 tests) |
| `trello_client.py` | Thin wrapper around Trello's REST API |
| `notion_client_custom.py` | Thin wrapper around Notion's REST API, including `get_projects()` which resolves Project names to their real Notion page IDs |
| `mapping_store.py` | The ID-mapping and loop-prevention database layer. Uses Postgres on Heroku (SQLite locally) — see Section 5 for why this distinction matters |
| `resolve_data_sources.py` | One-time helper to find a Notion database's real `data_source_id` from its URL. Kept for reference / future re-use |
| `register_trello_webhook.py` | One-time helper to register the Trello webhook against a deployed URL |
| `backfill_existing_issues.py` | One-off script (already run successfully) that links/creates Trello cards for Issues that predate this tool. Dry-run by default; see Section 4 |
| `Procfile` | Tells Heroku how to start the app (`gunicorn app:app`) |
| `.python-version` | Pins Python to 3.12 — required for `psycopg2-binary` to install correctly (see Section 5) |
| `requirements.txt` | Python dependencies |
| `test_field_mapping.py` | Unit tests for the translation logic — run with `python3 -m unittest test_field_mapping -v` |
| `test_app_sync.py` | Tests for the Notion→Trello card-creation safety gate (6 tests) |
| `test_backfill.py` | Tests for the backfill script, including the duplicate-linking behavior (7 tests) |
| `.env` (not in git) | The actual credentials — never committed, see `.gitignore` |

### 2.3 What actually gets synced

| Trello | ↔ | Notion (Issues database) |
|---|---|---|
| Card name | | `Issue` (title property) |
| Due date | | `Due Date` |
| List (Backlog / On Deck / In Progress / In Review / Done / Archived) | | `Status` — **this is Notion's "Status" property type, not "Select"; they use different API shapes** |
| Project label (must exactly match a real Project's name) | | `Project` — a **relation** to the Projects database, not a simple label |

### 2.4 Where everything lives

- **Code:** `https://github.com/Lunim-Corporate/trello-notion-integration` (properly owned by Lunim, not a personal account)
- **Hosting:** Heroku app `notion-trello-integration` (EU region), owned by Lunim's Heroku team account (`tabb@herokumanager.com`), with a `heroku-postgresql:essential-0` add-on (~$5/month)
- **Live URL:** `https://notion-trello-integration-ce5ba8e788f7.herokuapp.com`
- **Notion integration:** an internal integration named **"PMS Trello"** in the Lunim Notion workspace — created and owned by Pete/Peter. **Important: there is also a separate, unrelated integration called "KMS" in the same workspace — the webhook must be registered on "PMS Trello" specifically, not "KMS." This tripped us up once already during setup.**
- **Trello board:** "Sprint tracker — Dashboard Pilot" — **currently in my personal Trello workspace, not a Lunim-owned one.** See Section 3.

### 2.5 Environment variables (names only — actual values are in Heroku's config vars and my local `.env`, never in this document or in git)

```
TRELLO_API_KEY
TRELLO_TOKEN
TRELLO_BOARD_ID
NOTION_TOKEN
NOTION_ISSUES_DATA_SOURCE_ID
NOTION_PROJECTS_DATA_SOURCE_ID
DATABASE_URL          (auto-set by Heroku's Postgres add-on, don't set manually)
```

To view or change these on the live app: `heroku config -a notion-trello-integration`

### 2.6 How Notion → Trello card creation stays safe (added 9 Sep 2026)

A new Notion Issue only ever creates a Trello card when the incoming webhook event is specifically `page.created` — not merely "this page has no linked card yet." That distinction is the entire safety mechanism: every one of the ~70 pre-existing Issues also has no linked card, and without this check, editing any of them would have silently spawned a duplicate Trello card the first time anyone touched it.

If a page has no Status set yet, the new card defaults to the `Backlog` list (configurable). This behavior has 6 dedicated tests (`test_app_sync.py`) proving the safety gate specifically — including a test that directly simulates editing an old, unlinked page and confirms nothing gets created.

### 2.7 How to check the app is actually working (read this if something seems wrong)

**Is it running at all?**
```
heroku ps -a notion-trello-integration
```
Should show `web.1: up`. If it shows "No dynos," run `heroku ps:scale web=1 -a notion-trello-integration`.

**Is it responding?** Open `https://notion-trello-integration-ce5ba8e788f7.herokuapp.com/health` in a browser — should show `{"status":"ok"}`.

**Watch what it's doing in real time:**
```
heroku logs --tail -a notion-trello-integration
```
Leave this running, then move a card in Trello or edit an Issue in Notion and watch for a matching line. Press Ctrl+C to stop watching.

**What a successful sync looks like:**
```
INFO:sync:Synced Trello card <id> -> Notion page <id>
INFO:sync:Synced Notion page <id> -> Trello card <id>
INFO:sync:Created new Trello card <id> from Notion page <id>
```

**Lines that look alarming but are actually normal, expected behavior:**
```
INFO:sync:Skipping echo for Trello card <id>       <- loop-prevention working correctly
INFO:sync:Skipping echo for Notion page <id>        <- same, other direction
WARNING:sync:No linked Trello card for Notion page <id> yet -- skipping
```
That last one is expected if someone edits a Notion page that was created directly in Notion but hasn't been through a full sync yet, or in the rare case the backfill script (Section 4) somehow missed something. It is only a real problem if it appears for something that should already be linked.

**What an actual problem looks like:**
```
ERROR:sync:Failed syncing Trello card <id> to Notion
<a Python traceback follows>
```
If you see this, copy the full traceback — that's what's needed to diagnose it. Common historical causes are catalogued in Section 5 below.

**A change isn't showing up yet — before assuming it's broken:** Notion's webhooks are aggregated/delayed by Notion itself (Section 5) — wait a minute or two and check the logs again before concluding something's wrong.

---

## 3. Trello board handover — three ways to proceed

### Option A: Add an admin to the existing board (fastest, but doesn't fully fix the bus-factor problem)

1. Open "Sprint tracker — Dashboard Pilot" → **Share** → invite the new person by email → set their role to **Admin** (not just Member)
2. This gives them full board control immediately

**Why this alone isn't a complete fix:** the board still lives inside my personal Trello workspace (`userworkspace64363812`). If my Trello account is ever deactivated or inaccessible, there's a real risk to the board's continued existence, even with someone else as Admin. This option buys time but should be followed by Option B when convenient.

**Also required regardless of which option is chosen:** the credentials the app currently uses (`TRELLO_API_KEY`, `TRELLO_TOKEN`) were generated from **my personal** Trello account. These should be replaced with credentials from whoever becomes the new owner/admin, so the tool doesn't depend on my account indefinitely. Steps:
1. The new Trello admin goes to `trello.com/power-ups/admin` → creates a Power-Up → generates their own API Key and Token (see the app's `README.md`, Section 1, for the detailed walkthrough)
2. Update Heroku: `heroku config:set TRELLO_API_KEY=<new key> TRELLO_TOKEN=<new token> -a notion-trello-integration`
3. Re-register the Trello webhook (old one still points at the old key's authorization): first delete the old webhook via Trello's API or just let it fail silently, then run `python register_trello_webhook.py https://notion-trello-integration-ce5ba8e788f7.herokuapp.com/trello-webhook` using the new credentials locally

### Option B: Create a proper Lunim Trello Workspace and move the board there (recommended, more durable)

1. Someone with Trello admin rights creates a new Trello Workspace under a Lunim-controlled account (not a personal one)
2. From the existing board's settings, use **"Move workspace"** to relocate "Sprint tracker — Dashboard Pilot" into the new Lunim Workspace (requires being an Admin on the board)
3. Follow the same credential-replacement steps as Option A once this is done

### Option C: Start fresh with a brand-new board

If preferred instead of migrating the existing one:

1. Create a new board in a Lunim-owned Trello Workspace
2. Create exactly 6 lists, named **exactly**: `Backlog`, `On Deck`, `In Progress`, `In Review`, `Done`, `Archived` — these names must match Notion's Status options character-for-character, or the sync won't recognize them
3. Create one label per real Notion project, named **exactly** matching each Project's title in the Projects database (currently: Tabb Slice/Upgrade, Decision Intelligence, Psychological Profiling, Lunim MarComs Campaign, Lunim Site Upgrade, The Listening Road Site, Trello & Notion, Grant Delivery Project, Maya Poetry Awards Campaign, Maya Poetry Awards Site Upgrade, Crichel Down, Arthur Gordon Pym, Moonstone — or whatever the current list is by then)
4. Get the new board's ID (`GET https://api.trello.com/1/boards/<shortLink>?fields=id` with any valid key/token, or ask me/check the board's URL)
5. Update Heroku: `heroku config:set TRELLO_BOARD_ID=<new board id> -a notion-trello-integration` (plus new API key/token if also changing accounts)
6. Re-run `register_trello_webhook.py` pointed at the new board

**Note:** the Notion side (`NOTION_ISSUES_DATA_SOURCE_ID`, `NOTION_PROJECTS_DATA_SOURCE_ID`) does not need to change for any of these options — only the Trello side changes.

---

## 4. Changes made after initial launch (9-13 Sep 2026)

Three real bugs surfaced during real-world use after the initial deployment, plus one new feature was added the same day. All documented here because they're exactly the kind of thing that's easy to reintroduce accidentally, or assume doesn't exist, if this code gets modified later without this context.

**Bug 1 — stale metadata cache.** The app originally only fetched Trello's lists/labels and Notion's projects *once*, when it first started up, and never refreshed them again. When an "On Hold" list was added to the Trello board after the app was already running, the app had no idea it existed — any card moved there got mishandled (its Notion Status was silently cleared instead of set to "On Hold"). **Fix:** the cache now refreshes automatically every 5 minutes, and also force-refreshes immediately if it ever encounters an unrecognized list ID, rather than waiting for the next scheduled refresh.

**Bug 2 — echo-detection comparing incompatible data shapes.** The loop-prevention logic (which stops a Trello write from bouncing back and forth with Notion forever) was comparing a Notion-shaped payload against a Trello-shaped payload for what should have been the same underlying change — two structurally different dicts that could never actually match. This meant echoes were never correctly recognized, which combined with Bug 1 could make a card appear to "revert on its own" after being moved. **Fix:** both sync directions now build an identical, direction-independent "fingerprint" (status name, due date, sorted project ids) before comparing, so a genuine echo is reliably recognized as one.

**Bug 3 — trailing whitespace breaking Project matching.** Three real Notion projects ("Trello & Notion," "Maya Poetry Awards Campaign," "Psychological Profiling") had invisible trailing spaces in their titles, which silently broke the exact-string match against the (correctly clean) Trello label names — those three cards' Project relation just never got set, with only a log warning to show for it. **Fix:** both the Trello label name and the Notion project name are now whitespace-stripped before comparing, so this entire class of typo can't cause a silent failure again.

**Feature — Notion → Trello card creation.** Originally shipped as read/update-only in that direction (see Section 2.6 above for how the safety gate works, and the "Recommended workflow" note at the top of this document for what this changes day-to-day).

**Feature — backfilling all pre-existing Notion Issues (`backfill_existing_issues.py`).** A one-off script that gives every Issue that predates this tool a linked Trello card, run successfully on 9 Sep 2026: 87 total Issues found, 78 new cards created, 9 linked to already-existing cards, 0 errors. Runs as a **dry run by default** (prints exactly what it would do, changes nothing) and only executes for real with an explicit `--live` flag — deliberate, given it creates real objects on a shared team board. Safe to re-run at any time; already-linked Issues are automatically skipped.

**Near-miss caught by the dry run, worth knowing about:** the first dry-run pass showed several old Issues about to get **duplicate** Trello cards — cards with the exact same titles already existed on the board (created manually during earlier testing that same day, before this script existed). The script was extended with a name-matching check against every existing open Trello card before creating anything: an exact title match gets **linked** to the existing card instead of duplicated. This caught 9 real near-duplicates. **This same protection was NOT carried over into the live, always-running app** — see "Known limitations" at the top of this document, since that's a real residual gap worth closing.

**Bug 4 — a deleted/archived Notion page crashed the sync forever, on every retry.** Discovered 12-13 Sep 2026, during the Trello credential handover to Pete: if a Notion Issue linked to a Trello card gets deleted or archived in Notion, the app's next attempt to update that page fails with a 4xx error from Notion. Previously this error was uncaught — it crashed the whole request, Trello retried (as it does for any 5xx response the crash produced), and every retry failed identically, forever, with no way to recover except manually clearing the stale link in the database. **Fix:** the app now catches this specific failure, clears the stale mapping automatically, and creates a fresh Notion page on the same sync — so a deleted page self-heals on the next update to that card instead of crashing indefinitely. A genuine Notion server error (5xx, an outage on their end) is deliberately *not* treated this way — it still propagates and retries normally, so this fix can't accidentally mask a real outage as "page deleted." Both behaviors are directly tested (`test_app_sync.py`, `TestTrelloToNotionSelfHealing`), including a test proving a 500 error is NOT swallowed.

All bug fixes have accompanying unit tests (`test_field_mapping.py`'s `TestCanonicalFingerprint` and whitespace test, and `test_app_sync.py`'s `TestTrelloToNotionSelfHealing`) proving each specific failure mode is actually fixed, not just patched by inspection. The card-creation feature has its own dedicated tests (`test_app_sync.py`, `TestNotionToTrelloCreationGate`) proving the safety gate specifically, and the backfill script has `test_backfill.py` proving dry-run safety, error resilience, and the duplicate-linking behavior. All test files combined: 33 tests, all passing.

## 5. Non-obvious moments and nuances (learned the hard way — read this before debugging anything)

- **Trello's API Key can never be reset once created** — only the Token can be regenerated (via the account's "Applications" settings → Revoke, then generate a fresh one from the Power-Up admin page). Don't waste time looking for an API Key reset option; it doesn't exist by design.
- **Guests in a Notion workspace cannot reliably see the "Connections" panel** on a page or database — it may show misleading info (like "None" when something actually is connected, or vice versa) rather than the real state. Always verify actual access via a direct API call (`GET /v1/search`, or fetching the object directly with the integration's token) rather than trusting what a guest account sees in the UI.
- **Sharing a Notion page with an integration does NOT automatically share databases living inside that page.** Inline databases are a separate object from their containing page and need their own explicit connection. This caused most of the early setup delays.
- **Workspaces can contain old, orphaned duplicate databases with the same name as the real ones in use.** Early in this project, the URLs we were given pointed at empty, disconnected legacy "Projects"/"Issues" databases — completely different objects from the ones actually used day to day, despite identical names. If something looks unexpectedly empty, verify via a full `/v1/search` rather than assuming the URL given is correct.
- **Notion's "Status" property type and "Select" property type look identical in the UI but use different API shapes** (`{"status": {...}}` vs `{"select": {...}}`). Always check a property's actual `type` via the API before assuming.
- **Notion's `page.properties_updated` webhook events are aggregated/delayed by Notion itself**, not instant like Trello's. A short delay (up to roughly a minute) after an edit is normal, not a bug.
- **A Notion workspace can have multiple similarly-purposed integrations.** Double-check which integration a webhook is registered under actually matches the integration whose token the app is using (`GET /v1/users/me` with the app's token reveals its real name) — these can silently diverge.
- **Heroku's filesystem is wiped on every dyno restart** (which happens regularly, at least daily). This is why the app uses Postgres instead of a local SQLite file for its ID-mapping table — without that, the app would lose track of already-synced cards periodically and start creating duplicates.
- **`psycopg2-binary` doesn't always have a pre-built version for the newest Python release.** If a similar dependency fails to build during deployment with a compiler error, check whether pinning an older Python version (via `.python-version`) fixes it before assuming the dependency itself is broken.
- **`.env` must never be committed to git** — it's in `.gitignore`, verified before every push. If setting up a new environment, always double check `git status` shows `.env` is not staged before committing.

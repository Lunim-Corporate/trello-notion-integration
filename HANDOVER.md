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
- Runs continuously on its own, hosted on Heroku — no laptop, no manual triggering, no ongoing involvement needed from anyone once it's running

**Current status:** deployed, live, and both sync directions have been manually tested and confirmed working against the real Issues/Projects databases (not a sandbox).

**Immediate next step for whoever inherits this:** read Section 3 below — the Trello board this currently syncs with is tied to my personal Trello account, and that needs to change before I leave. This is the single most important thing in this document.

### Recommended workflow (read this first — it's the practical summary of everything below)

**Always create new work items in Trello, not Notion.** Once a card exists in Trello and has synced over, editing it from *either side* works fine going forward. But creation only flows one direction:

- ✅ **Create a card in Trello** → automatically appears as a new Issue in Notion → from that point on, editing Status/Due Date/Project works from either side
- ❌ **Create a new row directly in Notion** → does *not* create a Trello card. The app receives the event, finds no linked card, and does nothing (logs `"No linked Trello card ... -- skipping"`)
- ❌ **Edit a pre-existing Notion Issue** (one that existed before this tool went live) → also does nothing on the Trello side, for the same reason — it was never linked to a card in the first place

In short: **Trello is the source of truth for creating new work; Notion is where you can edit either new or already-linked items.**

### Known limitations (read before relying on this for anything important)

- **Notion → Trello card creation is not built yet.** This is the single biggest gap and the clearest "next step" for whoever picks this up. The `page.created` webhook already fires correctly and reaches the app — the missing piece is purely the logic to create a new Trello card when a page arrives with no existing link, plus writing that new pairing into the mapping table. Everything else needed (the Notion→Trello field-translation logic, the Trello API client, the mapping store) already exists and would mostly be reused; this is a meaningfully smaller task than the original build.
- **It does not match existing items by name.** If a new Trello card is created with the same name as an already-existing Notion Issue, the tool has no way of recognizing them as "the same thing" — it will create a **brand new, separate** Notion page, not link to the existing one. Matching only happens for pairs the tool itself created. This means **all the Notion Issues that existed before this tool went live are permanently unlinked** unless someone manually links them (which the tool has no feature for).
- **Assignee and Description are not synced.** These properties exist in the real schema (`Owner` for assignee, type `people`) but syncing them was never built — flagged as a possible next feature, not a bug.
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
| `Procfile` | Tells Heroku how to start the app (`gunicorn app:app`) |
| `.python-version` | Pins Python to 3.12 — required for `psycopg2-binary` to install correctly (see Section 5) |
| `requirements.txt` | Python dependencies |
| `test_field_mapping.py` | Unit tests for the translation logic — run with `python3 -m unittest test_field_mapping -v` |
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

## 4. Bugs found and fixed after initial launch (9 Sep 2026)

Three real bugs surfaced during real-world use after the initial deployment, all now fixed and confirmed working in production. Documented here because they're exactly the kind of thing that's easy to reintroduce accidentally if this code gets modified later without knowing why it's written the way it is.

**Bug 1 — stale metadata cache.** The app originally only fetched Trello's lists/labels and Notion's projects *once*, when it first started up, and never refreshed them again. When an "On Hold" list was added to the Trello board after the app was already running, the app had no idea it existed — any card moved there got mishandled (its Notion Status was silently cleared instead of set to "On Hold"). **Fix:** the cache now refreshes automatically every 5 minutes, and also force-refreshes immediately if it ever encounters an unrecognized list ID, rather than waiting for the next scheduled refresh.

**Bug 2 — echo-detection comparing incompatible data shapes.** The loop-prevention logic (which stops a Trello write from bouncing back and forth with Notion forever) was comparing a Notion-shaped payload against a Trello-shaped payload for what should have been the same underlying change — two structurally different dicts that could never actually match. This meant echoes were never correctly recognized, which combined with Bug 1 could make a card appear to "revert on its own" after being moved. **Fix:** both sync directions now build an identical, direction-independent "fingerprint" (status name, due date, sorted project ids) before comparing, so a genuine echo is reliably recognized as one.

**Bug 3 — trailing whitespace breaking Project matching.** Three real Notion projects ("Trello & Notion," "Maya Poetry Awards Campaign," "Psychological Profiling") had invisible trailing spaces in their titles, which silently broke the exact-string match against the (correctly clean) Trello label names — those three cards' Project relation just never got set, with only a log warning to show for it. **Fix:** both the Trello label name and the Notion project name are now whitespace-stripped before comparing, so this entire class of typo can't cause a silent failure again.

All three fixes have accompanying unit tests (`test_field_mapping.py`, `TestCanonicalFingerprint` and the whitespace test in `TestExtractProjectPageIds`) proving the specific failure mode is actually fixed, not just patched by inspection.

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

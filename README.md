# Trello ↔ Notion Sync (V1)

A minimal, self-hosted, webhook-driven two-way sync between the "Sprint tracker — Dashboard Pilot"
Trello board and the real **Lunim Project Tracker** in Notion. Runs on its own once deployed — no
ongoing involvement needed from either you or Claude.

## Schema this targets

The Lunim Project Tracker is **two linked databases**, not one flat table:
- **Issues** — task-level rows. This is what Trello cards sync to.
- **Projects** — one row per real project (Decision Intelligence, Tabb Slice/Upgrade, etc.).
  Issues.Project is a *relation* to this database, not a simple label.

## What it syncs

| Trello | ↔ | Notion (Issues database) |
|---|---|---|
| Card name | | Issue (title) |
| Due date | | Due Date |
| List (Backlog / On Deck / In Progress / In Review / Done / Archived) | | Status (select) |
| Label (project name, e.g. "Decision Intelligence") | | Project (relation → Projects database) |

**Not synced in V1:** Description and Assignee. These weren't visible in the Table view
screenshots we had to work from — they may exist under different names, further right in the
table, or not at all. `config.py` has `ASSIGNEE_PROPERTY_CONFIRMED` / `DESCRIPTION_PROPERTY_CONFIRMED`
flags — flip to `True` once confirmed and the code path is already there (currently gated off
rather than guessing at a property name).

## 1. Get your credentials

**Trello:**
1. Go to https://trello.com/power-ups/admin, create a Power-Up (any name), copy the **API Key**.
2. On the same page, click the **Token** link, authorize, copy the **Token**.

**Notion:**
This part can't be done by a guest — creating an internal integration requires workspace-owner
access, and guests are blocked from it entirely (Notion enforces this, not a Claude limitation).
1. **Peter** (or another Lunim workspace owner) goes to https://www.notion.so/my-integrations →
   **New integration** → internal → selects the **Lunim** workspace → copies the token.
2. He opens both the **Issues** and **Projects** databases → **•••** menu → **Connections** →
   adds the integration to each. Without this step every API call 404s.
3. He sends you the token securely (not plaintext in a channel message).

Fill the token and both data source ids into a `.env` file (copy `.env.example` — the Trello board
ID is already filled in; the two `NOTION_*_DATA_SOURCE_ID` values need to come from Peter, since
they can only be read from inside the Lunim workspace).

**Already done for you:** `.env` (not `.env.example`) has Peter's token and the Trello board ID
pre-filled — you just need your own Trello API key/token, and to run the step below for the two
Notion data source ids.

## 1b. Resolve the real Notion data source ids

```bash
pip install -r requirements.txt
python resolve_data_sources.py
```

This prints the correct `NOTION_ISSUES_DATA_SOURCE_ID` and `NOTION_PROJECTS_DATA_SOURCE_ID` values
— paste them into `.env`. (A database's URL id and its data source id aren't always the same thing
in Notion's current API, so this confirms the real ones rather than guessing.) If it prints a 404,
Peter's integration hasn't been shared with that database yet — see step 1's Notion instructions.

## 2. Install and test locally (optional but recommended)

```bash
pip install -r requirements.txt
python -m unittest test_field_mapping -v   # runs without any credentials or network access
```

## 3. Deploy

This needs to run somewhere with a public HTTPS URL and stay on continuously — webhooks can't
reach a laptop that's asleep or offline. A free-tier web service (Render, Railway, Fly.io) is
enough at this volume:

1. Push this folder to a GitHub repo.
2. On Render (or similar): **New Web Service** → connect the repo → build command
   `pip install -r requirements.txt` → start command `python app.py`.
3. Add the `.env` values as environment variables in the host's dashboard (don't commit `.env`
   itself — it's already gitignored below).
4. Deploy. Note the public URL, e.g. `https://your-app.onrender.com`.

## 4. Register the Trello webhook

```bash
python register_trello_webhook.py https://your-app.onrender.com/trello-webhook
```

Trello will send a HEAD request to that URL to confirm it's live before the webhook activates —
the app already handles that.

## 5. Register the Notion webhook

Notion webhook subscriptions are set up through the Developer portal UI, not the API:

1. Go to https://www.notion.so/my-integrations → your integration → **Webhooks** tab.
2. **Create a subscription** → URL: `https://your-app.onrender.com/notion-webhook`.
3. Notion will POST a `verification_token` to that URL once — check your host's logs for the
   line `Notion webhook verification token: ...`, then paste that token back into the Developer
   portal to confirm the subscription.
4. Subscribe to `page.properties_updated` and `page.created` events, scoped to the **Issues**
   database specifically (not Projects — this tool never writes to Projects).

## 6. Test end to end

- Move a card between lists in Trello → confirm the matching Notion Issue's Status updates.
- Edit an Issue's Status in Notion → confirm the Trello card moves lists.
- Change a Trello card's Project label → confirm the Issue's Project relation updates to point
  at the right Project row.
- Check the app logs for `Trello Project label(s) have no matching Notion Project row` warnings
  after startup — this fires if a Trello label's name doesn't exactly match a real Project name.

## Known limitations (V1 scope)

- **Assignee and Description aren't synced** — not confirmed to exist on the real Issues schema
  yet (see "Schema this targets" above). Gated behind config flags rather than guessed at.
- **New Notion rows don't create Trello cards.** The Notion → Trello direction only updates
  Issues that already have a linked Trello card (i.e., cards that originated on the Trello side).
- **Project label names must match exactly.** A Trello label like "Decision Intel" won't match
  a Notion project named "Decision Intelligence" — the match is exact-string, not fuzzy. Mismatches
  are logged as warnings on startup, not silently dropped.
- **This tool never writes to the Projects database** — only reads it, to resolve label→relation
  matches. Project rows, their Status, Timespan, etc. are untouched.
- **Maintenance:** Notion has shipped several breaking API changes through 2026. If Notion bumps
  its API version again, `NOTION_API_VERSION` in `config.py` and the property-shape assumptions
  in `field_mapping.py` may need updating.

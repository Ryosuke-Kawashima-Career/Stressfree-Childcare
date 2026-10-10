# Care & Learn integrated AI search

FastAPI serves both the HTML/CSS/JavaScript frontend and API on one origin. No separate frontend server or build is needed. The dashboard loads the SQLite directory, reveals stored matches on search and offers explicit AI refresh, shows citations and applies category/cost/vaccination filters to a cached discovery scope.

## Setup and start (PowerShell)

Run from `D:\hackathons\humanity`:

```powershell
Set-Location D:\hackathons\humanity
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m backend.app.seed --file backend/data/providers.json --validate-only
.\.venv\Scripts\python.exe -m backend.app.seed --file backend/data/providers.json
# Set this only if your server environment does not already contain the key.
$env:OPENAI_API_KEY = Read-Host 'OpenAI API key' -MaskInput
$env:CARE_LEARN_AI_MODEL = 'gpt-4.1-mini'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 4173
```

Open [the frontend](http://127.0.0.1:4173). Backend health is [here](http://127.0.0.1:4173/api/health), and registered API contracts are at [the API docs](http://127.0.0.1:4173/docs). Stop a historical static server occupying the port, or change Uvicorn to `--port 4174` and open that port. The static `http.server` command cannot handle the API calls used by this frontend. If `.venv` already exists, skip its creation.

The import initializes the schema and preserves four starting providers. Re-running it keeps discoveries in the database and avoids duplicate seed IDs. A missing database produces a readable error rather than creating a directory silently. The runtime database defaults to ignored `backend/data/caregiving.sqlite3`; `CARE_LEARN_DB_PATH` overrides it. Import and start must use the same environment/path.

## Using search

Choose Gurugram or Manesar and press Enter or **Search with AI**. The button first checks the full saved directory through `/api/reveal`, independently of the previous result scope. Leave the phrase blank to reveal the selected category/area, or try `hospitals in Gurgaon` or `Artemis`. Stored matches appear immediately on the list and map with **Stored results**, without an AI request. Category/cost/vaccination filters still apply. Clear restrictive cost/tag filters if they hide a matching hospital.

**Refresh search** requests live AI retrieval for a nonempty phrase and combines validated new discoveries with saved matches. If there are no saved matches for a submitted nonempty phrase, live discovery runs automatically. `Manipal Hospital Gurugram pediatric services` previously passed a live source-verification check; successful retrieval depends on current sources. Typing alone makes no AI request. Failed refresh retains stored results and shows a warning. **Clear filters** restores the full saved directory; the vaccination reminder also returns to the directory with its health/vaccination filter.

Details show source links, cited service relevance, checked dates, numeric latitude/longitude and the location source. The pin uses exactly the returned coordinate pair. Cards and markers use one server result set. Pending and failed searches explicitly identify retained previous results; retry is available. Reset and newer requests ignore stale responses. Cached discovery results show the retrieval timestamp; a failed refresh may show the existing valid cache with a warning.

## Server configuration and limits

`OPENAI_API_KEY` stays server-only. `.env` files are not automatically loaded; set environment variables in the shell that launches Uvicorn. Live search needs model access and outbound internet to OpenAI and approved official sources. Without a key, saved-directory filtering still works and AI submission returns a configuration error.

- `CARE_LEARN_AI_MODEL`: defaults to `gpt-4.1-mini`.
- `CARE_LEARN_SOURCE_DOMAINS`: optional comma-separated override of reviewed official provider/government domains; this replaces the default list.
- `CARE_LEARN_AI_TIMEOUT_SECONDS`: default/max 30 seconds.
- `CARE_LEARN_AI_MAX_RESULTS`: default 5, max 20.
- `CARE_LEARN_AI_MAX_OUTPUT_TOKENS`: default 6000.
- `CARE_LEARN_AI_REQUESTS_PER_MINUTE`: default 10 per server process.
- `CARE_LEARN_AI_MAX_INFLIGHT`: default 4, plus one discovery per browser session/query scope.
- `CARE_LEARN_CACHE_TTL_SECONDS`: default/max 86400 (24 hours).

The two model calls retrieve web sources and then extract structured fields from independently fetched pages. Citation excerpts/core fields and numeric coordinate evidence are checked before admission. Official HTTPS source redirects are followed for up to three allowlisted hops. Published place/JSON-LD coordinate pairs are retained even on long pages; map camera coordinates and unrelated branches are excluded. Providers without map-ready evidence are omitted with warnings. Unknown fees/hours/contact information remains unconfirmed; AI cannot certify WhatsApp support. Source/domain/coordinate admission can reduce coverage or yield no results. This directory is not a claim of current availability.

`POST /api/search` accepts optional distance/radius inputs for the future location UI; precise origins are not stored or forwarded to AI. Browser location and supported WhatsApp click-to-chat remain pending. API bodies and errors are bounded; only approved UI assets are served, never DB files, seeds or tests.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
node --check frontend/app.js
$env:NODE_PATH='C:\Users\kawas\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:CARE_LEARN_URL='http://127.0.0.1:4173'
node frontend/tests/stored-search-acceptance.cjs
node frontend/tests/backend-acceptance.cjs
node frontend/tests/acceptance.cjs
.\.venv\Scripts\python.exe .codex/skills/spec-plan-sync/scripts/verify_spec_plan_sync.py
```

Run Uvicorn first for browser tests. They use deterministic discovery/fixture routes and tile responses; they do not make paid AI calls or send messages. Backend tests use isolated temporary databases and stubbed retrieval. Live retrieval is a separate check. See [integration verification](../dev/verification/caregiving-ai-integration.md).

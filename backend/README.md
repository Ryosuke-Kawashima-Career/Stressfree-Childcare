# Care & Learn backend foundation

Phase 8 provides a single FastAPI/Uvicorn process for the existing UI and a readiness API, plus validated contracts for later directory/search/inquiry services. The frontend still fetches its existing four-provider public JSON. Search, provider details, inquiry endpoints, the schema/importer and expanded directory are pending Phases 9–12.

## Setup

Verified on Windows with Python 3.14.8 and standard-library SQLite 3.50.4. Run from `D:\hackathons\humanity`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 4173
```

Open http://127.0.0.1:4173. Stop the historical `python -m http.server` first if it occupies that port, or use `--port 4174` to keep both previews running. The frontend-only command in the root README remains usable.

## Readiness and configuration

`GET /api/health` returns 200 with `{"status":"ok","database":"ready"}` when an existing SQLite file has `PRAGMA user_version = 1`, a queryable `providers.id` column and a successful integrity check. Otherwise it returns 503 with `{"error":{"code":"database_unavailable","message":"Provider database is not ready."}}`. A fresh Phase 8 setup intentionally returns 503: Phase 9 supplies the actual schema and importer. Readiness does not create directories, tables, or DB files, and an empty directory of providers is not a data-coverage acceptance claim.

The default database is `backend/data/caregiving.sqlite3`. Override before starting:

```powershell
$env:CARE_LEARN_DB_PATH='D:\path\to\caregiving.sqlite3'
Invoke-WebRequest http://127.0.0.1:4173/api/health -SkipHttpErrorCheck
```

Relative overrides resolve from the launch directory; run from the repository root. `.venv`, caches, runtime databases and SQLite sidecars are ignored by Git. The future curated `backend/data/providers.json` is not ignored.

## Contracts and serving

`app/schemas.py` defines provider, search, location, counts, inquiry, health and application-error models. Unknown input fields are forbidden; query text is trimmed and capped at 120 characters; enums, dates, URLs, finite coordinates and radius bounds are validated. Radius requires an origin. Optional unknown provider information is nullable; WhatsApp support defaults false. Contract validation does not certify data or contact evidence; Phase 9/12 services will enforce those rules.

Only `/api/health` is implemented in this phase. `/docs` and `/openapi.json` document registered API routes. Future API request validation uses FastAPI's 422 `{"detail":[...]}` response; no request-body logging is configured. Unknown resource GETs return structured 404 errors. No database paths or stack traces are returned by readiness errors.

API registration precedes the UI route. The asset allowlist contains `/`, `/index.html`, `/app.js`, `/styles.css`, `/macos-tokens.css`, `/centers.json`, and the bundled Leaflet JS/CSS/license. No directory is broadly mounted. Tests, fixtures, backend seeds, DB files, hidden files and repository documentation are not exposed. Leaflet tiles still come from OpenStreetMap as in the current frontend.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip check
$env:NODE_PATH='C:\Users\kawas\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:CARE_LEARN_URL='http://127.0.0.1:4173'
node frontend/tests/acceptance.cjs
node --check frontend/app.js
```

The current Starlette TestClient emits a deprecation warning for HTTPX 0.28.1; tests pass with the specified HTTPX dependency. The browser suite intercepts tiles, dataset failures and fixture responses, and does not contact providers or send messages. See [Phase 8 verification](../dev/verification/caregiving-backend-phase8.md).

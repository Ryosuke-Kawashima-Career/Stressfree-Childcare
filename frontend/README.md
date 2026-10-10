# Care & Learn frontend

The frontend is served by the same FastAPI/Uvicorn process as the AI search backend. No build step or second server is required. Follow [backend setup and run instructions](../backend/README.md), then open http://127.0.0.1:4173.

Choose an area and submit with Enter or Search with AI. The button reveals matching providers from the full saved directory, including hospitals hidden by an earlier result scope. Empty input reveals the selected category/area. Stored matches need no AI call; a nonempty phrase with no saved matches continues to live discovery. Refresh explicitly retrieves new results and combines them with saved matches. Category/cost/tag filters apply to the returned scope. Clear filters restores the whole saved directory. Details include citations, checked dates and exact returned coordinates. Failed refresh keeps stored results visible with a warning.

Leaflet uses OpenStreetMap tiles and attribution. Lists/details still work when the map fails. Provider locations are approximate, and services/fees/eligibility should be confirmed with the provider. WhatsApp inquiries remain previews; browser geolocation is pending.

The historical `python -m http.server` command serves static assets but cannot run AI search. Use the integrated server for this frontend.

Browser tests: `node frontend/tests/stored-search-acceptance.cjs`, `node frontend/tests/backend-acceptance.cjs` and `node frontend/tests/acceptance.cjs`, with Uvicorn running and `CARE_LEARN_URL` pointing to it. Tests use Playwright/Chrome, deterministic fixtures, intercepted AI responses and map tiles. They preserve source/reminder, keyboard, responsive, reduced-motion, inquiry preview and failure/recovery checks. See [backend verification commands](../backend/README.md).

# Care & Learn dashboard

From `D:\hackathons\humanity` run:

```powershell
python -m http.server 4173 --bind 127.0.0.1 --directory frontend
```

Open http://127.0.0.1:4173. No install or build is required for the dashboard. Use HTTP so local JSON loads.

The map uses locally bundled **Leaflet 1.9.4** and real OpenStreetMap tiles with attribution, geographic markers, zoom, and pan. Internet access is required for tiles; the list and details remain usable when tiles or the map library fail. A tile error exposes a Retry action. Leaflet's license is in `vendor/leaflet/LICENSE`. No bulk tile downloads or offline tile cache are used.

The public dashboard shows two hospitals (Medanta and Artemis) and two learning centers (Udayan Care Dundahera and Manesar). Source links and checked dates appear in provider details. Published pins are approximate areas, not confirmed entrances. Fees, hours, eligibility, and vaccination availability remain unconfirmed. The health reminder links a dated [MoHFW/PIB immunization announcement](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2227422) from 13 February 2026. WhatsApp inquiries remain previews.

Six fictional examples are isolated in `tests/fixtures/centers.json`, not shown in the public directory. Tests route those fixtures only for vaccination/free-learning/unknown-contact scenarios. Public unsupported vaccination/free filters correctly show an empty state.

Review flows:
1. Select a hospital or learning center from the list or geographic marker; inspect its details and prepare an inquiry.
2. Open the health announcement; use vaccination discovery, then reset.
3. Search Udayan, combine category/cost filters, and test unmatched search/reset.

## Browser acceptance

Requires Playwright and installed Chrome. In the Codex bundled runtime:

```powershell
$env:NODE_PATH='C:\Users\kawas\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
node frontend/tests/acceptance.cjs
node --check frontend/app.js
python .codex/skills/spec-plan-sync/scripts/verify_spec_plan_sync.py
```

Run the server first. `CARE_LEARN_URL` can override the preview URL; `PLAYWRIGHT_CHANNEL` overrides Chrome. Checks cover matching marker/list IDs, sources/totals, both core flows, unknown fields, keyboard focus, five viewport widths, reduced motion, and data/tile/library failures and recovery. Results and screenshots are saved in `dev/verification/`. The browser suite uses deterministic tile responses. Run `node frontend/tests/capture-preview.cjs` separately for real OSM tiles and desktop/phone evidence. See [Phase 7 acceptance](../dev/verification/caregiving-phase7.md).

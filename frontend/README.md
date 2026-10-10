# Care & Learn dashboard

From `D:\hackathons\humanity` run:

```powershell
python -m http.server 4173 --bind 127.0.0.1 --directory frontend
```

Open http://127.0.0.1:4173. No install or build is required for the dashboard. Use HTTP so local JSON loads.

The map uses locally bundled **Leaflet 1.9.4** and real OpenStreetMap tiles with attribution, geographic markers, zoom, and pan. Internet access is required for tiles; the list and details remain usable when tiles or the map library fail. A tile error exposes a Retry action. Leaflet's license is in `vendor/leaflet/LICENSE`. No bulk tile downloads or offline tile cache are used.

The dashboard includes two published hospitals (Medanta and Artemis), two published learning centers (Udayan Care Dundahera and Manesar IT centres), and six clearly labeled fictional demo examples. Published addresses, contacts, and training descriptions come from official websites checked on 2026-10-10. Source links and dates appear in details. Published pins are approximate area positions, not confirmed entrances. The IT centres offer vocational/technology training; child eligibility, current fees, hours, and availability are not confirmed. Demo vaccination and free-learning examples remain fictional. WhatsApp inquiries are previews; no message is sent.

Review flows:
1. Vaccination banner → labeled health example → contextual inquiry preview.
2. Clear filters → Learning + Free → demo learning marker → general inquiry preview.
3. Search hospital or Udayan → published information, contact, official source, checked date, map precision.
4. Unmatched search → empty results → reset; selected centers clear when excluded.

## Browser acceptance

Requires Playwright and installed Chrome. In the Codex bundled runtime:

```powershell
$env:NODE_PATH='C:\Users\kawas\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
node frontend/tests/acceptance.cjs
node --check frontend/app.js
python .codex/skills/spec-plan-sync/scripts/verify_spec_plan_sync.py
```

Run the server first. `CARE_LEARN_URL` can override the preview URL; `PLAYWRIGHT_CHANNEL` overrides Chrome. Checks cover matching marker/list IDs, sources/totals, both core flows, unknown fields, keyboard focus, five viewport widths, reduced motion, and data/tile/library failures and recovery. Results and screenshots are saved in `dev/verification/`. See [Phase 6 acceptance](../dev/verification/caregiving-phase6.md).

# Care & Learn

Helps a caregiver in Gurgaon find a child health center or free learning center, inspect its details, and prepare a WhatsApp inquiry.

The public dashboard includes four sourced providers; fictional examples are isolated in test fixtures. Confirm details with a provider. Published map pins show approximate areas, not confirmed entrances.

## Architecture

A static single-page UI with an optional FastAPI backend foundation. Phase 8 serves the existing UI and `/api/health` in one process; provider search/import and UI integration remain pending. See [backend setup](backend/README.md). No accounts, geocoding, or location permission yet.

```text
centers.json ──fetch──> app.js ──render──> index.html + styles.css
                          │
                          ├─ filter state (search, category, cost, vaccination tag)
                          ├─ selected-center ID
                          └─ shared filter predicate ──> results list + map pins
```

- **Data:** local JSON, two published hospitals, two published learning centers, with six isolated test fixtures (three Health, three Learning) with coordinates, services, cost status, and contact/demo status.
- **State:** one filter state and one selected-center ID. A single filter predicate feeds both the list and the map, so they always agree. A selection that is filtered out is cleared.
- **Detail card:** one reusable card for list and map selection. It shows address, services, cost, contact, source links, and checked dates. Unknown optional fields show "Not confirmed".
- **Inquiry:** contextual message previews; external WhatsApp integration remains deferred.
- **Map:** locally bundled Leaflet 1.9.4 with real OpenStreetMap tiles, visible attribution, geographic markers, and tile-failure retry. List/details still work if the map is unavailable.

## Directory structure

```text
.
├── frontend/          Runnable app (HTML/CSS/JS, no build step)
│   ├── index.html     Page markup
│   ├── styles.css     Styling
│   ├── app.js         Filters, selection, rendering, inquiry preview
│   ├── centers.json   Published provider and demo data
│   └── README.md      Frontend preview and review notes
└── dev/
    ├── specs/         Requirements and specification
    └── plans/         Implementation plan
```

## Set up and run

Requires Python 3 (any static file server works). No install or build step.

From the repository root:

```powershell
python -m http.server 4173 --bind 127.0.0.1 --directory frontend
```

Open <http://127.0.0.1:4173>. Serve over HTTP rather than opening `index.html` directly, because the app fetches `centers.json`.

To open it from a phone on the same network, bind to all interfaces (`--bind 0.0.0.0`) and browse to `http://<computer-ip>:4173`. This may need an inbound firewall rule for the port.

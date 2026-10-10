# Care & Learn

Helps a caregiver in Gurgaon find a child health center or free learning center, inspect its details, and prepare a WhatsApp inquiry.

All data is fictional demo data. Confirm details with a provider.

## Architecture

A static single-page app. No backend, accounts, geocoding, or location permission.

```text
centers.json ──fetch──> app.js ──render──> index.html + styles.css
                          │
                          ├─ filter state (search, category, cost, vaccination tag)
                          ├─ selected-center ID
                          └─ shared filter predicate ──> results list + map pins
```

- **Data:** local JSON, six demo centers (three Health, three Learning) with coordinates, services, cost status, and contact/demo status.
- **State:** one filter state and one selected-center ID. A single filter predicate feeds both the list and the map, so they always agree. A selection that is filtered out is cleared.
- **Detail card:** one reusable card for list and map selection. It shows address, services, cost, contact, and demo status. Unknown optional fields show "Not confirmed".
- **Inquiry:** a valid WhatsApp number opens `https://wa.me/<digits>?text=<encoded-message>`. Demo records show a message preview instead.
- **Map:** currently a labeled local illustration. Leaflet with OpenStreetMap tiles (with visible attribution) is planned.

## Directory structure

```text
.
├── frontend/          Runnable app (HTML/CSS/JS, no build step)
│   ├── index.html     Page markup
│   ├── styles.css     Styling
│   ├── app.js         Filters, selection, rendering, inquiry preview
│   ├── centers.json   Demo center data
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

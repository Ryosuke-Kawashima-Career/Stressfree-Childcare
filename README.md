# Care & Learn

Helps a caregiver in Gurgaon find a child health center or free learning center, inspect its details, and prepare a WhatsApp inquiry.

The public dashboard includes four sourced providers; fictional examples are isolated in test fixtures. Confirm details with a provider. Published map pins show approximate areas, not confirmed entrances.

## Architecture

A single FastAPI/Uvicorn process serves the frontend and backend. SQLite holds the starting directory and source-backed AI discoveries. Explicit Submit/Enter calls `/api/discover`; category/cost/tag filters reuse the result scope through `/api/search`. Cards and Leaflet pins share the same response. Details show citations, relevance and checked dates. WhatsApp remains a message preview; browser location is pending.

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

Follow [backend setup](backend/README.md) to install dependencies, initialize the SQLite directory, configure the server AI key/model, and start:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 4173
```

Open [Care & Learn](http://127.0.0.1:4173). This one process runs both frontend and backend; no frontend build is needed. Enter a phrase and press Enter or Search with AI. A static file server cannot run the AI search API.

# Parcel Dispatch

Parcel Dispatch is a local package tracking and delivery-planning web app built with FastAPI, Jinja2, HTMX, and SQLite. It supports package and truck management, delivery-status lookups, nearest-neighbor route planning, a configurable simulation distance matrix, and optional road routing through OpenRouteService. Dispatching plans a route and places its packages in transit; an operator confirms each completed delivery from Tracking.

The database is initialized automatically on first run with fictional Exampleville demo data. Replace the sample packages and depot with your own records before using the app operationally. Demo distances are illustrative, not real-world measurements.

## Run locally

Requires Python 3.10 or later.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Open `http://127.0.0.1:8000`. The application stores data in `data/delivery.sqlite3` by default. Set `DATABASE_PATH` to use a different SQLite file. Use `/health` for a database-readiness check and `/docs` for the generated API documentation.

## Routing

Simulation mode uses the distance matrix managed on the Settings page and assumes a truck speed of 18 mph. Add a distance for each new address pair before dispatching a package in simulation mode.

Provider mode uses OpenRouteService geocoding and driving distances/ETAs. Set `OPENROUTESERVICE_API_KEY` in the server environment before selecting provider routing. You can override the API base with `OPENROUTESERVICE_BASE_URL`. Provider failures are surfaced to the operator; the app does not silently treat an unavailable road route as a successful simulation. Review OpenRouteService's current plan limits and terms before operational use.

PowerShell example:

```powershell
$env:OPENROUTESERVICE_API_KEY = "your-key"
python main.py
```

This initial version is designed for a single trusted local operator and has no authentication or CSRF protection. Do not expose it directly to the public internet. Use fictional or appropriately protected data for demos.

## Tests

Run the full test suite:

```powershell
python -m unittest discover -s tests -v
```

Run one test module:

```powershell
python -m unittest tests.test_domain -v
```

There is no separate build or lint configuration yet.

# Repository instructions

## Commands

- Install: `python -m pip install -r requirements.txt`
- Run locally: `python main.py` and open `http://127.0.0.1:8000`.
- Health/readiness endpoint: `GET /health` returns `{"status":"ok"}` when SQLite is available, otherwise HTTP 503.
- Run all tests: `python -m unittest discover -s tests -v`.
- Run one test module: `python -m unittest tests.test_domain -v` (replace the module name to target another file).
- There is no configured lint command or separate build step.

## Architecture

- `delivery/main.py` defines the FastAPI routes, JSON endpoints, and app lifespan. It renders Jinja2 templates from `templates/`; HTMX updates package search and dispatch results.
- `delivery/database.py` owns the SQLite schema, connection lifecycle, and fictional first-run demo data. The database path is configurable with `DATABASE_PATH`.
- `delivery/domain.py` holds the package/route types and nearest-neighbor route planner. `delivery/routing.py` supplies the matrix-backed simulation and OpenRouteService implementations.
- `templates/` contains server-rendered pages and fragments; `static/styles.css` provides local styles. `main.py` is the import-safe development-server entry point.
- Dispatch creates a planned route and moves packages from pending to in-transit; operators confirm actual completion from Tracking. Keep ETA separate from actual delivery timestamps.

## Project-specific conventions

- Keep route selection behind the routing implementations. Provider and simulation failures must be visible to the operator; never silently report a fallback route as provider-calculated.
- Simulation dispatch requires configured distances for each address pair, including the depot. Add or update bidirectional values through Settings.
- Keep SQL parameterized and use the `session()` context manager for database access so connections close and writes roll back on exceptions.
- External provider credentials are read from environment variables. Do not store API keys in source, templates, test fixtures, or SQLite.
- Demo addresses and distances are fictional and explicitly labeled as examples. Do not reintroduce school-specific identifiers, student details, or prior project data.
- Copilot skill guidance lives in `.github/skills/<name>/SKILL.md`; keep each skill focused on repository-specific commands and workflows.

---
name: fastapi-htmx-workflows
description: Use when changing Parcel Dispatch FastAPI routes, Jinja2 templates, HTMX interactions, or JSON endpoints.
---

# FastAPI, Jinja2, and HTMX workflows

- Route handlers and application startup are in `delivery/main.py`; the app object is `delivery.main:app`.
- Render HTML through `_render()` and templates in `templates/`. Keep browser interactions server-rendered; HTMX-enhanced forms must retain a normal `action`/`method` fallback where applicable.
- Use `HX-Request` to return partial HTML for requests that target a fragment. Keep fragment IDs and HTMX target/swap behavior in sync.
- The `/api/` routes return JSON alongside the HTML interface. Preserve both surfaces when changing package or truck data behavior.
- Form submissions use FastAPI `Form` fields and redirect with HTTP 303 after successful create/update operations. Validate user-selected truck IDs before writing.
- Dispatch marks stops in transit; the Tracking action confirms actual delivery and must not be conflated with a route ETA.
- Run route/UI tests with `python -m unittest tests.test_web -v`; use the full suite with `python -m unittest discover -s tests -v`.
- The app is single-operator and local-only; do not treat it as safe for public deployment without adding authentication, CSRF protection, and deployment hardening.

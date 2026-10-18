---
name: parcel-dispatch-testing
description: Use when adding or running tests for Parcel Dispatch domain logic, SQLite behavior, web routes, or routing integration.
---

# Project testing workflows

- Tests use the Python standard-library `unittest` runner; run all tests with `python -m unittest discover -s tests -v`.
- Run an individual module with `python -m unittest tests.test_domain -v` or `python -m unittest tests.test_web -v`.
- Domain tests belong in `tests/test_domain.py`; HTTP/UI and persistence tests belong in `tests/test_web.py`; provider request/response mapping tests belong in `tests/test_routing.py`.
- Use temporary SQLite files and FastAPI's `TestClient`. Do not use or modify the default local database in tests.
- Keep routing tests offline: exercise the matrix-backed router and mock provider HTTP responses or assert missing-credential errors.
- Dependencies needed by the application and HTTP test client (`httpx2` for the current Starlette test client) are listed in `requirements.txt`.

---
name: sqlite-data-workflows
description: Use when changing Parcel Dispatch SQLite schema, persistence, package records, truck assignments, or delivery history.
---

# SQLite persistence workflows

- Schema creation, first-run seed data, and database path configuration live in `delivery/database.py`.
- Use `session()` for database work. It commits successful work, rolls back exceptions, and always closes the connection.
- Use SQL placeholders for all user-provided values. Add schema constraints for valid statuses and non-negative quantities when extending persisted fields.
- Keep estimated arrival (`deliveries.eta_at`) distinct from actual completion (`packages.delivered_at` and `deliveries.completed_at`).
- Default storage is `data/delivery.sqlite3`; tests should use a temporary database path rather than the real local database.
- Keep first-run sample rows fictional, generic, and clearly marked as demo data. Never seed actual customer or school-project information.
- Verify changes with `python -m unittest tests.test_web -v` and `python -m unittest discover -s tests -v`.

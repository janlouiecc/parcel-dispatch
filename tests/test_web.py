import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import delivery.main as web


class WebApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.database_patch = patch.object(web, "DATABASE_PATH", self.database_path)
        self.database_patch.start()
        self.client_context = TestClient(web.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_home_and_packages_page_render_seeded_demo(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.get("/packages")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Demo Recipient A", response.text)
        self.assertIn("Exampleville", response.text)

    def test_health_endpoint_checks_database(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

        with patch.object(web, "DATABASE_PATH", self.temp_dir.name):
            unavailable = self.client.get("/health")
        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(unavailable.json()["detail"], "Database is unavailable.")

    def test_package_creation_and_json_lookup(self):
        response = self.client.post(
            "/packages",
            data={
                "recipient": "Test Customer",
                "address": "10 Test Street",
                "city": "Testville",
                "state": "TS",
                "postal_code": "12345",
                "deadline": "End of day",
                "weight_kg": "2.5",
                "notes": "",
                "truck_id": "3",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        packages = self.client.get("/api/packages").json()
        package = next(row for row in packages if row["recipient"] == "Test Customer")
        self.assertEqual(package["status"], "pending")
        self.assertEqual(package["truck_id"], 3)

    def test_simulation_dispatch_records_deliveries_and_tracking(self):
        response = self.client.post(
            "/dispatch",
            data={"truck_id": "1", "mode": "simulation"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("route planned", response.text)
        packages = self.client.get("/api/packages").json()
        truck_one = [package for package in packages if package["truck_id"] == 1]
        self.assertTrue(all(package["status"] == "in_transit" for package in truck_one))

        self.assertEqual(
            self.client.post("/packages/1/deliver", follow_redirects=False).status_code,
            303,
        )
        packages = self.client.get("/api/packages").json()
        self.assertEqual(next(row for row in packages if row["id"] == 1)["status"], "delivered")
        self.assertEqual(next(row for row in packages if row["id"] == 2)["status"], "in_transit")

        tracking = self.client.get("/tracking?as_of=2100-01-01T00%3A00")
        self.assertIn("Delivered", tracking.text)
        past_tracking = self.client.get("/tracking?as_of=2000-01-01T00%3A00")
        self.assertIn("Pending", past_tracking.text)

    def test_provider_error_is_reported_without_changing_package_status(self):
        with patch.dict(os.environ, {"OPENROUTESERVICE_API_KEY": ""}):
            response = self.client.post(
                "/dispatch",
                data={"truck_id": "1", "mode": "provider"},
            )

        self.assertIn("requires OPENROUTESERVICE_API_KEY", response.text)
        packages = self.client.get("/api/packages").json()
        truck_one = [package for package in packages if package["truck_id"] == 1]
        self.assertTrue(all(package["status"] == "pending" for package in truck_one))

    def test_settings_adds_symmetric_simulation_distance(self):
        response = self.client.post(
            "/settings",
            data={
                "hub_address": "Central Depot, Exampleville",
                "from_address": "10 Test Street",
                "to_address": "20 Test Street",
                "distance_miles": "4.2",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        with web.session(self.database_path) as connection:
            distances = connection.execute(
                "SELECT distance_miles FROM distance_matrix "
                "WHERE (from_address = ? AND to_address = ?) "
                "OR (from_address = ? AND to_address = ?)",
                ("10 Test Street", "20 Test Street", "20 Test Street", "10 Test Street"),
            ).fetchall()
        self.assertEqual([row["distance_miles"] for row in distances], [4.2, 4.2])


if __name__ == "__main__":
    unittest.main()

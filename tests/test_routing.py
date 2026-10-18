import json
import unittest
from unittest.mock import patch

from delivery.domain import Package
from delivery.routing import OpenRouteServiceRouter


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.payload


class OpenRouteServiceRouterTests(unittest.TestCase):
    def test_geocodes_locations_and_uses_provider_distances_and_durations(self):
        responses = [
            FakeResponse({"features": [{"geometry": {"coordinates": [0, 0]}}]}),
            FakeResponse({"features": [{"geometry": {"coordinates": [1, 0]}}]}),
            FakeResponse({"features": [{"geometry": {"coordinates": [2, 0]}}]}),
            FakeResponse({
                "distances": [[0, 4, 1], [4, 0, 2], [1, 2, 0]],
                "durations": [[0, 600, 180], [600, 0, 300], [180, 300, 0]],
            }),
        ]
        router = OpenRouteServiceRouter(api_key="test-key")
        with patch("delivery.routing.urlopen", side_effect=responses) as urlopen:
            route = router.plan("Depot", [Package(1, "Market"), Package(2, "Oak")])

        self.assertEqual([leg.package_id for leg in route], [2, 1, None])
        self.assertEqual([leg.distance_miles for leg in route], [1, 2, 4])
        self.assertEqual([leg.duration_minutes for leg in route], [3, 5, 10])
        self.assertEqual(urlopen.call_count, 4)
        self.assertTrue(all(
            call.args[0].get_header("Authorization") == "test-key"
            for call in urlopen.call_args_list
        ))


if __name__ == "__main__":
    unittest.main()

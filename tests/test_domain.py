import unittest

from delivery.domain import Package, nearest_neighbor_route


class NearestNeighborRouteTests(unittest.TestCase):
    def test_visits_nearest_remaining_package_and_returns_to_origin(self):
        distances = {
            ("Depot", "Market"): 2.0,
            ("Depot", "Oak"): 3.0,
            ("Market", "Oak"): 1.0,
            ("Market", "Depot"): 2.0,
            ("Oak", "Depot"): 3.0,
            ("Oak", "Market"): 1.0,
        }
        packages = [Package(2, "Oak"), Package(1, "Market")]

        route = nearest_neighbor_route("Depot", packages, lambda a, b: distances[(a, b)])

        self.assertEqual([leg.package_id for leg in route], [1, 2, None])
        self.assertEqual([leg.distance_miles for leg in route], [2.0, 1.0, 3.0])
        self.assertAlmostEqual(route[0].duration_minutes, 2.0 / 18 * 60)

    def test_ties_are_broken_by_package_id(self):
        route = nearest_neighbor_route(
            "Depot",
            [Package(4, "Oak"), Package(2, "Market")],
            lambda _a, _b: 1.0,
        )

        self.assertEqual([leg.package_id for leg in route], [2, 4, None])

    def test_rejects_negative_distance(self):
        with self.assertRaisesRegex(ValueError, "non-negative"):
            nearest_neighbor_route("Depot", [Package(1, "Market")], lambda _a, _b: -1.0)


if __name__ == "__main__":
    unittest.main()

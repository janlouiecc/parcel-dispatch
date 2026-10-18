import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from delivery.domain import Package, RouteLeg, nearest_neighbor_route


class RoutingError(Exception):
    """An actionable routing or geocoding failure."""


class SimulationRouter:
    def __init__(self, connection):
        self.distances = {
            (row["from_address"], row["to_address"]): row["distance_miles"]
            for row in connection.execute(
                "SELECT from_address, to_address, distance_miles FROM distance_matrix"
            )
        }

    def plan(self, origin: str, packages: list[Package]) -> list[RouteLeg]:
        def distance_between(start: str, end: str) -> float:
            if start == end:
                return 0.0
            try:
                return self.distances[(start, end)]
            except KeyError as error:
                raise RoutingError(
                    f"No simulation distance is configured between {start} and {end}. "
                    "Add the distance in Settings or use provider routing."
                ) from error

        return nearest_neighbor_route(origin, packages, distance_between)


class OpenRouteServiceRouter:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 15):
        self.api_key = api_key or os.environ.get("OPENROUTESERVICE_API_KEY", "")
        self.base_url = (base_url or os.environ.get(
            "OPENROUTESERVICE_BASE_URL", "https://api.openrouteservice.org"
        )).rstrip("/")
        self.timeout = timeout
        self._geocoded: dict[str, tuple[float, float]] = {}
        if not self.api_key:
            raise RoutingError(
                "Provider routing requires OPENROUTESERVICE_API_KEY. "
                "Set it in the server environment or use simulation mode."
            )

    def plan(self, origin: str, packages: list[Package]) -> list[RouteLeg]:
        addresses = list(dict.fromkeys([origin, *(package.address for package in packages)]))
        coordinates = [self._geocode(address) for address in addresses]
        distances, durations = self._route_matrix(coordinates)
        address_indexes = {address: index for index, address in enumerate(addresses)}

        def distance_between(start: str, end: str) -> float:
            return distances[address_indexes[start]][address_indexes[end]]

        def duration_between(start: str, end: str) -> float:
            return durations[address_indexes[start]][address_indexes[end]]

        return nearest_neighbor_route(
            origin, packages, distance_between, duration_between=duration_between
        )

    def _geocode(self, address: str) -> tuple[float, float]:
        if address not in self._geocoded:
            query = urlencode({"text": address, "size": 1})
            response = self._request("GET", f"/geocode/search?{query}")
            features = response.get("features", [])
            if not features:
                raise RoutingError(f"The routing provider could not find an address for: {address}")
            try:
                longitude, latitude = features[0]["geometry"]["coordinates"]
            except (KeyError, TypeError, ValueError) as error:
                raise RoutingError("The routing provider returned an invalid geocoding result.") from error
            self._geocoded[address] = (longitude, latitude)
        return self._geocoded[address]

    def _route_matrix(
        self, coordinates: list[tuple[float, float]]
    ) -> tuple[list[list[float]], list[list[float]]]:
        response = self._request(
            "POST",
            "/v2/matrix/driving-car",
            {
                "locations": [list(coordinate) for coordinate in coordinates],
                "metrics": ["distance", "duration"],
                "units": "mi",
            },
        )
        distances = response.get("distances")
        durations = response.get("durations")
        if (
            not isinstance(distances, list)
            or not isinstance(durations, list)
            or len(distances) != len(coordinates)
            or len(durations) != len(coordinates)
        ):
            raise RoutingError("The routing provider returned an incomplete route matrix.")
        try:
            if any(len(row) != len(coordinates) for row in distances + durations):
                raise ValueError
            return (
                [[float(value) for value in row] for row in distances],
                [[float(value) / 60 for value in row] for row in durations],
            )
        except (TypeError, ValueError) as error:
            raise RoutingError("The routing provider returned invalid route values.") from error

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "LocalPackageDeliveryPlanner/1.0",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code in (401, 403):
                raise RoutingError(
                    "The routing provider rejected its API key. Check OPENROUTESERVICE_API_KEY."
                ) from error
            raise RoutingError(f"The routing provider returned HTTP {error.code}.") from error
        except (URLError, TimeoutError) as error:
            raise RoutingError("The routing provider could not be reached. Check connectivity and retry.") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RoutingError("The routing provider returned an unreadable response.") from error

        if not isinstance(result, dict):
            raise RoutingError("The routing provider returned an invalid response.")
        provider_error = result.get("error")
        if provider_error:
            message = (
                provider_error.get("message", "The provider could not calculate this route.")
                if isinstance(provider_error, dict)
                else provider_error
            )
            raise RoutingError(str(message))
        return result

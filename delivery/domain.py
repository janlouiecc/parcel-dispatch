from dataclasses import dataclass
from math import isfinite
from typing import Callable, Iterable


@dataclass(frozen=True)
class Package:
    package_id: int
    address: str


@dataclass(frozen=True)
class RouteLeg:
    package_id: int | None
    address: str
    distance_miles: float
    duration_minutes: float


def nearest_neighbor_route(
    origin: str,
    packages: Iterable[Package],
    distance_between: Callable[[str, str], float],
    speed_mph: float = 18.0,
    duration_between: Callable[[str, str], float] | None = None,
) -> list[RouteLeg]:
    """Plan package stops greedily by the shortest next leg, then return to origin."""
    if speed_mph <= 0:
        raise ValueError("Truck speed must be greater than zero.")

    pending = list(packages)
    current = origin
    route = []

    while pending:
        candidates = []
        for package in pending:
            distance = distance_between(current, package.address)
            if not isfinite(distance) or distance < 0:
                raise ValueError("Route distances must be finite and non-negative.")
            candidates.append((distance, package.package_id, package))

        distance, _, package = min(candidates, key=lambda item: (item[0], item[1]))
        duration = (
            duration_between(current, package.address)
            if duration_between
            else distance / speed_mph * 60
        )
        if not isfinite(duration) or duration < 0:
            raise ValueError("Route durations must be finite and non-negative.")
        route.append(RouteLeg(
            package.package_id,
            package.address,
            distance,
            duration,
        ))
        pending.remove(package)
        current = package.address

    return_distance = distance_between(current, origin)
    if not isfinite(return_distance) or return_distance < 0:
        raise ValueError("Route distances must be finite and non-negative.")
    return_duration = (
        duration_between(current, origin)
        if duration_between
        else return_distance / speed_mph * 60
    )
    if not isfinite(return_duration) or return_duration < 0:
        raise ValueError("Route durations must be finite and non-negative.")
    route.append(RouteLeg(None, origin, return_distance, return_duration))
    return route

---
name: delivery-routing-workflows
description: Use when changing route planning, the simulation distance matrix, geocoding, or OpenRouteService integration.
---

# Delivery routing workflows

- Nearest-neighbor stop ordering and route-leg types are defined in `delivery/domain.py`.
- `delivery/routing.py` provides `SimulationRouter` and `OpenRouteServiceRouter`; dispatch chooses the implementation explicitly from the operator's selected mode.
- Simulation requires a configured bidirectional mileage for each address pair, including the configured depot. Manage the hub and matrix from `/settings`.
- Provider mode uses the OpenRouteService geocode and driving-matrix endpoints. Read `OPENROUTESERVICE_API_KEY` and optional `OPENROUTESERVICE_BASE_URL` from the server environment; never persist or log the key.
- Provider failures raise `RoutingError` and are shown to the operator. Do not convert provider errors into a successful simulated route.
- Preserve estimated leg durations, miles, and ETAs in delivery history. Planning a route moves packages into transit; actual delivery requires explicit confirmation. Test planning with the deterministic matrix demo fixtures and do not call the external provider in tests.

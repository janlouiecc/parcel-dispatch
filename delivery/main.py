import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from delivery.database import DEFAULT_DATABASE_PATH, initialize_database, session
from delivery.domain import Package
from delivery.routing import OpenRouteServiceRouter, RoutingError, SimulationRouter


PROJECT_ROOT = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", str(DEFAULT_DATABASE_PATH)))


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database(DATABASE_PATH)
    yield


app = FastAPI(title="Parcel Dispatch", description="Local package tracking and delivery route planning.", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")


@app.get("/health")
def health_check():
    try:
        with session(DATABASE_PATH) as connection:
            connection.execute("SELECT 1")
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from error
    return {"status": "ok"}


def _render(request: Request, template: str, status_code: int = 200, **context):
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={"request": request, **context},
        status_code=status_code,
    )


def _dispatch_error(request: Request, message: str):
    return _render(request, "dispatch_result.html", error=message)


def _trucks(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute("SELECT id, name, capacity FROM trucks ORDER BY id")]


def _hub_address(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT value FROM settings WHERE key = 'hub_address'").fetchone()
    return row["value"] if row else ""


def _formatted_address(record: sqlite3.Row | dict) -> str:
    return ", ".join(
        part for part in (
            record["address"],
            record["city"],
            " ".join(part for part in (record["state"], record["postal_code"]) if part),
        ) if part
    )


def _validate_package_fields(
    recipient: str,
    address: str,
    city: str,
    state: str,
    postal_code: str,
    weight_kg: float,
) -> None:
    if any(not value.strip() for value in (recipient, address, city, state, postal_code)):
        raise HTTPException(status_code=400, detail="Recipient and complete destination fields are required.")
    if not isfinite(weight_kg) or weight_kg < 0:
        raise HTTPException(status_code=400, detail="Weight must be a finite, non-negative number.")


def _package_row(connection: sqlite3.Connection, package_id: int) -> dict | None:
    row = connection.execute(
        """
        SELECT p.*, t.name AS truck_name
        FROM packages p LEFT JOIN trucks t ON p.truck_id = t.id
        WHERE p.id = ?
        """,
        (package_id,),
    ).fetchone()
    if not row:
        return None
    package = dict(row)
    package["full_address"] = _formatted_address(package)
    return package


def _package_list(connection: sqlite3.Connection, query: str = "", status: str = "") -> list[dict]:
    filters = []
    values = []
    if query:
        pattern = f"%{query.strip()}%"
        filters.append("(CAST(p.id AS TEXT) LIKE ? OR p.recipient LIKE ? OR p.address LIKE ?)")
        values.extend([pattern, pattern, pattern])
    if status in {"pending", "in_transit", "delivered"}:
        filters.append("p.status = ?")
        values.append(status)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = connection.execute(
        f"""
        SELECT p.*, t.name AS truck_name,
            (
                SELECT d.eta_at FROM deliveries d
                WHERE d.package_id = p.id ORDER BY d.id DESC LIMIT 1
            ) AS eta_at
        FROM packages p
        LEFT JOIN trucks t ON p.truck_id = t.id
        {where} ORDER BY p.id
        """,
        values,
    )
    packages = [dict(row) for row in rows]
    for package in packages:
        package["full_address"] = _formatted_address(package)
    return packages


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with session(DATABASE_PATH) as connection:
        counts = {
            row["status"]: row["total"]
            for row in connection.execute("SELECT status, COUNT(*) AS total FROM packages GROUP BY status")
        }
        recent = _package_list(connection)[:8]
        return _render(
            request,
            "dashboard.html",
            counts={status: counts.get(status, 0) for status in ("pending", "in_transit", "delivered")},
            recent=recent,
            truck_count=connection.execute("SELECT COUNT(*) FROM trucks").fetchone()[0],
        )


@app.get("/packages", response_class=HTMLResponse)
def packages_page(request: Request, q: str = "", status: str = ""):
    with session(DATABASE_PATH) as connection:
        packages = _package_list(connection, q, status)
        context = {"packages": packages, "q": q, "status": status}
        if request.headers.get("HX-Request") == "true":
            return _render(request, "partials/package_table.html", **context)
        return _render(request, "packages.html", **context)


@app.get("/packages/new", response_class=HTMLResponse)
def new_package_page(request: Request):
    with session(DATABASE_PATH) as connection:
        return _render(request, "package_form.html", package=None, trucks=_trucks(connection))


@app.post("/packages")
def create_package(
    recipient: str = Form(min_length=1, max_length=120),
    address: str = Form(min_length=1, max_length=240),
    city: str = Form(min_length=1, max_length=100),
    state: str = Form(min_length=1, max_length=80),
    postal_code: str = Form(min_length=1, max_length=20),
    deadline: str = Form(default="End of day", max_length=80),
    weight_kg: float = Form(default=0, ge=0),
    notes: str = Form(default="", max_length=1000),
    truck_id: int = Form(default=0, ge=0),
):
    _validate_package_fields(recipient, address, city, state, postal_code, weight_kg)
    with session(DATABASE_PATH) as connection:
        if truck_id and not connection.execute("SELECT 1 FROM trucks WHERE id = ?", (truck_id,)).fetchone():
            raise HTTPException(status_code=400, detail="Selected truck does not exist.")
        connection.execute(
            """
            INSERT INTO packages
                (recipient, address, city, state, postal_code, deadline, weight_kg, notes, truck_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (recipient.strip(), address.strip(), city.strip(), state.strip(), postal_code.strip(),
             deadline.strip() or "End of day", weight_kg, notes.strip(), truck_id or None),
        )
    return RedirectResponse("/packages", status_code=303)


@app.get("/packages/{package_id}/edit", response_class=HTMLResponse)
def edit_package_page(request: Request, package_id: int):
    with session(DATABASE_PATH) as connection:
        package = _package_row(connection, package_id)
        if package is None:
            raise HTTPException(status_code=404, detail="Package not found.")
        return _render(request, "package_form.html", package=package, trucks=_trucks(connection))


@app.post("/packages/{package_id}/edit")
def update_package(
    package_id: int,
    recipient: str = Form(min_length=1, max_length=120),
    address: str = Form(min_length=1, max_length=240),
    city: str = Form(min_length=1, max_length=100),
    state: str = Form(min_length=1, max_length=80),
    postal_code: str = Form(min_length=1, max_length=20),
    deadline: str = Form(default="End of day", max_length=80),
    weight_kg: float = Form(default=0, ge=0),
    notes: str = Form(default="", max_length=1000),
    truck_id: int = Form(default=0, ge=0),
):
    _validate_package_fields(recipient, address, city, state, postal_code, weight_kg)
    with session(DATABASE_PATH) as connection:
        if not connection.execute("SELECT 1 FROM packages WHERE id = ?", (package_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Package not found.")
        if truck_id and not connection.execute("SELECT 1 FROM trucks WHERE id = ?", (truck_id,)).fetchone():
            raise HTTPException(status_code=400, detail="Selected truck does not exist.")
        connection.execute(
            """
            UPDATE packages SET recipient = ?, address = ?, city = ?, state = ?,
                postal_code = ?, deadline = ?, weight_kg = ?, notes = ?, truck_id = ?
            WHERE id = ?
            """,
            (recipient.strip(), address.strip(), city.strip(), state.strip(), postal_code.strip(),
             deadline.strip() or "End of day", weight_kg, notes.strip(), truck_id or None, package_id),
        )
    return RedirectResponse("/packages", status_code=303)


@app.get("/trucks", response_class=HTMLResponse)
def trucks_page(request: Request):
    with session(DATABASE_PATH) as connection:
        trucks = connection.execute(
            """
            SELECT t.id, t.name, t.capacity, COUNT(p.id) AS package_count,
                SUM(CASE WHEN p.status != 'delivered' THEN 1 ELSE 0 END) AS undelivered_count
            FROM trucks t LEFT JOIN packages p ON p.truck_id = t.id
            GROUP BY t.id ORDER BY t.id
            """
        )
        return _render(request, "trucks.html", trucks=[dict(row) for row in trucks])


@app.post("/trucks")
def create_truck(name: str = Form(min_length=1, max_length=80), capacity: int = Form(default=16, gt=0, le=100)):
    if not name.strip():
        raise HTTPException(status_code=400, detail="Truck name cannot be blank.")
    try:
        with session(DATABASE_PATH) as connection:
            connection.execute("INSERT INTO trucks (name, capacity) VALUES (?, ?)", (name.strip(), capacity))
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=400, detail="A truck with that name already exists.") from error
    return RedirectResponse("/trucks", status_code=303)


@app.get("/dispatch", response_class=HTMLResponse)
def dispatch_page(request: Request, error: str = "", message: str = ""):
    with session(DATABASE_PATH) as connection:
        trucks = connection.execute(
            """
            SELECT t.id, t.name, COUNT(p.id) AS pending_count
            FROM trucks t LEFT JOIN packages p ON p.truck_id = t.id AND p.status = 'pending'
            GROUP BY t.id ORDER BY t.id
            """
        )
        return _render(
            request,
            "dispatch.html",
            trucks=[dict(row) for row in trucks],
            error=error,
            message=message,
        )


@app.post("/dispatch", response_class=HTMLResponse)
def dispatch(
    request: Request,
    truck_id: int = Form(gt=0),
    mode: str = Form(default="simulation"),
):
    if mode not in {"simulation", "provider"}:
        raise HTTPException(status_code=400, detail="Select simulation or provider routing.")

    with session(DATABASE_PATH) as connection:
        truck_row = connection.execute("SELECT * FROM trucks WHERE id = ?", (truck_id,)).fetchone()
        if truck_row is None:
            raise HTTPException(status_code=404, detail="Truck not found.")
        truck = dict(truck_row)
        rows = connection.execute(
            """
            SELECT id, address, city, state, postal_code FROM packages
            WHERE truck_id = ? AND status = 'pending' ORDER BY id
            """,
            (truck_id,),
        ).fetchall()
        if not rows:
            return _dispatch_error(request, f"{truck['name']} has no pending packages assigned.")
        if len(rows) > truck["capacity"]:
            return _dispatch_error(
                request,
                f"{truck['name']} has {len(rows)} undelivered packages, above its "
                f"capacity of {truck['capacity']}.",
            )
        packages = [Package(row["id"], _formatted_address(row)) for row in rows]
        origin = _hub_address(connection)
        simulation_router = SimulationRouter(connection) if mode == "simulation" else None

    try:
        router = simulation_router or OpenRouteServiceRouter()
        route = router.plan(origin, packages)
    except RoutingError as error:
        return _dispatch_error(request, str(error))
    except ValueError as error:
        return _dispatch_error(request, str(error))

    with session(DATABASE_PATH) as connection:
        current_time = datetime.now(timezone.utc).replace(microsecond=0)
        dispatched_at = current_time.isoformat(timespec="seconds")
        results = []
        total_miles = 0.0
        for sequence, leg in enumerate(route, start=1):
            total_miles += leg.distance_miles
            eta_time = datetime.fromtimestamp(
                current_time.timestamp() + leg.duration_minutes * 60,
                tz=timezone.utc,
            )
            eta_at = eta_time.isoformat(timespec="seconds")
            if leg.package_id is not None:
                updated = connection.execute(
                    """
                    UPDATE packages SET status = 'in_transit', dispatched_at = ?
                    WHERE id = ? AND truck_id = ? AND status = 'pending'
                    """,
                    (dispatched_at, leg.package_id, truck_id),
                )
                if updated.rowcount != 1:
                    raise HTTPException(
                        status_code=409,
                        detail="A package changed while the route was being planned. Retry dispatch.",
                    )
                results.append({
                    "package_id": leg.package_id,
                    "address": leg.address,
                    "distance_miles": leg.distance_miles,
                    "eta_at": eta_at,
                })
            connection.execute(
                """
                INSERT INTO deliveries
                    (truck_id, package_id, sequence, address, distance_miles,
                     duration_minutes, eta_at, routing_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (truck_id, leg.package_id, sequence, leg.address, leg.distance_miles,
                 leg.duration_minutes, eta_at, mode),
            )

    return _render(
        request,
        "dispatch_result.html",
        truck_name=truck["name"],
        route=results,
        total_miles=total_miles,
        mode=mode,
        error="",
    )


@app.get("/tracking", response_class=HTMLResponse)
def tracking_page(request: Request, as_of: str = "", error: str = ""):
    with session(DATABASE_PATH) as connection:
        packages = _package_list(connection)
    if as_of:
        try:
            point = datetime.fromisoformat(as_of)
            if point.tzinfo is None:
                point = point.replace(tzinfo=timezone.utc)
            point = point.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            return _render(
                request, "tracking.html", packages=packages, as_of=as_of,
                error="Enter a valid date and time.",
            )
        for package in packages:
            delivered_at = package["delivered_at"]
            dispatched_at = package["dispatched_at"]
            if delivered_at and delivered_at <= point:
                package["status_at_time"] = "delivered"
            elif dispatched_at and dispatched_at <= point:
                package["status_at_time"] = "in_transit"
            else:
                package["status_at_time"] = "pending"
    else:
        for package in packages:
            package["status_at_time"] = package["status"]
    return _render(request, "tracking.html", packages=packages, as_of=as_of, error=error)


@app.post("/packages/{package_id}/deliver")
def mark_package_delivered(package_id: int):
    delivered_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat(timespec="seconds")
    with session(DATABASE_PATH) as connection:
        updated = connection.execute(
            """
            UPDATE packages SET status = 'delivered', delivered_at = ?
            WHERE id = ? AND status = 'in_transit'
            """,
            (delivered_at, package_id),
        )
        if updated.rowcount == 0:
            exists = connection.execute("SELECT 1 FROM packages WHERE id = ?", (package_id,)).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="Package not found.")
            raise HTTPException(status_code=409, detail="Only an in-transit package can be marked delivered.")
        connection.execute(
            """
            UPDATE deliveries SET completed_at = ?
            WHERE id = (
                SELECT id FROM deliveries WHERE package_id = ? ORDER BY id DESC LIMIT 1
            )
            """,
            (delivered_at, package_id),
        )
    return RedirectResponse("/tracking", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, message: str = "", error: str = ""):
    with session(DATABASE_PATH) as connection:
        distances = [
            dict(row) for row in connection.execute(
                "SELECT from_address, to_address, distance_miles FROM distance_matrix "
                "WHERE from_address < to_address ORDER BY from_address, to_address"
            )
        ]
        return _render(
            request,
            "settings.html",
            hub_address=_hub_address(connection),
            distances=distances,
            message=message,
            error=error,
        )


@app.post("/settings")
def update_settings(
    hub_address: str = Form(min_length=1, max_length=240),
    from_address: str = Form(default="", max_length=240),
    to_address: str = Form(default="", max_length=240),
    distance_miles: float = Form(default=0, ge=0),
):
    if not hub_address.strip():
        raise HTTPException(status_code=400, detail="Depot address cannot be blank.")
    if not isfinite(distance_miles) or distance_miles < 0:
        raise HTTPException(status_code=400, detail="Distance must be a finite, non-negative number.")
    if bool(from_address.strip()) != bool(to_address.strip()):
        raise HTTPException(status_code=400, detail="Enter both addresses to add a simulation distance.")
    if from_address.strip() == to_address.strip() and from_address.strip():
        raise HTTPException(status_code=400, detail="Same-address distance is always zero.")
    with session(DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO settings (key, value) VALUES ('hub_address', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (hub_address.strip(),),
        )
        if from_address.strip() and to_address.strip():
            connection.executemany(
                """
                INSERT INTO distance_matrix (from_address, to_address, distance_miles)
                VALUES (?, ?, ?)
                ON CONFLICT(from_address, to_address) DO UPDATE SET distance_miles = excluded.distance_miles
                """,
                [
                    (from_address.strip(), to_address.strip(), distance_miles),
                    (to_address.strip(), from_address.strip(), distance_miles),
                ],
            )
    return RedirectResponse("/settings?message=Settings saved.", status_code=303)


@app.get("/api/packages")
def packages_api():
    with session(DATABASE_PATH) as connection:
        return _package_list(connection)


@app.get("/api/packages/{package_id}")
def package_api(package_id: int):
    with session(DATABASE_PATH) as connection:
        package = _package_row(connection, package_id)
        if package is None:
            raise HTTPException(status_code=404, detail="Package not found.")
        return package


@app.get("/api/trucks")
def trucks_api():
    with session(DATABASE_PATH) as connection:
        return _trucks(connection)

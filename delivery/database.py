import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


DEFAULT_DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "data/delivery.sqlite3"))

DEMO_HUB = "Central Depot, Exampleville"
DEMO_ADDRESSES = [
    "100 Market Street",
    "25 Oak Avenue",
    "8 River Road",
    "50 Pine Lane",
]


def connect(database_path: Path | str = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def session(database_path: Path | str = DEFAULT_DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    connection = connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: Path | str = DEFAULT_DATABASE_PATH) -> None:
    with session(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trucks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                capacity INTEGER NOT NULL DEFAULT 16 CHECK (capacity > 0)
            );

            CREATE TABLE IF NOT EXISTS packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient TEXT NOT NULL,
                address TEXT NOT NULL,
                city TEXT NOT NULL,
                state TEXT NOT NULL,
                postal_code TEXT NOT NULL,
                deadline TEXT NOT NULL DEFAULT 'End of day',
                weight_kg REAL NOT NULL DEFAULT 0 CHECK (weight_kg >= 0),
                notes TEXT NOT NULL DEFAULT '',
                truck_id INTEGER REFERENCES trucks(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'in_transit', 'delivered')),
                dispatched_at TEXT,
                delivered_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                truck_id INTEGER NOT NULL REFERENCES trucks(id),
                package_id INTEGER REFERENCES packages(id),
                sequence INTEGER NOT NULL,
                address TEXT NOT NULL,
                distance_miles REAL NOT NULL CHECK (distance_miles >= 0),
                duration_minutes REAL NOT NULL CHECK (duration_minutes >= 0),
                eta_at TEXT,
                completed_at TEXT,
                routing_mode TEXT NOT NULL CHECK (routing_mode IN ('simulation', 'provider'))
            );

            CREATE TABLE IF NOT EXISTS distance_matrix (
                from_address TEXT NOT NULL,
                to_address TEXT NOT NULL,
                distance_miles REAL NOT NULL CHECK (distance_miles >= 0),
                PRIMARY KEY (from_address, to_address)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        _seed_demo_data(connection)


def _seed_demo_data(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT 1 FROM trucks LIMIT 1").fetchone():
        return

    connection.executemany(
        "INSERT INTO trucks (name, capacity) VALUES (?, ?)",
        [("Truck 1", 16), ("Truck 2", 16), ("Truck 3", 16)],
    )
    connection.execute(
        "INSERT INTO settings (key, value) VALUES ('hub_address', ?)",
        (DEMO_HUB,),
    )

    distances = [
        [0.0, 2.1, 3.8, 5.0, 1.7],
        [2.1, 0.0, 1.9, 3.2, 2.6],
        [3.8, 1.9, 0.0, 2.4, 3.1],
        [5.0, 3.2, 2.4, 0.0, 4.5],
        [1.7, 2.6, 3.1, 4.5, 0.0],
    ]
    addresses = [DEMO_HUB, *(f"{address}, Exampleville, EX {index:05d}"
                              for index, address in enumerate(DEMO_ADDRESSES, start=1))]
    connection.executemany(
        """
        INSERT INTO distance_matrix (from_address, to_address, distance_miles)
        VALUES (?, ?, ?)
        """,
        [
            (addresses[row], addresses[column], distances[row][column])
            for row in range(len(addresses))
            for column in range(len(addresses))
        ],
    )

    connection.executemany(
        """
        INSERT INTO packages
            (recipient, address, city, state, postal_code, deadline, weight_kg, notes, truck_id)
        VALUES (?, ?, 'Exampleville', 'EX', ?, ?, ?, 'Fictional demo order', ?)
        """,
        [
            ("Demo Recipient A", DEMO_ADDRESSES[0], "00001", "End of day", 2.0, 1),
            ("Demo Recipient B", DEMO_ADDRESSES[1], "00002", "End of day", 1.5, 1),
            ("Demo Recipient C", DEMO_ADDRESSES[2], "00003", "End of day", 3.0, 2),
            ("Demo Recipient D", DEMO_ADDRESSES[3], "00004", "End of day", 0.8, 2),
        ],
    )

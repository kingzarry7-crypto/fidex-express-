import os
import random
import sqlite3
from datetime import datetime, timezone

# On Vercel, store the SQLite database file in the writeable /tmp folder
DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "/tmp/packages.db" if os.getenv("VERCEL") else "packages.db"
)


def get_connection():
    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_number TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'Registered',
            current_location TEXT NOT NULL,
            recipient_name TEXT NOT NULL,
            recipient_email TEXT,
            sender_name TEXT,
            sender_address TEXT,
            recipient_address TEXT,
            origin TEXT,
            destination TEXT,
            package_description TEXT,
            weight REAL,
            shipping_service TEXT,
            shipping_cost REAL,
            estimated_delivery TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tracking_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_number TEXT NOT NULL,
            status TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def generate_tracking_number():
    conn = get_connection()
    cursor = conn.cursor()

    while True:
        number = random.randint(10000000, 99999999)
        tracking = f"FDX{number}"

        cursor.execute(
            """
            SELECT tracking_number
            FROM packages
            WHERE tracking_number = ?
            """,
            (tracking,)
        )

        existing = cursor.fetchone()

        if not existing:
            conn.close()
            return tracking


def add_tracking_event(
    tracking_number,
    status,
    location,
    description=None
):
    conn = get_connection()
    cursor = conn.cursor()

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    cursor.execute(
        """
        INSERT INTO tracking_events
        (
            tracking_number,
            status,
            location,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            tracking_number,
            status,
            location,
            description,
            created_at
        )
    )

    conn.commit()
    conn.close()


def initialize():
    init_db()

import os
import secrets
from datetime import datetime, timezone
import psycopg
from psycopg.rows import dict_row

# Vercel automatically populates DATABASE_URL or POSTGRES_URL when Neon is linked
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")


def get_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL environment variable is not configured.")
    
    # Returns row objects as dictionaries to match original sqlite3 row_factory behavior
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS packages (
            id SERIAL PRIMARY KEY,
            tracking_number VARCHAR(100) UNIQUE NOT NULL,
            status VARCHAR(100) NOT NULL DEFAULT 'Registered',
            current_location VARCHAR(255) NOT NULL,
            recipient_name VARCHAR(255) NOT NULL,
            recipient_email VARCHAR(255),
            sender_name VARCHAR(255),
            sender_address TEXT,
            recipient_address TEXT,
            origin VARCHAR(255),
            destination VARCHAR(255),
            package_description TEXT,
            weight REAL,
            shipping_service VARCHAR(100),
            shipping_cost REAL,
            estimated_delivery VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tracking_events (
            id SERIAL PRIMARY KEY,
            tracking_number VARCHAR(100) NOT NULL,
            status VARCHAR(100) NOT NULL,
            location VARCHAR(255) NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        );
        """
    )

    conn.commit()
    conn.close()


def generate_tracking_number():
    conn = get_connection()
    cursor = conn.cursor()

    while True:
        number = secrets.randbelow(90000000) + 10000000
        tracking = f"FDX{number}"

        cursor.execute(
            """
            SELECT tracking_number
            FROM packages
            WHERE tracking_number = %s
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

    created_at = datetime.now(timezone.utc).isoformat()

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
        VALUES (%s, %s, %s, %s, %s)
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

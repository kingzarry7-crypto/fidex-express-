import os
import secrets
from datetime import datetime, timezone
import psycopg
from psycopg.rows import dict_row

# Retrieves connection string provided by Vercel / Neon
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")


def get_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is missing on Vercel.")
    
    # SSL mode required for Neon / Vercel cloud Postgres instances
    url = DATABASE_URL
    if "sslmode=" not in url:
        url += "?sslmode=require" if "?" not in url else "&sslmode=require"

    return psycopg.connect(url, row_factory=dict_row)


def init_db():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
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
    except Exception as err:
        if conn:
            conn.rollback()
        print("Database initialization warning:", err)
    finally:
        if conn:
            conn.close()


def generate_tracking_number():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
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
                    return tracking
    finally:
        conn.close()


def add_tracking_event(
    tracking_number,
    status,
    location,
    description=None
):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
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
    except Exception as err:
        conn.rollback()
        raise err
    finally:
        conn.close()


def initialize():
    init_db()

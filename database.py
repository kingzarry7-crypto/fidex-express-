import os
import sqlite3
from datetime import datetime, timezone


# =========================================================
# 👑 FIDEX EXPRESS DATABASE
# SQLite development database
#
# Production:
# Use PostgreSQL through DATABASE_URL.
# =========================================================

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "packages.db"
)


def get_db_connection():
    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def init_db():

    conn = get_db_connection()
    cursor = conn.cursor()


    # =====================================================
    # PACKAGES TABLE
    # =====================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS packages (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tracking_number TEXT UNIQUE NOT NULL,

            status TEXT NOT NULL
                DEFAULT 'Registered',

            current_location TEXT NOT NULL
                DEFAULT 'Shipment Center',

            recipient_name TEXT NOT NULL,

            recipient_email TEXT,

            sender_name TEXT,

            sender_address TEXT,

            recipient_address TEXT,

            origin TEXT,

            destination TEXT,

            package_description TEXT,

            weight REAL,

            shipping_service TEXT
                DEFAULT 'Standard Shipping',

            shipping_cost REAL,

            estimated_delivery TEXT,

            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL
        )
        """
    )


    # =====================================================
    # TRACKING HISTORY TABLE
    # =====================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tracking_history (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tracking_number TEXT NOT NULL,

            status TEXT NOT NULL,

            location TEXT NOT NULL,

            description TEXT,

            created_at TEXT NOT NULL,

            FOREIGN KEY (
                tracking_number
            )
            REFERENCES packages (
                tracking_number
            )
        )
        """
    )


    # =====================================================
    # INDEXES
    # =====================================================

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_packages_tracking
        ON packages(tracking_number)
        """
    )


    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_tracking_history_number
        ON tracking_history(tracking_number)
        """
    )


    # =====================================================
    # DO NOT CREATE FAKE CUSTOMER PACKAGES
    #
    # We intentionally do NOT insert:
    #
    # FDX12345678
    #
    # Packages should only be created by the admin
    # dashboard.
    # =====================================================


    conn.commit()
    conn.close()

    print(
        "✅ Fidex Express database initialized successfully."
    )


# =========================================================
# RUN DIRECTLY
# =========================================================

if __name__ == "__main__":
    init_db()

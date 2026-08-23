import os
import secrets
import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# =========================================================
# 👑 FIDEX EXPRESS API
# Admin-only package registration + real tracking
# =========================================================

app = FastAPI(
    title="Fidex Express Tracking API",
    version="2.0.0",
)


# =========================================================
# CONFIG
# =========================================================

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "Fedexg217@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Frontend URL.
# Example:
# https://fidex-express-git-vercel-ins-137a0d-kingzarry7-cryptos-projects.vercel.app
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")

DATABASE_PATH = os.getenv("DATABASE_PATH", "packages.db")


# =========================================================
# CORS
# =========================================================

allowed_origins = ["*"] if FRONTEND_URL == "*" else [
    FRONTEND_URL.rstrip("/")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


# =========================================================
# DATABASE
# =========================================================

def get_db_connection():
    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Main packages table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tracking_number TEXT UNIQUE NOT NULL,

            status TEXT NOT NULL DEFAULT 'Registered',

            current_location TEXT NOT NULL DEFAULT 'Shipment Center',

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

            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL
        )
        """
    )

    # Tracking history
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tracking_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tracking_number TEXT NOT NULL,

            status TEXT NOT NULL,

            location TEXT NOT NULL,

            description TEXT,

            created_at TEXT NOT NULL,

            FOREIGN KEY (tracking_number)
                REFERENCES packages(tracking_number)
        )
        """
    )

    conn.commit()
    conn.close()


init_database()


# =========================================================
# HELPERS
# =========================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def generate_tracking_number():
    """
    Generates tracking numbers such as:

    FID123456789012
    """

    while True:
        number = secrets.randbelow(900000000000) + 100000000000
        tracking = f"FID{number}"

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM packages WHERE tracking_number = ?",
            (tracking,)
        )

        exists = cursor.fetchone()

        conn.close()

        if not exists:
            return tracking


def verify_admin(
    x_admin_email: Optional[str] = Header(default=None),
    x_admin_password: Optional[str] = Header(default=None),
):
    """
    Simple admin authentication.

    The frontend/admin dashboard sends:

    X-Admin-Email
    X-Admin-Password
    """

    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_PASSWORD is not configured on the server"
        )

    if x_admin_email != ADMIN_EMAIL:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials"
        )

    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials"
        )

    return True


# =========================================================
# MODELS
# =========================================================

class PackageCreate(BaseModel):
    recipient_name: str = Field(..., min_length=1)
    recipient_email: Optional[str] = None

    sender_name: Optional[str] = None
    sender_address: Optional[str] = None

    recipient_address: Optional[str] = None

    origin: str = "Shipment Center"
    destination: str

    package_description: Optional[str] = None

    weight: Optional[float] = None

    shipping_service: str = "Standard Shipping"

    shipping_cost: Optional[float] = None

    estimated_delivery: Optional[str] = None


class PackageUpdate(BaseModel):
    status: str
    current_location: str
    description: Optional[str] = None


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():
    return {
        "status": "Fidex Express API is running",
        "version": "2.0.0",
        "service": "Fidex Express",
    }


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "database": "connected",
        "time": utc_now(),
    }


# =========================================================
# ADMIN LOGIN CHECK
# =========================================================

@app.post("/api/admin/login")
def admin_login(
    x_admin_email: Optional[str] = Header(default=None),
    x_admin_password: Optional[str] = Header(default=None),
):
    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_PASSWORD has not been configured"
        )

    if x_admin_email != ADMIN_EMAIL:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    return {
        "success": True,
        "message": "Admin authentication successful",
        "email": ADMIN_EMAIL,
    }


# =========================================================
# PUBLIC PACKAGE TRACKING
# =========================================================

@app.get("/api/track/{tracking_num}")
def track_package(tracking_num: str):

    tracking_num = tracking_num.strip().upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            tracking_number,
            status,
            current_location,
            recipient_name,
            origin,
            destination,
            package_description,
            weight,
            shipping_service,
            estimated_delivery,
            created_at,
            updated_at
        FROM packages
        WHERE tracking_number = ?
        """,
        (tracking_num,)
    )

    package = cursor.fetchone()

    if not package:
        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Tracking number not found"
        )

    cursor.execute(
        """
        SELECT
            status,
            location,
            description,
            created_at
        FROM tracking_history
        WHERE tracking_number = ?
        ORDER BY id ASC
        """,
        (tracking_num,)
    )

    history = [
        dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    result = dict(package)
    result["history"] = history

    return result


# =========================================================
# ADMIN: REGISTER PACKAGE
# =========================================================

@app.post(
    "/api/packages",
    dependencies=[Depends(verify_admin)]
)
def create_package(pkg: PackageCreate):

    conn = get_db_connection()
    cursor = conn.cursor()

    tracking_number = generate_tracking_number()
    now = utc_now()

    try:

        cursor.execute(
            """
            INSERT INTO packages (
                tracking_number,
                status,
                current_location,
                recipient_name,
                recipient_email,
                sender_name,
                sender_address,
                recipient_address,
                origin,
                destination,
                package_description,
                weight,
                shipping_service,
                shipping_cost,
                estimated_delivery,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tracking_number,
                "Registered",
                pkg.origin,
                pkg.recipient_name,
                pkg.recipient_email,
                pkg.sender_name,
                pkg.sender_address,
                pkg.recipient_address,
                pkg.origin,
                pkg.destination,
                pkg.package_description,
                pkg.weight,
                pkg.shipping_service,
                pkg.shipping_cost,
                pkg.estimated_delivery,
                now,
                now,
            )
        )

        cursor.execute(
            """
            INSERT INTO tracking_history (
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
                "Registered",
                pkg.origin,
                "Package successfully registered.",
                now,
            )
        )

        conn.commit()

    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Unable to register package"
        )

    conn.close()

    return {
        "success": True,
        "message": "Package successfully registered",
        "tracking_number": tracking_number,
        "status": "Registered",
        "data": {
            "tracking_number": tracking_number,
            "recipient_name": pkg.recipient_name,
            "recipient_email": pkg.recipient_email,
            "origin": pkg.origin,
            "destination": pkg.destination,
            "shipping_service": pkg.shipping_service,
            "shipping_cost": pkg.shipping_cost,
            "estimated_delivery": pkg.estimated_delivery,
        }
    }


# =========================================================
# ADMIN: LIST PACKAGES
# =========================================================

@app.get(
    "/api/admin/packages",
    dependencies=[Depends(verify_admin)]
)
def admin_packages():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM packages
        ORDER BY id DESC
        """
    )

    packages = [
        dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    return {
        "success": True,
        "count": len(packages),
        "packages": packages,
    }


# =========================================================
# ADMIN: UPDATE PACKAGE
# =========================================================

@app.patch(
    "/api/admin/packages/{tracking_num}",
    dependencies=[Depends(verify_admin)]
)
def update_package(
    tracking_num: str,
    update: PackageUpdate
):

    tracking_num = tracking_num.strip().upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id
        FROM packages
        WHERE tracking_number = ?
        """,
        (tracking_num,)
    )

    package = cursor.fetchone()

    if not package:
        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Tracking number not found"
        )

    now = utc_now()

    cursor.execute(
        """
        UPDATE packages
        SET
            status = ?,
            current_location = ?,
            updated_at = ?
        WHERE tracking_number = ?
        """,
        (
            update.status,
            update.current_location,
            now,
            tracking_num,
        )
    )

    cursor.execute(
        """
        INSERT INTO tracking_history (
            tracking_number,
            status,
            location,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            tracking_num,
            update.status,
            update.current_location,
            update.description,
            now,
        )
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Package status updated",
        "tracking_number": tracking_num,
        "status": update.status,
        "current_location": update.current_location,
    }


# =========================================================
# ADMIN: GET SINGLE PACKAGE
# =========================================================

@app.get(
    "/api/admin/packages/{tracking_num}",
    dependencies=[Depends(verify_admin)]
)
def admin_get_package(tracking_num: str):

    tracking_num = tracking_num.strip().upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM packages
        WHERE tracking_number = ?
        """,
        (tracking_num,)
    )

    package = cursor.fetchone()

    if not package:
        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Tracking number not found"
        )

    cursor.execute(
        """
        SELECT *
        FROM tracking_history
        WHERE tracking_number = ?
        ORDER BY id ASC
        """,
        (tracking_num,)
    )

    history = [
        dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    result = dict(package)
    result["history"] = history

    return result


# =========================================================
# ADMIN: DELETE PACKAGE
# =========================================================

@app.delete(
    "/api/admin/packages/{tracking_num}",
    dependencies=[Depends(verify_admin)]
)
def delete_package(tracking_num: str):

    tracking_num = tracking_num.strip().upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id
        FROM packages
        WHERE tracking_number = ?
        """,
        (tracking_num,)
    )

    package = cursor.fetchone()

    if not package:
        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Tracking number not found"
        )

    cursor.execute(
        """
        DELETE FROM tracking_history
        WHERE tracking_number = ?
        """,
        (tracking_num,)
    )

    cursor.execute(
        """
        DELETE FROM packages
        WHERE tracking_number = ?
        """,
        (tracking_num,)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Package deleted",
        "tracking_number": tracking_num,
    }

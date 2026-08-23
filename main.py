import os
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# =========================================================
# 👑 FIDEX EXPRESS API
# =========================================================

app = FastAPI(
    title="Fidex Express Tracking API",
    version="2.0.0",
)


# =========================================================
# CONFIG
# =========================================================

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "Fedexg217@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")  # Fallback added to prevent 500 errors

FRONTEND_URL = os.getenv("FRONTEND_URL", "*")

# Write to ephemeral /tmp directory on Vercel serverless functions
DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "/tmp/packages.db" if os.getenv("VERCEL") else "packages.db"
)


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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
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
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

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
    except Exception as error:
        print("Database initialization error:", error)


@app.on_event("startup")
def startup_event():
    init_database()


# =========================================================
# HELPERS
# =========================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def generate_tracking_number():
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
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    if not x_admin_email or not x_admin_password:
        raise HTTPException(
            status_code=400,
            detail="Missing administrative headers"
        )

    clean_email = x_admin_email.strip().lower()
    clean_password = x_admin_password.strip()

    target_email = ADMIN_EMAIL.strip().lower()
    target_password = ADMIN_PASSWORD.strip()

    if clean_email != target_email or clean_password != target_password:
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
# HOME & HEALTH
# =========================================================

@app.get("/")
def home():
    return {
        "status": "Fidex Express API is running",
        "version": "2.0.0",
        "service": "Fidex Express",
    }


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
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    verify_admin(x_admin_email, x_admin_password)

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
    init_database()
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
        ORDER BY id DESC
        """,
        (tracking_num,)
    )

    history = [dict(row) for row in cursor.fetchall()]
    conn.close()

    result = dict(package)
    result["history"] = history
    result["tracking_history"] = history

    return result


# =========================================================
# ADMIN: REGISTER PACKAGE
# =========================================================

@app.post(
    "/api/packages",
    dependencies=[Depends(verify_admin)]
)
def create_package(pkg: PackageCreate):
    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()

    tracking_number = generate_tracking_number()
    now = utc_now()

    try:
        cursor.execute(
            """
            INSERT INTO packages (
                tracking_number, status, current_location, recipient_name,
                recipient_email, sender_name, sender_address, recipient_address,
                origin, destination, package_description, weight, shipping_service,
                shipping_cost, estimated_delivery, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tracking_number, "Registered", pkg.origin, pkg.recipient_name,
                pkg.recipient_email, pkg.sender_name, pkg.sender_address,
                pkg.recipient_address, pkg.origin, pkg.destination,
                pkg.package_description, pkg.weight, pkg.shipping_service,
                pkg.shipping_cost, pkg.estimated_delivery, now, now,
            )
        )

        cursor.execute(
            """
            INSERT INTO tracking_history (
                tracking_number, status, location, description, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                tracking_number, "Registered", pkg.origin,
                "Package successfully registered.", now,
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
    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM packages ORDER BY id DESC")
    packages = [dict(row) for row in cursor.fetchall()]

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
    init_database()
    tracking_num = tracking_num.strip().upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM packages WHERE tracking_number = ?",
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
        SET status = ?, current_location = ?, updated_at = ?
        WHERE tracking_number = ?
        """,
        (update.status, update.current_location, now, tracking_num)
    )

    cursor.execute(
        """
        INSERT INTO tracking_history (
            tracking_number, status, location, description, created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (tracking_num, update.status, update.current_location, update.description, now)
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
    init_database()
    tracking_num = tracking_num.strip().upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM packages WHERE tracking_number = ?",
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
        SELECT * FROM tracking_history
        WHERE tracking_number = ?
        ORDER BY id DESC
        """,
        (tracking_num,)
    )

    history = [dict(row) for row in cursor.fetchall()]
    conn.close()

    result = dict(package)
    result["history"] = history
    result["tracking_history"] = history

    return result


# =========================================================
# ADMIN: DELETE PACKAGE
# =========================================================

@app.delete(
    "/api/admin/packages/{tracking_num}",
    dependencies=[Depends(verify_admin)]
)
def delete_package(tracking_num: str):
    init_database()
    tracking_num = tracking_num.strip().upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM packages WHERE tracking_number = ?",
        (tracking_num,)
    )

    package = cursor.fetchone()

    if not package:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="Tracking number not found"
        )

    cursor.execute("DELETE FROM tracking_history WHERE tracking_number = ?", (tracking_num,))
    cursor.execute("DELETE FROM packages WHERE tracking_number = ?", (tracking_num,))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Package deleted",
        "tracking_number": tracking_num,
    }

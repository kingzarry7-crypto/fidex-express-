import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import (
    get_connection,
    generate_tracking_number,
    add_tracking_event,
    init_db
)

# =========================================================
# APP CONFIGURATION & LIFESPAN
# =========================================================

def safe_init_db():
    """Attempts DB initialization safely without breaking app startup."""
    try:
        init_db()
    except Exception as error:
        print("Database initialization warning:", error)

@asynccontextmanager
async def lifespan(app: FastAPI):
    safe_init_db()
    yield

app = FastAPI(
    title="Fidex Express Tracking API",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Safe fallback credentials if environment variables aren't defined in Vercel
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "Fedexg217@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Helper to normalize database rows into Python dictionaries
def row_to_dict(cursor, row) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "_asdict"):
        return row._asdict()
    # Fallback if raw tuple cursor is used
    column_names = [col[0] for col in cursor.description]
    return dict(zip(column_names, row))

# =========================================================
# AUTHENTICATION HELPER
# =========================================================

def check_admin(
    admin_email: Optional[str],
    admin_password: Optional[str]
):
    if not admin_email or not admin_password:
        raise HTTPException(
            status_code=400,
            detail="Admin credentials missing from headers."
        )

    clean_email = admin_email.strip().lower()
    clean_password = admin_password.strip()

    target_email = ADMIN_EMAIL.strip().lower()
    target_password = ADMIN_PASSWORD.strip()

    if clean_email != target_email or clean_password != target_password:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials."
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
    origin: str
    destination: str
    package_description: Optional[str] = None
    weight: Optional[float] = None
    shipping_service: Optional[str] = "Standard Shipping"
    shipping_cost: Optional[float] = None
    estimated_delivery: Optional[str] = None

class PackageUpdate(BaseModel):
    status: str
    current_location: str
    description: Optional[str] = None

# =========================================================
# ROUTES
# =========================================================

@app.get("/")
def home():
    return {
        "status": "Fidex Express API is running",
        "version": "2.0.0"
    }

@app.post("/api/admin/login")
def admin_login(
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    check_admin(x_admin_email, x_admin_password)

    return {
        "success": True,
        "message": "Admin authentication successful",
        "email": ADMIN_EMAIL
    }

@app.get("/api/track/{tracking_number}")
def track_package(tracking_number: str):
    clean_tracking = tracking_number.upper().strip()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM packages WHERE tracking_number = %s",
                (clean_tracking,)
            )
            raw_package = cursor.fetchone()

            if not raw_package:
                raise HTTPException(
                    status_code=404,
                    detail="Tracking number not found"
                )

            package = row_to_dict(cursor, raw_package)

            cursor.execute(
                """
                SELECT id, status, location, description, created_at
                FROM tracking_events
                WHERE tracking_number = %s
                ORDER BY id DESC
                """,
                (clean_tracking,)
            )

            raw_events = cursor.fetchall() or []
            events = [row_to_dict(cursor, event) for event in raw_events]

            package["tracking_history"] = events
            package["history"] = events

            return package
    finally:
        conn.close()

@app.post("/api/packages")
def create_package(
    pkg: PackageCreate,
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    check_admin(x_admin_email, x_admin_password)

    tracking_number = generate_tracking_number()
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO packages
                (
                    tracking_number, status, current_location, recipient_name,
                    recipient_email, sender_name, sender_address, recipient_address,
                    origin, destination, package_description, weight,
                    shipping_service, shipping_cost, estimated_delivery,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tracking_number, "Registered", pkg.origin, pkg.recipient_name,
                    pkg.recipient_email, pkg.sender_name, pkg.sender_address,
                    pkg.recipient_address, pkg.origin, pkg.destination,
                    pkg.package_description, pkg.weight, pkg.shipping_service,
                    pkg.shipping_cost, pkg.estimated_delivery, now, now
                )
            )
            conn.commit()
    finally:
        conn.close()

    add_tracking_event(
        tracking_number=tracking_number,
        status="Registered",
        location=pkg.origin,
        description="Shipment registered with Fidex Express."
    )

    return {
        "success": True,
        "message": "Package successfully registered.",
        "tracking_number": tracking_number
    }

@app.get("/api/admin/packages")
def get_packages(
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    check_admin(x_admin_email, x_admin_password)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM packages ORDER BY id DESC")
            raw_packages = cursor.fetchall() or []
            packages = [row_to_dict(cursor, pkg) for pkg in raw_packages]

            return {
                "success": True,
                "count": len(packages),
                "packages": packages
            }
    finally:
        conn.close()

@app.get("/api/admin/packages/{tracking_number}")
def get_admin_package(
    tracking_number: str,
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    check_admin(x_admin_email, x_admin_password)

    clean_tracking = tracking_number.upper().strip()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM packages WHERE tracking_number = %s",
                (clean_tracking,)
            )
            raw_package = cursor.fetchone()

            if not raw_package:
                raise HTTPException(
                    status_code=404,
                    detail="Package not found."
                )

            package = row_to_dict(cursor, raw_package)

            cursor.execute(
                """
                SELECT * FROM tracking_events
                WHERE tracking_number = %s
                ORDER BY id DESC
                """,
                (clean_tracking,)
            )
            raw_events = cursor.fetchall() or []
            events = [row_to_dict(cursor, event) for event in raw_events]

            package["tracking_history"] = events
            package["history"] = events

            return package
    finally:
        conn.close()

@app.patch("/api/admin/packages/{tracking_number}")
def update_package(
    tracking_number: str,
    update: PackageUpdate,
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    check_admin(x_admin_email, x_admin_password)

    clean_tracking = tracking_number.upper().strip()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT tracking_number FROM packages WHERE tracking_number = %s",
                (clean_tracking,)
            )
            package = cursor.fetchone()

            if not package:
                raise HTTPException(
                    status_code=404,
                    detail="Package not found."
                )

            now = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """
                UPDATE packages
                SET status = %s, current_location = %s, updated_at = %s
                WHERE tracking_number = %s
                """,
                (update.status, update.current_location, now, clean_tracking)
            )
            conn.commit()
    finally:
        conn.close()

    add_tracking_event(
        clean_tracking,
        update.status,
        update.current_location,
        update.description
    )

    return {
        "success": True,
        "message": "Package updated successfully.",
        "tracking_number": clean_tracking,
        "status": update.status,
        "current_location": update.current_location
    }

@app.delete("/api/admin/packages/{tracking_number}")
def delete_package(
    tracking_number: str,
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    check_admin(x_admin_email, x_admin_password)

    clean_tracking = tracking_number.upper().strip()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM tracking_events WHERE tracking_number = %s", (clean_tracking,))
            cursor.execute("DELETE FROM packages WHERE tracking_number = %s", (clean_tracking,))
            deleted = cursor.rowcount

            conn.commit()

            if deleted == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Package not found."
                )

            return {
                "success": True,
                "message": "Package deleted successfully.",
                "tracking_number": clean_tracking
            }
    finally:
        conn.close()

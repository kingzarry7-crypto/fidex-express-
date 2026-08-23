import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import (
    FastAPI,
    HTTPException,
    Header
)

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from database import (
    get_connection,
    generate_tracking_number,
    add_tracking_event,
    init_db
)


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Fidex Express Tracking API",
    version="2.0.0"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=False,

    allow_methods=["*"],

    allow_headers=["*"],
)


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

try:
    init_db()
except Exception as error:
    print(
        "Database initialization warning:",
        error
    )


# =========================================================
# ADMIN AUTHENTICATION
# =========================================================

ADMIN_EMAIL = os.getenv(
    "ADMIN_EMAIL",
    ""
)

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD",
    ""
)


def check_admin(
    admin_email: Optional[str],
    admin_password: Optional[str]
):

    if not ADMIN_EMAIL or not ADMIN_PASSWORD:

        raise HTTPException(
            status_code=500,
            detail="Admin authentication is not configured in Vercel."
        )

    if (
        admin_email != ADMIN_EMAIL
        or admin_password != ADMIN_PASSWORD
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials."
        )

    return True


# =========================================================
# MODELS
# =========================================================

class PackageCreate(BaseModel):

    recipient_name: str = Field(
        min_length=1
    )

    recipient_email: Optional[str] = None

    sender_name: Optional[str] = None

    sender_address: Optional[str] = None

    recipient_address: Optional[str] = None

    origin: str

    destination: str

    package_description: Optional[str] = None

    weight: Optional[float] = None

    shipping_service: Optional[str] = (
        "Standard Shipping"
    )

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
        "version": "2.0.0"
    }


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.post("/api/admin/login")
def admin_login(

    x_admin_email: Optional[str] = Header(
        default=None,
        alias="X-Admin-Email"
    ),

    x_admin_password: Optional[str] = Header(
        default=None,
        alias="X-Admin-Password"
    )

):

    check_admin(
        x_admin_email,
        x_admin_password
    )

    return {
        "success": True,
        "message": "Admin authentication successful",
        "email": ADMIN_EMAIL
    }


# =========================================================
# CUSTOMER TRACKING
# =========================================================

@app.get("/api/track/{tracking_number}")
def track_package(
    tracking_number: str
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM packages
        WHERE tracking_number = ?
        """,
        (
            tracking_number.upper().strip(),
        )
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
            id,
            status,
            location,
            description,
            created_at
        FROM tracking_events
        WHERE tracking_number = ?
        ORDER BY id DESC
        """,
        (
            tracking_number.upper().strip(),
        )
    )

    events = [
        dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()


    result = dict(package)

    result["tracking_history"] = events

    return result


# =========================================================
# ADMIN: REGISTER PACKAGE
# =========================================================

@app.post("/api/packages")
def create_package(

    pkg: PackageCreate,

    x_admin_email: Optional[str] = Header(
        default=None,
        alias="X-Admin-Email"
    ),

    x_admin_password: Optional[str] = Header(
        default=None,
        alias="X-Admin-Password"
    )

):

    check_admin(
        x_admin_email,
        x_admin_password
    )


    tracking_number = (
        generate_tracking_number()
    )


    now = datetime.now(
        timezone.utc
    ).isoformat()


    conn = get_connection()
    cursor = conn.cursor()


    cursor.execute(
        """
        INSERT INTO packages
        (
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
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

            now
        )
    )


    conn.commit()
    conn.close()


    add_tracking_event(
        tracking_number=tracking_number,

        status="Registered",

        location=pkg.origin,

        description=(
            "Shipment registered with "
            "Fidex Express."
        )
    )


    return {

        "success": True,

        "message": (
            "Package successfully registered."
        ),

        "tracking_number":
            tracking_number

    }


# =========================================================
# ADMIN: GET ALL PACKAGES
# =========================================================

@app.get("/api/admin/packages")
def get_packages(

    x_admin_email: Optional[str] = Header(
        default=None,
        alias="X-Admin-Email"
    ),

    x_admin_password: Optional[str] = Header(
        default=None,
        alias="X-Admin-Password"
    )

):

    check_admin(
        x_admin_email,
        x_admin_password
    )


    conn = get_connection()
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
        "packages": packages
    }


# =========================================================
# ADMIN: GET SINGLE PACKAGE
# =========================================================

@app.get(
    "/api/admin/packages/{tracking_number}"
)
def get_admin_package(

    tracking_number: str,

    x_admin_email: Optional[str] = Header(
        default=None,
        alias="X-Admin-Email"
    ),

    x_admin_password: Optional[str] = Header(
        default=None,
        alias="X-Admin-Password"
    )

):

    check_admin(
        x_admin_email,
        x_admin_password
    )


    conn = get_connection()
    cursor = conn.cursor()


    cursor.execute(
        """
        SELECT *
        FROM packages
        WHERE tracking_number = ?
        """,
        (
            tracking_number.upper(),
        )
    )


    package = cursor.fetchone()


    if not package:

        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Package not found."
        )


    result = dict(package)


    cursor.execute(
        """
        SELECT *
        FROM tracking_events
        WHERE tracking_number = ?
        ORDER BY id DESC
        """,
        (
            tracking_number.upper(),
        )
    )


    result["tracking_history"] = [
        dict(row)
        for row in cursor.fetchall()
    ]


    conn.close()


    return result


# =========================================================
# ADMIN: UPDATE PACKAGE
# =========================================================

@app.patch(
    "/api/admin/packages/{tracking_number}"
)
def update_package(

    tracking_number: str,

    update: PackageUpdate,

    x_admin_email: Optional[str] = Header(
        default=None,
        alias="X-Admin-Email"
    ),

    x_admin_password: Optional[str] = Header(
        default=None,
        alias="X-Admin-Password"
    )

):

    check_admin(
        x_admin_email,
        x_admin_password
    )


    tracking_number = (
        tracking_number.upper().strip()
    )


    conn = get_connection()
    cursor = conn.cursor()


    cursor.execute(
        """
        SELECT tracking_number
        FROM packages
        WHERE tracking_number = ?
        """,
        (
            tracking_number,
        )
    )


    package = cursor.fetchone()


    if not package:

        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Package not found."
        )


    now = datetime.now(
        timezone.utc
    ).isoformat()


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

            tracking_number
        )
    )


    conn.commit()
    conn.close()


    add_tracking_event(

        tracking_number,

        update.status,

        update.current_location,

        update.description
    )


    return {

        "success": True,

        "message":
            "Package updated successfully.",

        "tracking_number":
            tracking_number,

        "status":
            update.status,

        "current_location":
            update.current_location

    }


# =========================================================
# ADMIN: DELETE PACKAGE
# =========================================================

@app.delete(
    "/api/admin/packages/{tracking_number}"
)
def delete_package(

    tracking_number: str,

    x_admin_email: Optional[str] = Header(
        default=None,
        alias="X-Admin-Email"
    ),

    x_admin_password: Optional[str] = Header(
        default=None,
        alias="X-Admin-Password"
    )

):

    check_admin(
        x_admin_email,
        x_admin_password
    )


    tracking_number = (
        tracking_number.upper().strip()
    )


    conn = get_connection()
    cursor = conn.cursor()


    cursor.execute(
        """
        DELETE FROM tracking_events
        WHERE tracking_number = ?
        """,
        (
            tracking_number,
        )
    )


    cursor.execute(
        """
        DELETE FROM packages
        WHERE tracking_number = ?
        """,
        (
            tracking_number,
        )
    )


    deleted = cursor.rowcount


    conn.commit()
    conn.close()


    if deleted == 0:

        raise HTTPException(
            status_code=404,
            detail="Package not found."
        )


    return {

        "success": True,

        "message":
            "Package deleted successfully.",

        "tracking_number":
            tracking_number

    }

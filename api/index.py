import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Header, Request, Body
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

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "Fedexg217@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Email Settings (Set via Environment Variables or defaults)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", ADMIN_EMAIL)
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")  # Use Gmail App Password

def send_email_notification(to_email: str, subject: str, body_html: str):
    """Sends email asynchronously without crashing main request pipeline."""
    if not to_email or not SENDER_PASSWORD:
        print("Email notification skipped: Receiver email or SENDER_PASSWORD missing.")
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = f"Fidex Express <{SENDER_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print(f"Notification email successfully sent to {to_email}")
    except Exception as e:
        print("Error sending email notification:", e)

def row_to_dict(cursor, row) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "_asdict"):
        return row._asdict()
    column_names = [col[0] for col in cursor.description]
    return dict(zip(column_names, row))

# =========================================================
# FLEXIBLE AUTHENTICATION HELPER
# =========================================================

def verify_credentials(admin_email: Optional[str], admin_password: Optional[str]) -> bool:
    if not admin_email or not admin_password:
        return False

    clean_email = admin_email.strip().lower()
    clean_password = admin_password.strip()

    target_email = ADMIN_EMAIL.strip().lower()
    target_password = ADMIN_PASSWORD.strip()

    return clean_email == target_email and clean_password == target_password

async def get_credentials_from_request(
    request: Request,
    header_email: Optional[str] = None,
    header_pass: Optional[str] = None
) -> tuple[Optional[str], Optional[str]]:
    """Extracts email and password from headers, query params, or JSON body."""
    # 1. Try Headers
    email = header_email or request.headers.get("X-Admin-Email") or request.headers.get("x-admin-email")
    password = header_pass or request.headers.get("X-Admin-Password") or request.headers.get("x-admin-password")

    # 2. Try Query Params
    if not email:
        email = request.query_params.get("email") or request.query_params.get("admin_email")
    if not password:
        password = request.query_params.get("password") or request.query_params.get("admin_password")

    # 3. Try JSON Body
    if not email or not password:
        try:
            body = await request.json()
            if isinstance(body, dict):
                email = email or body.get("email") or body.get("admin_email") or body.get("x_admin_email")
                password = password or body.get("password") or body.get("admin_password") or body.get("x_admin_password")
        except Exception:
            pass

    return email, password

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
    destination: Optional[str] = None
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
async def admin_login(
    request: Request,
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    email, password = await get_credentials_from_request(request, x_admin_email, x_admin_password)

    if not verify_credentials(email, password):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials."
        )

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
async def create_package(
    request: Request,
    pkg: PackageCreate,
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    email, password = await get_credentials_from_request(request, x_admin_email, x_admin_password)
    if not verify_credentials(email, password):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")

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

    # Send confirmation email to recipient
    if pkg.recipient_email:
        email_body = f"""
        <h2>Package Registered - Fidex Express</h2>
        <p>Hello <strong>{pkg.recipient_name}</strong>,</p>
        <p>A package has been registered for you.</p>
        <p><strong>Tracking Code:</strong> {tracking_number}<br>
        <strong>Origin:</strong> {pkg.origin}<br>
        <strong>Destination:</strong> {pkg.destination}</p>
        <p>Thank you for choosing Fidex Express!</p>
        """
        send_email_notification(
            to_email=pkg.recipient_email,
            subject=f"Shipment Registered: {tracking_number}",
            body_html=email_body
        )

    return {
        "success": True,
        "message": "Package successfully registered.",
        "tracking_number": tracking_number
    }

@app.get("/api/admin/packages")
async def get_packages(
    request: Request,
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    email, password = await get_credentials_from_request(request, x_admin_email, x_admin_password)
    if not verify_credentials(email, password):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")

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
async def get_admin_package(
    tracking_number: str,
    request: Request,
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    email, password = await get_credentials_from_request(request, x_admin_email, x_admin_password)
    if not verify_credentials(email, password):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")

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
async def update_package(
    tracking_number: str,
    request: Request,
    update: PackageUpdate,
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    email, password = await get_credentials_from_request(request, x_admin_email, x_admin_password)
    if not verify_credentials(email, password):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")

    clean_tracking = tracking_number.upper().strip()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT tracking_number, recipient_name, recipient_email FROM packages WHERE tracking_number = %s",
                (clean_tracking,)
            )
            raw_package = cursor.fetchone()

            if not raw_package:
                raise HTTPException(
                    status_code=404,
                    detail="Package not found."
                )

            package = row_to_dict(cursor, raw_package)
            now = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """
                UPDATE packages
                SET
                    status = %s,
                    current_location = %s,
                    destination = COALESCE(%s, destination),
                    updated_at = %s
                WHERE tracking_number = %s
                """,
                (
                    update.status,
                    update.current_location,
                    update.destination,
                    now,
                    clean_tracking
                )
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

    # Send email update to recipient
    if package and package.get("recipient_email"):
        update_body = f"""
        <h2>Shipment Status Update - Fidex Express</h2>
        <p>Hello <strong>{package.get('recipient_name', 'Customer')}</strong>,</p>
        <p>Your package status has been updated.</p>
        <p><strong>Tracking Code:</strong> {clean_tracking}<br>
        <strong>New Status:</strong> {update.status}<br>
        <strong>Current Location:</strong> {update.current_location}</p>
        """
        send_email_notification(
            to_email=package.get("recipient_email"),
            subject=f"Shipment Update: {clean_tracking} - {update.status}",
            body_html=update_body
        )

    return {
        "success": True,
        "message": "Package updated successfully.",
        "tracking_number": clean_tracking,
        "status": update.status,
        "current_location": update.current_location,
        "destination": update.destination
    }

@app.delete("/api/admin/packages/{tracking_number}")
async def delete_package(
    tracking_number: str,
    request: Request,
    x_admin_email: Optional[str] = Header(default=None, alias="X-Admin-Email"),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")
):
    email, password = await get_credentials_from_request(request, x_admin_email, x_admin_password)
    if not verify_credentials(email, password):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")

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

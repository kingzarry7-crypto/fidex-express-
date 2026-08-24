import os
import requests
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
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# =========================================================
# RESEND EMAIL NOTIFICATION SYSTEM
# =========================================================

def send_email_notification(
    to_email: str, 
    recipient_name: str, 
    tracking_number: str, 
    status: str, 
    location: str, 
    est_delivery: Optional[str] = None
):
    """Sends clean, styled tracking update emails via Resend HTTP API."""
    if not RESEND_API_KEY:
        print("Email skipped: RESEND_API_KEY environment variable is missing.")
        return

    track_url = f"https://fidex-express-pi.vercel.app/index.html?tracking={tracking_number}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f4f4f5; margin: 0; padding: 20px; }}
        .card {{ max-width: 500px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); color: #18181b; }}
        .header {{ background: #0f172a; padding: 24px; text-align: center; color: #ffffff; }}
        .header h1 {{ margin: 0; font-size: 20px; letter-spacing: 1px; }}
        .content {{ padding: 24px; }}
        .status-badge {{ display: inline-block; background: #e0e7ff; color: #3730a3; font-weight: 600; padding: 6px 12px; border-radius: 20px; font-size: 13px; margin-bottom: 16px; }}
        .info-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; }}
        .btn {{ display: block; width: 100%; text-align: center; background: #2563eb; color: #ffffff !important; font-weight: 600; padding: 12px 0; border-radius: 8px; text-decoration: none; margin-top: 20px; }}
        .footer {{ text-align: center; padding: 16px; font-size: 12px; color: #9ca3af; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h1>FIDEX EXPRESS</h1>
        </div>
        <div class="content">
          <span class="status-badge">📦 Status: {status}</span>
          <p style="margin: 0 0 12px 0; font-size: 16px;">Hi <strong>{recipient_name}</strong>,</p>
          <p style="margin: 0; color: #4b5563; font-size: 14px;">Here is the latest update for your package.</p>
          
          <div class="info-box">
            <div style="font-size: 11px; color: #64748b; text-transform: uppercase; margin-bottom: 8px; font-weight: 700;">Package Details</div>
            <p style="margin: 4px 0; font-size: 14px;"><strong>Tracking Code:</strong> {tracking_number}</p>
            <p style="margin: 4px 0; font-size: 14px;"><strong>Current Location:</strong> {location}</p>
            {"<p style='margin: 4px 0; font-size: 14px;'><strong>Estimated Delivery:</strong> " + str(est_delivery) + "</p>" if est_delivery else ""}
          </div>

          <a href="{track_url}" class="btn">Track Your Parcel</a>
        </div>
        <div class="footer">
          &copy; Fidex Express Logistics. All rights reserved.
        </div>
      </div>
    </body>
    </html>
    """

    payload = {
        "from": "Fidex Express <onboarding@resend.dev>",
        "to": [to_email],
        "subject": f"Shipment Update: {tracking_number} ({status})",
        "html": html_content
    }

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=10)
        print(f"Resend Output: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Failed sending email via Resend: {e}")

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

    # Send Resend email notification
    if pkg.recipient_email:
        send_email_notification(
            to_email=pkg.recipient_email,
            recipient_name=pkg.recipient_name,
            tracking_number=tracking_number,
            status="Registered",
            location=pkg.origin,
            est_delivery=pkg.estimated_delivery
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

    # Send Resend email notification
    if package and package.get("recipient_email"):
        send_email_notification(
            to_email=package.get("recipient_email"),
            recipient_name=package.get("recipient_name", "Customer"),
            tracking_number=clean_tracking,
            status=update.status,
            location=update.current_location
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

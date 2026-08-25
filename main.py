import os
import html
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr

from database import (
    get_connection,
    generate_tracking_number,
    add_tracking_event,
    init_db,
)


# =========================================================
# 👑 FIDEX EXPRESS API
# =========================================================

app = FastAPI(
    title="Fidex Express Tracking API",
    version="3.0.0",
)


# =========================================================
# CONFIGURATION
# =========================================================

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "https://fidex-express-logistics.vercel.app"
).strip().rstrip("/")


# =========================================================
# EMAIL CONFIGURATION
# =========================================================
#
# PRIMARY:
#   RESEND_API_KEY
#   EMAIL_FROM
#
# OPTIONAL SMTP FALLBACK:
#   SMTP_SERVER
#   SMTP_PORT
#   SMTP_USERNAME
#   SMTP_PASSWORD
#
# Example:
#
# RESEND_API_KEY=re_xxxxxxxxx
# EMAIL_FROM=Fidex Express <notifications@yourdomain.com>
#
# OR Gmail:
#
# SMTP_SERVER=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USERNAME=yourgmail@gmail.com
# SMTP_PASSWORD=your_gmail_app_password
# EMAIL_FROM=Fidex Express <yourgmail@gmail.com>
# =========================================================

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()

EMAIL_FROM = os.getenv(
    "EMAIL_FROM",
    "Fidex Express <onboarding@resend.dev>"
).strip()

SMTP_SERVER = os.getenv(
    "SMTP_SERVER",
    "smtp.gmail.com"
).strip()

SMTP_PORT = int(
    os.getenv("SMTP_PORT", "587")
)

SMTP_USERNAME = os.getenv(
    "SMTP_USERNAME",
    ""
).strip()

SMTP_PASSWORD = os.getenv(
    "SMTP_PASSWORD",
    ""
).strip()


# =========================================================
# TRACKING URL
# =========================================================

TRACKING_URL = os.getenv(
    "TRACKING_URL",
    FRONTEND_URL
).strip().rstrip("/")


# =========================================================
# CORS
# =========================================================

if FRONTEND_URL == "*":
    allowed_origins = ["*"]
else:
    allowed_origins = [
        FRONTEND_URL,
        "https://fidex-express.vercel.app",
        "https://fidex-express-logistics.vercel.app",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=[
        "GET",
        "POST",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=["*"],
)


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
def startup_event():
    try:
        init_db()
        print("✅ PostgreSQL database initialized")
    except Exception as error:
        print("❌ Database startup error:", repr(error))


# =========================================================
# HELPERS
# =========================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    value = str(value).strip()

    return value if value else None


def safe_html(value: Optional[str]) -> str:
    return html.escape(str(value or ""))


# =========================================================
# ADMIN AUTHENTICATION
# =========================================================

def verify_admin(
    x_admin_email: Optional[str] = Header(
        default=None,
        alias="X-Admin-Email"
    ),
    x_admin_password: Optional[str] = Header(
        default=None,
        alias="X-Admin-Password"
    ),
):
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail=(
                "Admin credentials are not configured. "
                "Set ADMIN_EMAIL and ADMIN_PASSWORD in Vercel."
            ),
        )

    if not x_admin_email or not x_admin_password:
        raise HTTPException(
            status_code=400,
            detail="Missing administrative headers",
        )

    if (
        x_admin_email.strip().lower() != ADMIN_EMAIL.lower()
        or x_admin_password.strip() != ADMIN_PASSWORD
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials",
        )

    return True


# =========================================================
# EMAIL HTML
# =========================================================

def build_email_html(
    recipient_name: str,
    tracking_number: str,
    status: str,
    location: str,
    description: Optional[str],
    origin: Optional[str],
    destination: Optional[str],
    estimated_delivery: Optional[str],
    event_type: str,
) -> str:

    tracking_link = (
        f"{TRACKING_URL}/?tracking={tracking_number}"
        if TRACKING_URL
        else ""
    )

    if event_type == "registration":
        title = "Your shipment has been registered"
        intro = (
            "Your Fidex Express shipment has been successfully "
            "registered in our tracking system."
        )
    else:
        title = "Your shipment has been updated"
        intro = (
            "There has been a new movement or status update "
            "for your Fidex Express shipment."
        )

    tracking_button = ""

    if tracking_link:
        tracking_button = f"""
        <div style="text-align:center;margin:28px 0;">
            <a
                href="{safe_html(tracking_link)}"
                style="
                    display:inline-block;
                    background:#4d148c;
                    color:#ffffff;
                    text-decoration:none;
                    padding:13px 24px;
                    border-radius:6px;
                    font-weight:bold;
                "
            >
                Track Your Package
            </a>
        </div>
        """

    description_html = ""

    if description:
        description_html = f"""
        <p style="margin:8px 0;">
            <strong>Update:</strong>
            {safe_html(description)}
        </p>
        """

    estimated_html = ""

    if estimated_delivery:
        estimated_html = f"""
        <p style="margin:8px 0;">
            <strong>Estimated Delivery:</strong>
            {safe_html(estimated_delivery)}
        </p>
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Fidex Express Shipment Update</title>
</head>

<body
    style="
        margin:0;
        padding:0;
        background:#f4f4f7;
        font-family:Arial,Helvetica,sans-serif;
        color:#222222;
    "
>

<div style="padding:30px 15px;">

    <div
        style="
            max-width:620px;
            margin:0 auto;
            background:#ffffff;
            border-radius:10px;
            overflow:hidden;
            border:1px solid #e5e7eb;
        "
    >

        <div
            style="
                background:#4d148c;
                padding:24px;
                text-align:center;
                color:#ffffff;
            "
        >
            <h1 style="margin:0;font-size:25px;">
                Fidex Express
            </h1>

            <p style="margin:8px 0 0;">
                Shipment Tracking Notification
            </p>
        </div>

        <div style="padding:30px;">

            <h2 style="margin-top:0;">
                {safe_html(title)}
            </h2>

            <p>
                Hello <strong>{safe_html(recipient_name)}</strong>,
            </p>

            <p>
                {safe_html(intro)}
            </p>

            <div
                style="
                    background:#f8f9fb;
                    border:1px solid #e5e7eb;
                    border-radius:8px;
                    padding:20px;
                    margin:22px 0;
                "
            >

                <p style="margin:8px 0;">
                    <strong>Tracking Number:</strong>
                    {safe_html(tracking_number)}
                </p>

                <p style="margin:8px 0;">
                    <strong>Status:</strong>
                    <span style="color:#4d148c;font-weight:bold;">
                        {safe_html(status)}
                    </span>
                </p>

                <p style="margin:8px 0;">
                    <strong>Current Location:</strong>
                    {safe_html(location)}
                </p>

                <p style="margin:8px 0;">
                    <strong>Origin:</strong>
                    {safe_html(origin)}
                </p>

                <p style="margin:8px 0;">
                    <strong>Destination:</strong>
                    {safe_html(destination)}
                </p>

                {estimated_html}

                {description_html}

            </div>

            {tracking_button}

            <p style="font-size:13px;color:#6b7280;">
                Please keep your tracking number for future reference.
            </p>

            <p style="font-size:13px;color:#6b7280;">
                Thank you for using Fidex Express.
            </p>

        </div>

        <div
            style="
                background:#f8f9fb;
                padding:18px;
                text-align:center;
                font-size:12px;
                color:#777777;
            "
        >
            © Fidex Express
        </div>

    </div>

</div>

</body>
</html>
"""


# =========================================================
# RESEND EMAIL
# =========================================================

def send_email_resend(
    recipient_email: str,
    subject: str,
    html_content: str,
):
    if not RESEND_API_KEY:
        raise RuntimeError(
            "RESEND_API_KEY is not configured"
        )

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": EMAIL_FROM,
            "to": [recipient_email],
            "subject": subject,
            "html": html_content,
        },
        timeout=20,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Resend error {response.status_code}: "
            f"{response.text[:1000]}"
        )

    try:
        data = response.json()
    except Exception:
        data = {}

    print(
        "✅ Email sent through Resend:",
        data.get("id", "unknown-id"),
    )

    return data


# =========================================================
# SMTP FALLBACK
# =========================================================

def send_email_smtp(
    recipient_email: str,
    subject: str,
    html_content: str,
):
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP credentials are not configured"
        )

    message = MIMEMultipart("alternative")

    message["From"] = EMAIL_FROM
    message["To"] = recipient_email
    message["Subject"] = subject

    message.attach(
        MIMEText(
            html_content,
            "html",
            "utf-8",
        )
    )

    with smtplib.SMTP(
        SMTP_SERVER,
        SMTP_PORT,
        timeout=20,
    ) as server:

        server.ehlo()
        server.starttls()
        server.ehlo()

        server.login(
            SMTP_USERNAME,
            SMTP_PASSWORD,
        )

        server.sendmail(
            SMTP_USERNAME,
            [recipient_email],
            message.as_string(),
        )

    print(
        f"✅ Email sent through SMTP to {recipient_email}"
    )


# =========================================================
# UNIFIED EMAIL SENDER
# =========================================================

def send_notification_email(
    recipient_email: Optional[str],
    recipient_name: str,
    tracking_number: str,
    status: str,
    location: str,
    description: Optional[str] = None,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    estimated_delivery: Optional[str] = None,
    event_type: str = "update",
):
    """
    Sends shipment notification.

    Resend is used first.
    SMTP is used if Resend is unavailable or fails.
    """

    recipient_email = clean_text(recipient_email)

    if not recipient_email:
        print(
            f"⚠️ No recipient email for {tracking_number}"
        )
        return False

    if "@" not in recipient_email:
        print(
            f"⚠️ Invalid recipient email: {recipient_email}"
        )
        return False

    if event_type == "registration":
        subject = (
            f"Shipment Registered [{tracking_number}]"
        )
    else:
        subject = (
            f"Shipment Update [{tracking_number}] - {status}"
        )

    html_content = build_email_html(
        recipient_name=recipient_name,
        tracking_number=tracking_number,
        status=status,
        location=location,
        description=description,
        origin=origin,
        destination=destination,
        estimated_delivery=estimated_delivery,
        event_type=event_type,
    )

    # -----------------------------------------------------
    # RESEND
    # -----------------------------------------------------

    if RESEND_API_KEY:
        try:
            send_email_resend(
                recipient_email,
                subject,
                html_content,
            )
            return True

        except Exception as error:
            print(
                "❌ Resend email failed:",
                repr(error),
            )

    # -----------------------------------------------------
    # SMTP FALLBACK
    # -----------------------------------------------------

    if SMTP_USERNAME and SMTP_PASSWORD:
        try:
            send_email_smtp(
                recipient_email,
                subject,
                html_content,
            )
            return True

        except Exception as error:
            print(
                "❌ SMTP email failed:",
                repr(error),
            )

    print(
        "❌ NO EMAIL PROVIDER CONFIGURED. "
        "Set RESEND_API_KEY or SMTP_USERNAME/SMTP_PASSWORD."
    )

    return False


# =========================================================
# PYDANTIC MODELS
# =========================================================

class PackageCreate(BaseModel):
    recipient_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    recipient_email: Optional[EmailStr] = None

    sender_name: Optional[str] = None
    sender_address: Optional[str] = None

    recipient_address: Optional[str] = None

    origin: str = Field(
        default="Shipment Center",
        max_length=255,
    )

    destination: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    package_description: Optional[str] = None

    weight: Optional[float] = None

    shipping_service: str = Field(
        default="Standard Shipping",
        max_length=100,
    )

    shipping_cost: Optional[float] = None

    estimated_delivery: Optional[str] = None


class PackageUpdate(BaseModel):
    status: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    current_location: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    description: Optional[str] = None


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():
    return {
        "status": "Fidex Express API is running",
        "version": "3.0.0",
        "service": "Fidex Express",
        "database": "PostgreSQL",
        "email": (
            "Resend"
            if RESEND_API_KEY
            else "SMTP"
            if SMTP_USERNAME and SMTP_PASSWORD
            else "NOT_CONFIGURED"
        ),
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():
    try:
        conn = get_connection()

        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        conn.close()

        return {
            "status": "ok",
            "database": "connected",
            "time": utc_now(),
            "email": (
                "resend"
                if RESEND_API_KEY
                else "smtp"
                if SMTP_USERNAME and SMTP_PASSWORD
                else "not_configured"
            ),
        }

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "database": "disconnected",
                "error": str(error),
            },
        )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.post("/api/admin/login")
def admin_login(
    x_admin_email: Optional[str] = Header(
        default=None,
        alias="X-Admin-Email",
    ),
    x_admin_password: Optional[str] = Header(
        default=None,
        alias="X-Admin-Password",
    ),
):

    verify_admin(
        x_admin_email,
        x_admin_password,
    )

    return {
        "success": True,
        "message": "Admin authentication successful",
        "email": ADMIN_EMAIL,
    }


# =========================================================
# PUBLIC TRACKING
# =========================================================

@app.get("/api/track/{tracking_num}")
def track_package(tracking_num: str):

    tracking_num = tracking_num.strip().upper()

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

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
                    shipping_cost,
                    estimated_delivery,
                    created_at,
                    updated_at
                FROM packages
                WHERE tracking_number = %s
                """,
                (tracking_num,),
            )

            package = cursor.fetchone()

            if not package:
                raise HTTPException(
                    status_code=404,
                    detail="Tracking number not found",
                )

            cursor.execute(
                """
                SELECT
                    status,
                    location,
                    description,
                    created_at
                FROM tracking_events
                WHERE tracking_number = %s
                ORDER BY id DESC
                """,
                (tracking_num,),
            )

            history = cursor.fetchall()

            result = dict(package)

            result["history"] = history
            result["tracking_history"] = history

            return result

    finally:
        conn.close()


# =========================================================
# ADMIN: REGISTER PACKAGE
# =========================================================

@app.post(
    "/api/packages",
    dependencies=[Depends(verify_admin)],
)
def create_package(pkg: PackageCreate):

    now = utc_now()
    tracking_number = generate_tracking_number()

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

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
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    tracking_number,
                    "Registered",
                    pkg.origin,
                    pkg.recipient_name,
                    str(pkg.recipient_email)
                    if pkg.recipient_email
                    else None,
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
                ),
            )

            cursor.execute(
                """
                INSERT INTO tracking_events (
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
                    "Registered",
                    pkg.origin,
                    "Package successfully registered.",
                    now,
                ),
            )

        conn.commit()

    except Exception as error:

        conn.rollback()

        print(
            "❌ Package registration failed:",
            repr(error),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to register package",
        )

    finally:
        conn.close()

    # -----------------------------------------------------
    # SEND REGISTRATION EMAIL
    # -----------------------------------------------------

    email_sent = False

    if pkg.recipient_email:

        email_sent = send_notification_email(
            recipient_email=str(pkg.recipient_email),
            recipient_name=pkg.recipient_name,
            tracking_number=tracking_number,
            status="Registered",
            location=pkg.origin,
            description="Package successfully registered.",
            origin=pkg.origin,
            destination=pkg.destination,
            estimated_delivery=pkg.estimated_delivery,
            event_type="registration",
        )

    return {
        "success": True,
        "message": "Package successfully registered",
        "tracking_number": tracking_number,
        "status": "Registered",
        "email_sent": email_sent,
        "data": {
            "tracking_number": tracking_number,
            "recipient_name": pkg.recipient_name,
            "recipient_email": (
                str(pkg.recipient_email)
                if pkg.recipient_email
                else None
            ),
            "origin": pkg.origin,
            "destination": pkg.destination,
            "shipping_service": pkg.shipping_service,
            "shipping_cost": pkg.shipping_cost,
            "estimated_delivery": pkg.estimated_delivery,
        },
    }


# =========================================================
# ADMIN: LIST PACKAGES
# =========================================================

@app.get(
    "/api/admin/packages",
    dependencies=[Depends(verify_admin)],
)
def admin_packages():

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM packages
                ORDER BY id DESC
                """
            )

            packages = cursor.fetchall()

            return {
                "success": True,
                "count": len(packages),
                "packages": packages,
            }

    finally:
        conn.close()


# =========================================================
# ADMIN: UPDATE PACKAGE
# =========================================================

@app.patch(
    "/api/admin/packages/{tracking_num}",
    dependencies=[Depends(verify_admin)],
)
def update_package(
    tracking_num: str,
    update: PackageUpdate,
):

    tracking_num = tracking_num.strip().upper()

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            # ---------------------------------------------
            # GET CURRENT PACKAGE
            # ---------------------------------------------

            cursor.execute(
                """
                SELECT
                    recipient_email,
                    recipient_name,
                    status,
                    current_location,
                    origin,
                    destination,
                    estimated_delivery
                FROM packages
                WHERE tracking_number = %s
                """,
                (tracking_num,),
            )

            package = cursor.fetchone()

            if not package:
                raise HTTPException(
                    status_code=404,
                    detail="Tracking number not found",
                )

            old_status = package["status"]
            old_location = package["current_location"]

            new_status = update.status.strip()
            new_location = update.current_location.strip()

            status_changed = (
                old_status != new_status
            )

            location_changed = (
                old_location != new_location
            )

            # ---------------------------------------------
            # UPDATE ONLY WHEN SOMETHING ACTUALLY CHANGED
            # ---------------------------------------------

            if status_changed or location_changed:

                now = utc_now()

                cursor.execute(
                    """
                    UPDATE packages
                    SET
                        status = %s,
                        current_location = %s,
                        updated_at = %s
                    WHERE tracking_number = %s
                    """,
                    (
                        new_status,
                        new_location,
                        now,
                        tracking_num,
                    ),
                )

                cursor.execute(
                    """
                    INSERT INTO tracking_events (
                        tracking_number,
                        status,
                        location,
                        description,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        tracking_num,
                        new_status,
                        new_location,
                        update.description,
                        now,
                    ),
                )

            conn.commit()

            recipient_email = package["recipient_email"]
            recipient_name = package["recipient_name"]

            origin = package["origin"]
            destination = package["destination"]
            estimated_delivery = package["estimated_delivery"]

    except HTTPException:
        conn.rollback()
        raise

    except Exception as error:

        conn.rollback()

        print(
            "❌ Package update failed:",
            repr(error),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to update package",
        )

    finally:
        conn.close()

    # -----------------------------------------------------
    # SEND EMAIL ONLY WHEN STATUS OR LOCATION CHANGED
    # -----------------------------------------------------

    email_sent = False

    if status_changed or location_changed:

        if recipient_email:

            email_sent = send_notification_email(
                recipient_email=recipient_email,
                recipient_name=recipient_name,
                tracking_number=tracking_num,
                status=new_status,
                location=new_location,
                description=update.description,
                origin=origin,
                destination=destination,
                estimated_delivery=estimated_delivery,
                event_type="update",
            )

    return {
        "success": True,
        "message": (
            "Package updated and notification processed"
            if status_changed or location_changed
            else "No package changes detected"
        ),
        "tracking_number": tracking_num,
        "status": new_status,
        "current_location": new_location,
        "status_changed": status_changed,
        "location_changed": location_changed,
        "email_sent": email_sent,
    }


# =========================================================
# ADMIN: GET SINGLE PACKAGE
# =========================================================

@app.get(
    "/api/admin/packages/{tracking_num}",
    dependencies=[Depends(verify_admin)],
)
def admin_get_package(tracking_num: str):

    tracking_num = tracking_num.strip().upper()

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM packages
                WHERE tracking_number = %s
                """,
                (tracking_num,),
            )

            package = cursor.fetchone()

            if not package:
                raise HTTPException(
                    status_code=404,
                    detail="Tracking number not found",
                )

            cursor.execute(
                """
                SELECT *
                FROM tracking_events
                WHERE tracking_number = %s
                ORDER BY id DESC
                """,
                (tracking_num,),
            )

            history = cursor.fetchall()

            result = dict(package)

            result["history"] = history
            result["tracking_history"] = history

            return result

    finally:
        conn.close()


# =========================================================
# ADMIN: DELETE PACKAGE
# =========================================================

@app.delete(
    "/api/admin/packages/{tracking_num}",
    dependencies=[Depends(verify_admin)],
)
def delete_package(tracking_num: str):

    tracking_num = tracking_num.strip().upper()

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT id
                FROM packages
                WHERE tracking_number = %s
                """,
                (tracking_num,),
            )

            package = cursor.fetchone()

            if not package:
                raise HTTPException(
                    status_code=404,
                    detail="Tracking number not found",
                )

            cursor.execute(
                """
                DELETE FROM tracking_events
                WHERE tracking_number = %s
                """,
                (tracking_num,),
            )

            cursor.execute(
                """
                DELETE FROM packages
                WHERE tracking_number = %s
                """,
                (tracking_num,),
            )

        conn.commit()

        return {
            "success": True,
            "message": "Package deleted",
            "tracking_number": tracking_num,
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as error:

        conn.rollback()

        print(
            "❌ Package deletion failed:",
            repr(error),
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to delete package",
        )

    finally:
        conn.close()

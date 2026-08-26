# =========================================================
# 📧 EMAIL CONFIGURATION
# =========================================================

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()

EMAIL_FROM = os.getenv(
    "EMAIL_FROM",
    ""
).strip()

SMTP_SERVER = os.getenv(
    "SMTP_SERVER",
    "smtp.gmail.com"
).strip()

SMTP_PORT = int(
    os.getenv("SMTP_PORT", "587").strip()
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
# EMAIL VALIDATION
# =========================================================

def is_valid_email(email: Optional[str]) -> bool:
    if not email:
        return False

    email = str(email).strip()

    if len(email) > 320:
        return False

    if "@" not in email:
        return False

    local, domain = email.rsplit("@", 1)

    if not local or not domain:
        return False

    if "." not in domain:
        return False

    return True


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

    if not EMAIL_FROM:
        raise RuntimeError(
            "EMAIL_FROM is not configured"
        )

    recipient_email = recipient_email.strip()

    payload = {
        "from": EMAIL_FROM,
        "to": [recipient_email],
        "subject": subject,
        "html": html_content,
    }

    print(
        f"📧 Sending Resend email "
        f"from={EMAIL_FROM} "
        f"to={recipient_email}"
    )

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    # Always print the response for debugging
    print(
        f"📨 Resend HTTP status: {response.status_code}"
    )

    print(
        f"📨 Resend response: "
        f"{response.text[:2000]}"
    )

    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(
            f"Resend API error "
            f"{response.status_code}: "
            f"{response.text[:2000]}"
        )

    try:
        data = response.json()
    except Exception:
        data = {}

    message_id = data.get("id")

    if not message_id:
        raise RuntimeError(
            f"Resend accepted the request but "
            f"returned no email ID: {data}"
        )

    print(
        f"✅ RESEND ACCEPTED EMAIL "
        f"message_id={message_id}"
    )

    return {
        "success": True,
        "provider": "resend",
        "message_id": message_id,
    }


# =========================================================
# SMTP EMAIL
# =========================================================

def send_email_smtp(
    recipient_email: str,
    subject: str,
    html_content: str,
):
    if not SMTP_USERNAME:
        raise RuntimeError(
            "SMTP_USERNAME is not configured"
        )

    if not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP_PASSWORD is not configured"
        )

    message = MIMEMultipart("alternative")

    # IMPORTANT:
    # Use the authenticated SMTP account as the sender.
    smtp_from = SMTP_USERNAME

    message["From"] = smtp_from
    message["To"] = recipient_email
    message["Subject"] = subject

    message.attach(
        MIMEText(
            html_content,
            "html",
            "utf-8",
        )
    )

    print(
        f"📧 Sending SMTP email "
        f"from={smtp_from} "
        f"to={recipient_email}"
    )

    with smtplib.SMTP(
        SMTP_SERVER,
        SMTP_PORT,
        timeout=30,
    ) as server:

        server.ehlo()

        server.starttls()

        server.ehlo()

        server.login(
            SMTP_USERNAME,
            SMTP_PASSWORD,
        )

        server.sendmail(
            smtp_from,
            [recipient_email],
            message.as_string(),
        )

    print(
        f"✅ SMTP EMAIL ACCEPTED "
        f"to={recipient_email}"
    )

    return {
        "success": True,
        "provider": "smtp",
    }


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
    Send shipment notification to receiver.

    Priority:
        1. Resend
        2. SMTP fallback

    Returns a detailed result instead of only True/False.
    """

    recipient_email = clean_text(recipient_email)

    if not recipient_email:
        print(
            f"⚠️ No recipient email "
            f"for tracking {tracking_number}"
        )

        return {
            "success": False,
            "provider": None,
            "error": "No recipient email",
        }

    if not is_valid_email(recipient_email):
        print(
            f"⚠️ Invalid recipient email: "
            f"{recipient_email}"
        )

        return {
            "success": False,
            "provider": None,
            "error": "Invalid recipient email",
        }

    # -----------------------------------------------------
    # SUBJECT
    # -----------------------------------------------------

    if event_type == "registration":
        subject = (
            f"Fidex Express Shipment Registered "
            f"[{tracking_number}]"
        )
    else:
        subject = (
            f"Fidex Express Shipment Update "
            f"[{tracking_number}] - {status}"
        )

    # -----------------------------------------------------
    # HTML
    # -----------------------------------------------------

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

            result = send_email_resend(
                recipient_email=recipient_email,
                subject=subject,
                html_content=html_content,
            )

            print(
                f"✅ Receiver notification sent "
                f"through Resend to "
                f"{recipient_email}"
            )

            return result

        except Exception as error:

            print(
                "❌ RESEND FAILED:"
            )

            print(
                repr(error)
            )

    # -----------------------------------------------------
    # SMTP FALLBACK
    # -----------------------------------------------------

    if SMTP_USERNAME and SMTP_PASSWORD:

        try:

            result = send_email_smtp(
                recipient_email=recipient_email,
                subject=subject,
                html_content=html_content,
            )

            print(
                f"✅ Receiver notification sent "
                f"through SMTP to "
                f"{recipient_email}"
            )

            return result

        except Exception as error:

            print(
                "❌ SMTP FAILED:"
            )

            print(
                repr(error)
            )

    # -----------------------------------------------------
    # NOTHING WORKED
    # -----------------------------------------------------

    print(
        "❌ EMAIL DELIVERY FAILED"
    )

    print(
        "Configure either:"
    )

    print(
        "RESEND_API_KEY + EMAIL_FROM"
    )

    print(
        "OR"
    )

    print(
        "SMTP_USERNAME + SMTP_PASSWORD"
    )

    return {
        "success": False,
        "provider": None,
        "error": "No working email provider",
    }

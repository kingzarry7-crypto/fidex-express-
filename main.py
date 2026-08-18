from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3

app = FastAPI(title="Fidex Express Tracking API")

# Enable CORS so your Vercel frontend can call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from any frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Data schema for adding new packages
class PackageCreate(BaseModel):
    tracking_number: str
    status: str
    current_location: str
    recipient_name: str


def get_db_connection():
    conn = sqlite3.connect("packages.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/")
def home():
    return {"status": "Fidex Express API is running"}


# Endpoint to lookup tracking information
@app.get("/api/track/{tracking_num}")
def track_package(tracking_num: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM packages WHERE tracking_number = ?", (tracking_num,)
    )
    package = cursor.fetchone()
    conn.close()

    if not package:
        raise HTTPException(status_code=404, detail="Tracking number not found")

    return dict(package)


# Endpoint to register/add new packages to the database
@app.post("/api/packages")
def create_package(pkg: PackageCreate):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO packages (tracking_number, status, current_location, recipient_name)
            VALUES (?, ?, ?, ?)
        """,
            (
                pkg.tracking_number,
                pkg.status,
                pkg.current_location,
                pkg.recipient_name,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(
            status_code=400, detail="Tracking number already exists"
        )

    conn.close()
    return {"message": "Package successfully registered", "data": pkg}

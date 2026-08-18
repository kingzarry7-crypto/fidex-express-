import sqlite3


def init_db():
    conn = sqlite3.connect("packages.db")
    cursor = conn.cursor()

    # Create packages table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS packages (
            tracking_number TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            current_location TEXT NOT NULL,
            recipient_name TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Insert sample tracking record
    cursor.execute(
        """
        INSERT OR IGNORE INTO packages (tracking_number, status, current_location, recipient_name)
        VALUES ('FDX12345678', 'In Transit', 'Regional Distribution Center', 'John Doe')
    """
    )

    conn.commit()
    conn.close()
    print("Database initialized successfully.")


if __name__ == "__main__":
    init_db()

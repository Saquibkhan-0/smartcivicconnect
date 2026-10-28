import sqlite3

DB_PATH = "civic.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # lets us read columns by name: row["category"]
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL DEFAULT 'other',
            description_original TEXT NOT NULL DEFAULT '',
            description_english TEXT NOT NULL DEFAULT '',
            severity INTEGER NOT NULL DEFAULT 5,
            priority INTEGER NOT NULL DEFAULT 5,
            duplicate_count INTEGER NOT NULL DEFAULT 1,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            image_url TEXT NOT NULL DEFAULT '',
            audio_path TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT 'en',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
import math
import os
import sqlite3
import uuid
from datetime import datetime

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ai import analyse_report

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

VALID_STATUSES = {"open", "in_progress", "resolved"}
DUPLICATE_RADIUS_M = 50  # same category within this distance = same issue

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # must be False when using "*"
    allow_methods=["*"],      # includes PATCH
    allow_headers=["*"],
)

# Photos are served at /uploads/<file>; the dashboard uses API_BASE + image_url
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            description_original TEXT,
            description_english TEXT,
            severity INTEGER,
            priority INTEGER,
            duplicate_count INTEGER,
            lat REAL,
            lng REAL,
            status TEXT,
            image_url TEXT,
            created_at TEXT,
            merged BOOLEAN,
            estimated_cost REAL,
            estimated_hours REAL
        )
    """)
    # Migrate older databases that are missing newer columns
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(reports)")}
    for name, typ in [("merged", "BOOLEAN"), ("estimated_cost", "REAL"),
                      ("estimated_hours", "REAL")]:
        if name not in cols:
            conn.execute(f"ALTER TABLE reports ADD COLUMN {name} {typ}")
    conn.commit()
    conn.close()


init_db()


def distance_m(lat1, lng1, lat2, lng2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def row_to_dict(row):
    d = dict(row)
    d["merged"] = bool(d.get("merged"))
    return d


@app.post("/reports")
async def create_report(
    text: str = Form(None),
    lat: float = Form(...),
    lng: float = Form(...),
    photo: UploadFile = File(None),
    audio: UploadFile = File(None),
    language: str = Form("en"),
):
    text = (text or "").strip() or None

    image_bytes = image_mime = audio_bytes = audio_mime = None
    image_url = ""

    if photo and photo.filename:
        image_bytes = await photo.read()
        image_mime = (photo.content_type or "image/jpeg").split(";")[0]
        ext = os.path.splitext(photo.filename)[1].lower() or ".jpg"
        fname = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
            f.write(image_bytes)
        image_url = f"/uploads/{fname}"

    if audio and audio.filename:
        audio_bytes = await audio.read()
        audio_mime = (audio.content_type or "audio/webm").split(";")[0]

    if not (text or image_bytes or audio_bytes):
        raise HTTPException(400, "Provide a description, photo, or voice note.")

    ai = analyse_report(
        text=text, image_bytes=image_bytes, image_mime=image_mime,
        audio_bytes=audio_bytes, audio_mime=audio_mime, language=language,
    )

    db = db_conn()

    # Duplicate detection: same category, still unresolved, nearby
    candidates = db.execute(
        "SELECT * FROM reports WHERE category = ? AND status != 'resolved'",
        (ai["category"],),
    ).fetchall()
    match = next(
        (c for c in candidates
         if distance_m(lat, lng, c["lat"], c["lng"]) <= DUPLICATE_RADIUS_M),
        None,
    )

    if match:
        dup = (match["duplicate_count"] or 0) + 1
        # More people reporting = higher priority (capped at 10)
        priority = min(10, max(match["priority"] or 0, ai["severity"]) + 1)
        db.execute(
            "UPDATE reports SET duplicate_count = ?, priority = ?, merged = 1 WHERE id = ?",
            (dup, priority, match["id"]),
        )
        db.commit()
        row = db.execute("SELECT * FROM reports WHERE id = ?", (match["id"],)).fetchone()
        db.close()
        out = row_to_dict(row)
        out["merged"] = True
        return out

    cur = db.execute(
        """INSERT INTO reports (category, description_original, description_english,
           severity, priority, duplicate_count, lat, lng, status, image_url,
           created_at, merged, estimated_cost, estimated_hours)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ai["category"], ai["description_original"], ai["description_english"],
            ai["severity"], ai["severity"], 0, lat, lng, "open", image_url,
            datetime.utcnow().isoformat(), 0,
            ai["estimated_cost"], ai["estimated_hours"],
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM reports WHERE id = ?", (cur.lastrowid,)).fetchone()
    db.close()
    out = row_to_dict(row)
    out["merged"] = False
    return out


@app.get("/reports")
def get_reports():
    db = db_conn()
    rows = db.execute("SELECT * FROM reports ORDER BY id").fetchall()
    db.close()
    return [row_to_dict(r) for r in rows]


@app.patch("/reports/{report_id}")
def update_report(report_id: int, body: dict = Body(...)):
    status = body.get("status")
    if status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUSES)}")
    db = db_conn()
    cur = db.execute("UPDATE reports SET status = ? WHERE id = ?", (status, report_id))
    db.commit()
    if cur.rowcount == 0:
        db.close()
        raise HTTPException(404, "Report not found")
    row = db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    db.close()
    return row_to_dict(row)
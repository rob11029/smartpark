
from flask import Flask, jsonify, request, render_template, session, redirect, url_for
import sqlite3
import time
import os
import hashlib
import secrets

from csuf_parking_scraper import (
    fetch_all_lots_with_levels,
    fetch_lot_levels,
    fetch_lot_summary,
)

from parking_recommender import merge_live_with_db, recommend_lots

app = Flask(__name__)
BUILDINGS = {
    "library": {"lat": 33.8816, "lng": -117.8854},
    "tsu": {"lat": 33.8812, "lng": -117.8845},  # Titan Student Union
    "gym": {"lat": 33.8830, "lng": -117.8870},
    "mccarthy": {"lat": 33.8797, "lng": -117.8850},
    "gordon": {"lat": 33.8789, "lng": -117.8842},
    "langsdorf": {"lat": 33.8805, "lng": -117.8837}
}
app.secret_key = secrets.token_hex(16)

DB_PATH = os.path.join(os.path.dirname(__file__), "smartpark.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS parking_lots (
            id INTEGER PRIMARY KEY,
            name TEXT,
            lat REAL,
            lng REAL,
            capacity INTEGER,
            available INTEGER,
            last_updated TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            lot_id INTEGER,
            timestamp TEXT
        )
    """)

    conn.commit()
    conn.close()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def calculate_status(available, capacity):
    if available is None:
        return "Closed"

    ratio = (available / capacity) if capacity else 0
    if available <= 0:
        return "Full"
    if ratio < 0.2:
        return "Almost Full"
    if ratio < 0.5:
        return "Busy"
    return "Available"


#Base Recommendation Contribution
def generate_explanation(recommendations):
    if not recommendations:
        return "No parking lots available right now."

    best = recommendations[0]

    name = best.get("name", "This lot")
    distance = best.get("distance_m", 0)
    available = best.get("available", 0)

    return (
        f"{name} is your best option because it is only {int(distance)} meters away "
        f"and currently has {available} available spots."
    )


@app.route("/")
def index():
    return render_template("index.html", user=session.get("user"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        raw_password = request.form.get("password") or ""
        password = hash_password(raw_password)

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email, password)
        ).fetchone()
        conn.close()

        if user:
            session["user"] = {"id": user["id"], "email": user["email"]}
            return redirect(url_for("index"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        raw_password = request.form.get("password") or ""

        if not email or not raw_password:
            return render_template("register.html", error="Email and password are required")

        password = hash_password(raw_password)

        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO users VALUES (NULL, ?, ?, ?)",
                (email, password, time.strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("register.html", error="Email exists")

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/api/parking", methods=["GET"])
def get_parking():
    include_levels = request.args.get("include_levels", "false").lower() == "true"

    try:
        if include_levels:
            data = fetch_all_lots_with_levels()
        else:
            data = fetch_lot_summary()

        return jsonify(data), 200

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch parking",
            "details": str(e)
        }), 500


@app.route("/api/parking/levels/<path:lot_name>", methods=["GET"])
def get_levels(lot_name):
    try:
        data = fetch_lot_levels(lot_name=lot_name)
        return jsonify(data), 200

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch levels",
            "details": str(e)
        }), 500


@app.route("/api/lots")
def get_lots():
    conn = get_db()
    rows = conn.execute("SELECT * FROM parking_lots").fetchall()
    conn.close()

    return jsonify([
        {
            "id": r["id"],
            "name": r["name"],
            "lat": r["lat"],
            "lng": r["lng"],
            "capacity": r["capacity"],
            "available": r["available"],
            "status": calculate_status(r["available"], r["capacity"]),
            "last_updated": r["last_updated"],
        }
        for r in rows
    ])


@app.route("/api/checkin", methods=["POST"])
def checkin():
    data = request.get_json(silent=True) or {}
    lot_id = data.get("lot_id")

    if lot_id is None:
        return jsonify({
            "status": "error",
            "message": "Missing lot_id"
        }), 400

    conn = get_db()
    lot = conn.execute("SELECT * FROM parking_lots WHERE id=?", (lot_id,)).fetchone()

    if not lot:
        conn.close()
        return jsonify({
            "status": "error",
            "message": "Parking lot not found"
        }), 404

    if lot["available"] is None or lot["available"] <= 0:
        conn.close()
        return jsonify({
            "status": "error",
            "message": "Lot full"
        }), 400

    user = session.get("user")
    user_id = user["id"] if user else None

    new_available = lot["available"] - 1
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        "UPDATE parking_lots SET available=?, last_updated=? WHERE id=?",
        (new_available, ts, lot_id)
    )

    conn.execute(
        "INSERT INTO checkins (user_id, lot_id, timestamp) VALUES (?, ?, ?)",
        (user_id, lot_id, ts)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "message": f"Checked into {lot['name']}",
        "available": new_available,
        "lot_id": lot_id,
        "timestamp": ts
    }), 200


@app.route("/api/analytics")
def analytics():
    user = session.get("user")
    if not user:
        return jsonify({"message": "Unauthorized"}), 401

    user_id = user["id"]
    conn = get_db()

    total_checkins_row = conn.execute(
        "SELECT COUNT(*) AS count FROM checkins WHERE user_id=?",
        (user_id,)
    ).fetchone()

    favorite_lot_row = conn.execute("""
        SELECT parking_lots.id, parking_lots.name, COUNT(*) AS cnt
        FROM checkins
        JOIN parking_lots ON parking_lots.id = checkins.lot_id
        WHERE checkins.user_id=?
        GROUP BY parking_lots.id, parking_lots.name
        ORDER BY cnt DESC, parking_lots.name ASC
        LIMIT 1
    """, (user_id,)).fetchone()

    recent_rows = conn.execute("""
        SELECT checkins.timestamp, parking_lots.name AS lot_name
        FROM checkins
        JOIN parking_lots ON parking_lots.id = checkins.lot_id
        WHERE checkins.user_id=?
        ORDER BY checkins.timestamp DESC
        LIMIT 10
    """, (user_id,)).fetchall()

    conn.close()

    return jsonify({
        "total_checkins": total_checkins_row["count"] if total_checkins_row else 0,
        "favorite_lot": {
            "id": favorite_lot_row["id"],
            "name": favorite_lot_row["name"],
            "count": favorite_lot_row["cnt"],
        } if favorite_lot_row else None,
        "recent_checkins": [
            {
                "lot_name": row["lot_name"],
                "timestamp": row["timestamp"],
            }
            for row in recent_rows
        ]
    }), 200

@app.route("/api/recommend", methods=["POST"])
def recommend():
    data = request.get_json(silent=True) or {}

    try:
        user_lat = float(data.get("user_lat"))
        user_lng = float(data.get("user_lng"))
        limit = max(1, min(int(data.get("limit", 3)), 5))
    except (TypeError, ValueError):
        return jsonify({"message": "user_lat, user_lng, and limit must be valid numbers"}), 400

    conn = get_db()
    rows = conn.execute("SELECT * FROM parking_lots").fetchall()
    conn.close()

    db_lots = [dict(r) for r in rows]

    try:
        live_payload = fetch_lot_summary()
        live_lots = live_payload.get("lots", [])
    except Exception:
        live_lots = []

    merged_lots = merge_live_with_db(db_lots, live_lots)
    recommendations = recommend_lots(
        user_lat=user_lat,
        user_lng=user_lng,
        lots=merged_lots,
        limit=limit,
        distance_weight=0.7,
        available_weight=0.3,
    )

    for lot in recommendations:
        lot["status"] = calculate_status(lot["available"], lot["capacity"])

    explanation = generate_explanation(recommendations)

    return jsonify({
    "user_location": {"lat": user_lat, "lng": user_lng},
    "weights": {"distance": 0.7, "available": 0.3},
    "recommendations": recommendations,
    "explanation": explanation
}), 200


@app.route("/api/recommend/building", methods=["POST"])
def recommend_building():
    data = request.get_json(silent=True) or {}
    building = (data.get("building") or "").lower()

    if building not in BUILDINGS:
        return jsonify({"message": "Invalid building"}), 400

    target = BUILDINGS[building]

    conn = get_db()
    rows = conn.execute("SELECT * FROM parking_lots").fetchall()
    conn.close()

    db_lots = [dict(r) for r in rows]

    try:
        live_payload = fetch_lot_summary()
        live_lots = live_payload.get("lots", [])
    except Exception:
        live_lots = []

    merged_lots = merge_live_with_db(db_lots, live_lots)

    recommendations = recommend_lots(
        user_lat=target["lat"],
        user_lng=target["lng"],
        lots=merged_lots,
        limit=3,
        distance_weight=0.9,   # prioritize distance more
        available_weight=0.1,
    )

    for lot in recommendations:
        lot["status"] = calculate_status(lot["available"], lot["capacity"])

    explanation = generate_explanation(recommendations)

    return jsonify({
        "building": building,
        "recommendations": recommendations,
        "explanation": explanation
    }), 200



if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5001)
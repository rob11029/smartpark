from flask import Flask, jsonify, request, render_template, session, redirect, url_for
import sqlite3
import time
import os
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

DB_PATH = os.path.join(os.path.dirname(__file__), 'smartpark.db')

# ─────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Parking lots table
    c.execute('''
        CREATE TABLE IF NOT EXISTS parking_lots (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            lat         REAL NOT NULL,
            lng         REAL NOT NULL,
            capacity    INTEGER NOT NULL,
            available   INTEGER NOT NULL,
            last_updated TEXT
        )
    ''')

    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
    ''')

    # Check-ins table
    c.execute('''
        CREATE TABLE IF NOT EXISTS checkins (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            lot_id      INTEGER NOT NULL,
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (lot_id)  REFERENCES parking_lots(id)
        )
    ''')

    # Seed parking lots if empty (real CSUF data)
    c.execute('SELECT COUNT(*) FROM parking_lots')
    if c.fetchone()[0] == 0:
        lots = [
            (1, 'Nutwood Structure',       33.878742, -117.888837, 2484, 2275),
            (2, 'State College Structure', 33.883105, -117.888612, 1373, 1134),
            (3, 'Eastside North',          33.881100, -117.881850, 1880, 1765),
            (4, 'Eastside South',          33.879800, -117.881200, 1341, 1028),
            (5, 'S8 and S10',              33.882000, -117.883500, 2104,  987),
            (6, 'Fullerton Free Church',   33.876500, -117.890000,  800,    0),
        ]
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        c.executemany(
            'INSERT INTO parking_lots (id, name, lat, lng, capacity, available, last_updated) VALUES (?,?,?,?,?,?,?)',
            [(*l, ts) for l in lots]
        )

    conn.commit()
    conn.close()

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def calculate_status(available, capacity):
    ratio = available / capacity if capacity else 0
    if ratio <= 0.0:
        return 'Closed'
    elif ratio < 0.2:
        return 'Full'
    elif ratio < 0.5:
        return 'Busy'
    else:
        return 'Available'

# ─────────────────────────────────────────
# ROUTES — PAGES
# ─────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', user=session.get('user'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email')
        password = hash_password(request.form.get('password'))
        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE email=? AND password=?', (email, password)
        ).fetchone()
        conn.close()
        if user:
            session['user'] = {'id': user['id'], 'email': user['email']}
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid email or password.')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email    = request.form.get('email')
        password = hash_password(request.form.get('password'))
        try:
            conn = get_db()
            conn.execute(
                'INSERT INTO users (email, password, created_at) VALUES (?,?,?)',
                (email, password, time.strftime('%Y-%m-%d %H:%M:%S'))
            )
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return render_template('register.html', error='Email already registered.')
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ─────────────────────────────────────────
# ROUTES — API
# ─────────────────────────────────────────

@app.route('/api/lots', methods=['GET'])
def get_lots():
    conn = get_db()
    lots = conn.execute('SELECT * FROM parking_lots').fetchall()
    conn.close()
    return jsonify([{
        'id':           l['id'],
        'name':         l['name'],
        'lat':          l['lat'],
        'lng':          l['lng'],
        'capacity':     l['capacity'],
        'available':    l['available'],
        'status':       calculate_status(l['available'], l['capacity']),
        'last_updated': l['last_updated']
    } for l in lots])

@app.route('/api/checkin', methods=['POST'])
def checkin():
    data   = request.get_json()
    lot_id = data.get('lot_id')

    if not isinstance(lot_id, int):
        return jsonify({'status': 'error', 'message': 'Invalid lot ID'}), 400

    conn = get_db()
    lot  = conn.execute('SELECT * FROM parking_lots WHERE id=?', (lot_id,)).fetchone()

    if not lot:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Lot not found'}), 404

    if lot['available'] <= 0:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Lot is full'}), 400

    new_available = lot['available'] - 1
    ts = time.strftime('%Y-%m-%d %H:%M:%S')

    conn.execute(
        'UPDATE parking_lots SET available=?, last_updated=? WHERE id=?',
        (new_available, ts, lot_id)
    )

    # Log check-in if user is logged in
    user_id = session.get('user', {}).get('id')
    conn.execute(
        'INSERT INTO checkins (user_id, lot_id, timestamp) VALUES (?,?,?)',
        (user_id, lot_id, ts)
    )

    conn.commit()
    conn.close()

    return jsonify({
        'status':    'success',
        'message':   f'Checked in at {lot["name"]}',
        'available': new_available,
        'lot_status': calculate_status(new_available, lot['capacity'])
    })

@app.route('/api/analytics', methods=['GET'])
def analytics():
    user_id = session.get('user', {}).get('id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401

    conn = get_db()

    # Total check-ins
    total = conn.execute(
        'SELECT COUNT(*) as cnt FROM checkins WHERE user_id=?', (user_id,)
    ).fetchone()['cnt']

    # Most visited lot
    frequent = conn.execute('''
        SELECT p.name, COUNT(*) as visits
        FROM checkins c
        JOIN parking_lots p ON c.lot_id = p.id
        WHERE c.user_id = ?
        GROUP BY c.lot_id
        ORDER BY visits DESC
        LIMIT 1
    ''', (user_id,)).fetchone()

    # Recent check-ins
    recent = conn.execute('''
        SELECT p.name, c.timestamp
        FROM checkins c
        JOIN parking_lots p ON c.lot_id = p.id
        WHERE c.user_id = ?
        ORDER BY c.timestamp DESC
        LIMIT 5
    ''', (user_id,)).fetchall()

    conn.close()

    return jsonify({
        'total_checkins':  total,
        'favorite_lot':    dict(frequent) if frequent else None,
        'recent_checkins': [dict(r) for r in recent]
    })

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

# SmartPark — CSUF Parking Assistant
CPSC 491 | Team: Roberto Chavez, Shaikh Amin, Xiaohui Gao, Andrew Vu, Amr Mahmoud

## Setup & Run

`ModuleNotFoundError: No module named 'flask'` happens when you run **`python3 app.py`** using system Python, but **`pip install`** put packages somewhere else (another Python, or a venv you are not activating). **Install and run with the same interpreter** — the steps below do that.

```bash
# 1. Go to the app folder (where app.py and requirements.txt live)
cd smartpark

# 2. Create a virtual environment once (skip if .venv already exists)
python3 -m venv .venv

# 3. Install dependencies into that venv (not global pip)
./.venv/bin/pip install -r requirements.txt

# 4. Run with that same venv’s Python
./.venv/bin/python app.py
```

Then open **http://127.0.0.1:5001** in your browser (see `app.py` if the port changes).

**Optional — activate the venv instead of `./.venv/bin/...` paths:**

```bash
cd smartpark
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py               # now uses venv’s python while activated
```

**From repo parent folder** (`490Project/`) without `cd smartpark`:

```bash
python3 -m venv smartpark/.venv
smartpark/.venv/bin/pip install -r smartpark/requirements.txt
smartpark/.venv/bin/python smartpark/app.py
```

## Project Structure
```
smartpark/
├── app.py                  # Flask backend + SQLite DB
├── smartpark.db            # Auto-created on first run
├── requirements.txt
├── templates/
│   ├── index.html          # Main app
│   ├── login.html          # Sign in page
│   └── register.html       # Register page
└── static/
    ├── css/style.css       # All styles
    └── js/main.js          # Map + API logic
```

## API Endpoints
| Method | Endpoint         | Description              |
|--------|-----------------|--------------------------|
| GET    | /api/lots        | Get all parking lots      |
| POST   | /api/checkin     | Check in to a lot         |
| GET    | /api/analytics   | Get user analytics (auth) |

## Parking Lots
1. Nutwood Structure (2,484 spots)
2. State College Structure (1,373 spots)
3. Eastside North (1,880 spots)
4. Eastside South (1,341 spots)
5. S8 and S10 (2,104 spots)
6. Fullerton Free Church (800 spots)

# SmartPark — CSUF Parking Assistant
CPSC 491 | Team: Roberto Chavez, Shaikh Amin, Xiaohui Gao, Andrew Vu

## Setup & Run

```bash
# 1. Navigate to project folder
cd smartpark

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py

# 4. Open your browser
# http://127.0.0.1:5001   (or set PORT=5000 if 5000 is free)
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

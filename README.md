# ClipsFarm 🎬

Automated Twitch clip collector with a PySide6 desktop GUI.
Fetch, filter, score, and manage CS2 (or any game) highlights from the Twitch API — with zero manual searching.

## Features

- 🔍 Fetch existing clips by **game** (e.g. CS2) or a **custom broadcaster watchlist**
- 📅 Filter by **time range** (last 24h, 7d, 30d, or custom dates)
- 📊 Sort by **view count**, created date, duration, or custom score
- 💾 Persist clips to a local **SQLite database** with automatic deduplication
- 📋 **Review queue** — mark clips as Candidate / Approved / Rejected / Uploaded
- 📤 Export to **CSV or JSON**
- 🔄 **Auto-refresh** watchlist on a configurable interval
- 🖥️ Clean PySide6 GUI with dark mode, sortable table, detail pane, and thumbnail preview

## Project Structure

```
ClipsFarm/
├── main.py                  # Entry point
├── config.py                # Settings & credential loader
├── twitch_api.py            # Twitch Helix API client
├── database.py              # SQLite wrapper
├── fetch_worker.py          # QThread background fetch worker
├── watchlist.py             # Saved sources & auto-refresh scheduler
├── gui/
│   ├── main_window.py       # Main application window
│   ├── clips_table.py       # Sortable/filterable clips table widget
│   └── detail_pane.py       # Clip detail & preview panel
├── .env                     # Your Twitch credentials (not committed)
├── .env.example             # Template for credentials
├── requirements.txt
└── clips.db                 # Auto-created SQLite database
```

## Setup

### 1. Clone the repo
```bash
git clone https://github.com/Psmith23434/ClipsFarm.git
cd ClipsFarm
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Create a Twitch application
- Go to https://dev.twitch.tv/console/apps
- Click **Register Your Application**
- Set OAuth redirect URL to `http://localhost`
- Copy your **Client ID** and generate a **Client Secret**

### 4. Configure credentials
```bash
cp .env.example .env
# Edit .env and fill in your TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET
```

### 5. Run
```bash
python main.py
```

## Twitch API Notes

- Uses **Client Credentials flow** (app-level token, no user login required)
- `Get Clips` endpoint returns **existing clips** created by viewers/broadcasters — no clip creation needed
- CS2 Game ID: `1659186957` (fetched automatically by the app via game name lookup)
- Rate limits: ~800 requests/minute on default app token

## Requirements

- Python 3.10+
- PySide6
- See `requirements.txt` for full list

## License

MIT

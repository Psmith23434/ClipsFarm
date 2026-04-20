"""
database.py
SQLite persistence layer for ClipsFarm.
Handles saving clips, deduplication, status management, and CSV/JSON export.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from config import cfg

logger = logging.getLogger(__name__)

# Clip review statuses
STATUS_CANDIDATE = "candidate"
STATUS_APPROVED  = "approved"
STATUS_REJECTED  = "rejected"
STATUS_UPLOADED  = "uploaded"
ALL_STATUSES = [STATUS_CANDIDATE, STATUS_APPROVED, STATUS_REJECTED, STATUS_UPLOADED]


CREATE_CLIPS_TABLE = """
CREATE TABLE IF NOT EXISTS clips (
    clip_id          TEXT PRIMARY KEY,
    url              TEXT,
    embed_url        TEXT,
    thumbnail_url    TEXT,
    title            TEXT,
    broadcaster_id   TEXT,
    broadcaster_name TEXT,
    creator_id       TEXT,
    creator_name     TEXT,
    game_id          TEXT,
    language         TEXT,
    view_count       INTEGER DEFAULT 0,
    duration         REAL    DEFAULT 0.0,
    vod_offset       INTEGER,
    is_featured      INTEGER DEFAULT 0,
    created_at       TEXT,
    fetched_at       TEXT,
    status           TEXT    DEFAULT 'candidate',
    score            REAL    DEFAULT 0.0,
    notes            TEXT    DEFAULT ''
);
"""

CREATE_WATCHLIST_TABLE = """
CREATE TABLE IF NOT EXISTS watchlist (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type      TEXT NOT NULL,  -- 'game' or 'broadcaster'
    source_value     TEXT NOT NULL,  -- game_id or broadcaster_login
    display_name     TEXT,
    enabled          INTEGER DEFAULT 1,
    added_at         TEXT
);
"""


class Database:
    """SQLite database wrapper. Creates the DB file and schema on first use."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or cfg.DB_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------ #
    #  Internal                                                            #
    # ------------------------------------------------------------------ #

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(CREATE_CLIPS_TABLE)
            conn.execute(CREATE_WATCHLIST_TABLE)
            conn.commit()
        logger.info("Database ready: %s", self.db_path)

    # ------------------------------------------------------------------ #
    #  Clips: write                                                        #
    # ------------------------------------------------------------------ #

    def save_clips(self, clips: list[dict]) -> tuple[int, int]:
        """
        Insert clips, skipping duplicates (by clip_id).
        Returns (inserted, skipped) counts.
        """
        inserted = 0
        skipped = 0
        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            for clip in clips:
                score = self._compute_score(clip)
                try:
                    conn.execute(
                        """
                        INSERT INTO clips (
                            clip_id, url, embed_url, thumbnail_url, title,
                            broadcaster_id, broadcaster_name,
                            creator_id, creator_name,
                            game_id, language,
                            view_count, duration, vod_offset, is_featured,
                            created_at, fetched_at, status, score, notes
                        ) VALUES (
                            :clip_id, :url, :embed_url, :thumbnail_url, :title,
                            :broadcaster_id, :broadcaster_name,
                            :creator_id, :creator_name,
                            :game_id, :language,
                            :view_count, :duration, :vod_offset, :is_featured,
                            :created_at, :fetched_at, :status, :score, ''
                        )
                        """,
                        {
                            **clip,
                            "fetched_at": now,
                            "status": STATUS_CANDIDATE,
                            "score": score,
                            "is_featured": int(clip.get("is_featured", False)),
                        },
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    # clip_id already exists — update view_count and score only
                    conn.execute(
                        """
                        UPDATE clips
                        SET view_count = MAX(view_count, :view_count),
                            score = :score
                        WHERE clip_id = :clip_id
                        """,
                        {"clip_id": clip["clip_id"], "view_count": clip["view_count"], "score": score},
                    )
                    skipped += 1
            conn.commit()

        logger.info("save_clips: inserted=%d skipped=%d", inserted, skipped)
        return inserted, skipped

    def update_status(self, clip_id: str, status: str) -> None:
        """Update the review status of a clip."""
        assert status in ALL_STATUSES, f"Invalid status: {status}"
        with self._connect() as conn:
            conn.execute(
                "UPDATE clips SET status = ? WHERE clip_id = ?",
                (status, clip_id),
            )
            conn.commit()

    def update_notes(self, clip_id: str, notes: str) -> None:
        """Update the notes field for a clip."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE clips SET notes = ? WHERE clip_id = ?",
                (notes, clip_id),
            )
            conn.commit()

    def delete_clip(self, clip_id: str) -> None:
        """Permanently remove a clip from the database."""
        with self._connect() as conn:
            conn.execute("DELETE FROM clips WHERE clip_id = ?", (clip_id,))
            conn.commit()

    # ------------------------------------------------------------------ #
    #  Clips: read / query                                                 #
    # ------------------------------------------------------------------ #

    def get_clips(
        self,
        *,
        status: Optional[str] = None,
        game_id: Optional[str] = None,
        broadcaster_name: Optional[str] = None,
        min_views: int = 0,
        language: Optional[str] = None,
        days: Optional[int] = None,
        order_by: str = "score",
        ascending: bool = False,
        limit: int = 500,
    ) -> list[dict]:
        """Query clips from the local database with optional filters."""
        conditions = ["view_count >= :min_views"]
        params: dict = {"min_views": min_views, "limit": limit}

        if status:
            conditions.append("status = :status")
            params["status"] = status
        if game_id:
            conditions.append("game_id = :game_id")
            params["game_id"] = game_id
        if broadcaster_name:
            conditions.append("LOWER(broadcaster_name) LIKE :bname")
            params["bname"] = f"%{broadcaster_name.lower()}%"
        if language:
            conditions.append("language = :language")
            params["language"] = language
        if days:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            conditions.append("created_at >= :cutoff")
            params["cutoff"] = cutoff

        allowed_order = {"score", "view_count", "created_at", "fetched_at", "duration", "title"}
        if order_by not in allowed_order:
            order_by = "score"
        direction = "ASC" if ascending else "DESC"

        where = " AND ".join(conditions)
        sql = f"""
            SELECT * FROM clips
            WHERE {where}
            ORDER BY {order_by} {direction}
            LIMIT :limit
        """

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    def get_clip(self, clip_id: str) -> Optional[dict]:
        """Fetch a single clip by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM clips WHERE clip_id = ?", (clip_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_stats(self) -> dict:
        """Return summary stats for the status bar."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
            by_status = {
                row["status"]: row["cnt"]
                for row in conn.execute(
                    "SELECT status, COUNT(*) as cnt FROM clips GROUP BY status"
                ).fetchall()
            }
        return {"total": total, "by_status": by_status}

    # ------------------------------------------------------------------ #
    #  Export                                                              #
    # ------------------------------------------------------------------ #

    def export_csv(self, path: str, **filter_kwargs) -> int:
        """Export filtered clips to CSV. Returns number of rows written."""
        import csv
        clips = self.get_clips(**filter_kwargs)
        if not clips:
            return 0
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=clips[0].keys())
            writer.writeheader()
            writer.writerows(clips)
        logger.info("Exported %d clips to CSV: %s", len(clips), path)
        return len(clips)

    def export_json(self, path: str, **filter_kwargs) -> int:
        """Export filtered clips to JSON. Returns number of records written."""
        clips = self.get_clips(**filter_kwargs)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(clips, f, indent=2, ensure_ascii=False)
        logger.info("Exported %d clips to JSON: %s", len(clips), path)
        return len(clips)

    # ------------------------------------------------------------------ #
    #  Watchlist                                                           #
    # ------------------------------------------------------------------ #

    def get_watchlist(self) -> list[dict]:
        """Return all watchlist entries."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM watchlist ORDER BY added_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def add_watchlist_entry(
        self,
        source_type: str,
        source_value: str,
        display_name: str = "",
    ) -> int:
        """Add a broadcaster or game to the watchlist. Returns new row ID."""
        assert source_type in ("game", "broadcaster")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO watchlist (source_type, source_value, display_name, enabled, added_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (source_type, source_value, display_name or source_value, now),
            )
            conn.commit()
        return cur.lastrowid or 0

    def remove_watchlist_entry(self, entry_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM watchlist WHERE id = ?", (entry_id,))
            conn.commit()

    def toggle_watchlist_entry(self, entry_id: int, enabled: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE watchlist SET enabled = ? WHERE id = ?",
                (int(enabled), entry_id),
            )
            conn.commit()

    # ------------------------------------------------------------------ #
    #  Scoring                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_score(clip: dict) -> float:
        """
        Simple score: view_count * VIEW_WEIGHT + recency_bonus * RECENCY_WEIGHT.
        recency_bonus decays linearly over 7 days (1.0 = brand new, 0.0 = 7+ days old).
        """
        views = clip.get("view_count", 0)

        recency = 0.0
        created_at = clip.get("created_at", "")
        if created_at:
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400
                recency = max(0.0, 1.0 - age_days / 7.0)
            except ValueError:
                pass

        return (
            views * cfg.SCORE_VIEW_WEIGHT
            + recency * 10_000 * cfg.SCORE_RECENCY_WEIGHT
        )


# Module-level singleton
db = Database()

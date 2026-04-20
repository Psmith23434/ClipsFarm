"""
fetch_worker.py
QThread-based background worker for fetching Twitch clips.
Emits signals so the GUI stays responsive during API calls.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from PySide6.QtCore import QThread, Signal, QObject

from config import cfg
from twitch_api import twitch, TwitchAuthError, TwitchAPIError
from database import db

logger = logging.getLogger(__name__)


class FetchWorker(QObject):
    """
    Worker object (moved to a QThread) that fetches clips from Twitch
    and saves them to the database.

    Signals:
        started()              — fetch has begun
        progress(str)          — status message update
        clip_batch(list)       — emitted after each page/batch of clips
        finished(int, int)     — (inserted, skipped) when complete
        error(str)             — error message string
    """

    started  = Signal()
    progress = Signal(str)
    clip_batch = Signal(list)
    finished = Signal(int, int)
    error    = Signal(str)

    def __init__(
        self,
        *,
        game_id: Optional[str] = None,
        broadcaster_ids: Optional[list[str]] = None,
        broadcaster_logins: Optional[list[str]] = None,
        days: int = 7,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        max_results: int = 100,
        min_views: int = 0,
        language: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.game_id = game_id
        self.broadcaster_ids = broadcaster_ids or []
        self.broadcaster_logins = broadcaster_logins or []
        self.days = days
        self.started_at = started_at
        self.ended_at = ended_at
        self.max_results = max_results
        self.min_views = min_views
        self.language = language
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation. Worker will stop after the current batch."""
        self._cancelled = True

    def run(self) -> None:
        """Main fetch logic. Called by QThread.start()."""
        self.started.emit()
        total_inserted = 0
        total_skipped = 0

        # Resolve date range
        started_at = self.started_at or (
            datetime.now(timezone.utc) - timedelta(days=self.days)
        )
        ended_at = self.ended_at

        try:
            # --- Game-level fetch ---
            if self.game_id and not self._cancelled:
                self.progress.emit(
                    f"Fetching top clips for game ID {self.game_id} · last {self.days}d · max {self.max_results}"
                )
                clips = twitch.get_clips(
                    game_id=self.game_id,
                    started_at=started_at,
                    ended_at=ended_at,
                    max_results=self.max_results,
                    min_views=self.min_views,
                    language=self.language or None,
                )
                if clips:
                    self.clip_batch.emit(clips)
                    ins, skp = db.save_clips(clips)
                    total_inserted += ins
                    total_skipped += skp
                    self.progress.emit(
                        f"Game fetch done — {ins} new, {skp} duplicates"
                    )

            # --- Broadcaster-level fetches (by ID) ---
            for bid in self.broadcaster_ids:
                if self._cancelled:
                    break
                self.progress.emit(f"Fetching clips for broadcaster ID {bid}…")
                clips = twitch.get_clips(
                    broadcaster_id=bid,
                    started_at=started_at,
                    ended_at=ended_at,
                    max_results=self.max_results,
                    min_views=self.min_views,
                    language=self.language or None,
                )
                if clips:
                    self.clip_batch.emit(clips)
                    ins, skp = db.save_clips(clips)
                    total_inserted += ins
                    total_skipped += skp
                    self.progress.emit(
                        f"  → {clips[0].get('broadcaster_name', bid)}: {ins} new, {skp} dupes"
                    )

            # --- Broadcaster-level fetches (by login name) ---
            for login in self.broadcaster_logins:
                if self._cancelled:
                    break
                self.progress.emit(f"Looking up broadcaster: {login}…")
                bid = twitch.get_broadcaster_id(login)
                if not bid:
                    self.progress.emit(f"  ⚠ Broadcaster not found: {login}")
                    continue
                clips = twitch.get_clips(
                    broadcaster_id=bid,
                    started_at=started_at,
                    ended_at=ended_at,
                    max_results=self.max_results,
                    min_views=self.min_views,
                    language=self.language or None,
                )
                if clips:
                    self.clip_batch.emit(clips)
                    ins, skp = db.save_clips(clips)
                    total_inserted += ins
                    total_skipped += skp
                    self.progress.emit(
                        f"  → {login}: {ins} new, {skp} dupes"
                    )

        except TwitchAuthError as e:
            logger.error("Auth error: %s", e)
            self.error.emit(f"Authentication error: {e}")
            return
        except TwitchAPIError as e:
            logger.error("API error: %s", e)
            self.error.emit(f"Twitch API error: {e}")
            return
        except Exception as e:
            logger.exception("Unexpected fetch error")
            self.error.emit(f"Unexpected error: {e}")
            return

        if self._cancelled:
            self.progress.emit("Fetch cancelled.")

        self.finished.emit(total_inserted, total_skipped)


class FetchThread(QThread):
    """
    Convenience wrapper: creates a FetchWorker, moves it to this thread,
    and wires up cleanup on finish.

    Usage:
        self._thread = FetchThread(game_id="1659186957", days=1)
        self._thread.worker.progress.connect(self.on_progress)
        self._thread.worker.finished.connect(self.on_finished)
        self._thread.worker.error.connect(self.on_error)
        self._thread.start()
    """

    def __init__(self, **worker_kwargs) -> None:
        super().__init__()
        self.worker = FetchWorker(**worker_kwargs)
        self.worker.moveToThread(self)
        self.started.connect(self.worker.run)
        self.finished.connect(self.worker.deleteLater)

    def cancel(self) -> None:
        self.worker.cancel()

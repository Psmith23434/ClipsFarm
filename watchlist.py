"""
watchlist.py
Watchlist manager and auto-refresh scheduler for ClipsFarm.
Handles enabling/disabling sources and triggering periodic fetches.
"""

import logging
from typing import Optional, Callable

from PySide6.QtCore import QTimer, QObject, Signal

from config import cfg
from database import db
from fetch_worker import FetchThread

logger = logging.getLogger(__name__)


class WatchlistManager(QObject):
    """
    Manages the watchlist of sources (games + broadcasters) and
    drives the optional auto-refresh QTimer.

    Signals:
        refresh_started()        — auto-refresh cycle has begun
        refresh_finished(int, int) — (inserted, skipped) for the whole cycle
        refresh_error(str)       — error message
        progress(str)            — forwarded from inner FetchThread
    """

    refresh_started  = Signal()
    refresh_finished = Signal(int, int)
    refresh_error    = Signal(str)
    progress         = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._active_thread: Optional[FetchThread] = None
        self._total_inserted = 0
        self._total_skipped = 0

    # ------------------------------------------------------------------ #
    #  Watchlist CRUD (delegates to database.py)                          #
    # ------------------------------------------------------------------ #

    def get_entries(self) -> list[dict]:
        """Return all watchlist entries from the DB."""
        return db.get_watchlist()

    def get_enabled_entries(self) -> list[dict]:
        """Return only enabled watchlist entries."""
        return [e for e in db.get_watchlist() if e["enabled"]]

    def add_game(self, game_id: str, display_name: str = "") -> int:
        """Add a game ID to the watchlist."""
        return db.add_watchlist_entry("game", game_id, display_name)

    def add_broadcaster(self, login: str, display_name: str = "") -> int:
        """Add a broadcaster login to the watchlist."""
        return db.add_watchlist_entry("broadcaster", login, display_name)

    def remove(self, entry_id: int) -> None:
        db.remove_watchlist_entry(entry_id)

    def toggle(self, entry_id: int, enabled: bool) -> None:
        db.toggle_watchlist_entry(entry_id, enabled)

    # ------------------------------------------------------------------ #
    #  Manual fetch                                                        #
    # ------------------------------------------------------------------ #

    def fetch_now(
        self,
        *,
        days: int = 7,
        max_results: int = 100,
        min_views: int = 0,
        language: Optional[str] = None,
        on_progress: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[int, int], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> Optional[FetchThread]:
        """
        Trigger an immediate fetch of all enabled watchlist entries.
        Returns the FetchThread (already started), or None if watchlist is empty.
        """
        entries = self.get_enabled_entries()
        if not entries:
            logger.info("Watchlist is empty or all entries disabled.")
            return None

        game_ids = [
            e["source_value"] for e in entries if e["source_type"] == "game"
        ]
        broadcaster_logins = [
            e["source_value"] for e in entries if e["source_type"] == "broadcaster"
        ]

        # For simplicity: if multiple game IDs, run one fetch per game
        # (Twitch API only supports one game_id per request)
        threads = []
        for gid in game_ids:
            t = FetchThread(
                game_id=gid,
                days=days,
                max_results=max_results,
                min_views=min_views,
                language=language,
            )
            self._wire_thread(t, on_progress, on_finished, on_error)
            threads.append(t)

        if broadcaster_logins:
            t = FetchThread(
                broadcaster_logins=broadcaster_logins,
                days=days,
                max_results=max_results,
                min_views=min_views,
                language=language,
            )
            self._wire_thread(t, on_progress, on_finished, on_error)
            threads.append(t)

        # Start all threads; store last one for cancel reference
        for t in threads:
            t.start()
        self._active_thread = threads[-1] if threads else None
        return self._active_thread

    def cancel(self) -> None:
        """Cancel any in-progress fetch."""
        if self._active_thread:
            self._active_thread.cancel()

    # ------------------------------------------------------------------ #
    #  Auto-refresh timer                                                  #
    # ------------------------------------------------------------------ #

    def start_auto_refresh(self, interval_minutes: Optional[int] = None) -> None:
        """Start the auto-refresh timer."""
        minutes = interval_minutes or cfg.AUTO_REFRESH_INTERVAL_MINUTES
        self._timer.start(minutes * 60 * 1000)
        logger.info("Auto-refresh started: every %d minutes.", minutes)

    def stop_auto_refresh(self) -> None:
        """Stop the auto-refresh timer."""
        self._timer.stop()
        logger.info("Auto-refresh stopped.")

    def is_auto_refresh_active(self) -> bool:
        return self._timer.isActive()

    def set_interval(self, minutes: int) -> None:
        """Update the timer interval (restarts timer if active)."""
        was_active = self._timer.isActive()
        self._timer.stop()
        if was_active:
            self._timer.start(minutes * 60 * 1000)

    def _on_timer(self) -> None:
        logger.info("Auto-refresh triggered.")
        self.refresh_started.emit()
        self.fetch_now(
            days=cfg.DEFAULT_TIME_WINDOW_DAYS,
            max_results=cfg.MAX_CLIPS_PER_FETCH,
            min_views=cfg.MIN_VIEW_COUNT,
            on_progress=lambda msg: self.progress.emit(msg),
            on_finished=lambda ins, skp: self.refresh_finished.emit(ins, skp),
            on_error=lambda err: self.refresh_error.emit(err),
        )

    # ------------------------------------------------------------------ #
    #  Internal                                                            #
    # ------------------------------------------------------------------ #

    def _wire_thread(
        self,
        thread: FetchThread,
        on_progress: Optional[Callable],
        on_finished: Optional[Callable],
        on_error: Optional[Callable],
    ) -> None:
        if on_progress:
            thread.worker.progress.connect(on_progress)
        if on_finished:
            thread.worker.finished.connect(on_finished)
        if on_error:
            thread.worker.error.connect(on_error)
        thread.worker.progress.connect(lambda msg: self.progress.emit(msg))


# Module-level singleton
watchlist = WatchlistManager()

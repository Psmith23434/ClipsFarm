"""
gui/main_window.py
Main application window for ClipsFarm.
Sidebar (watchlist + fetch controls) | Clips table | Detail pane
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from config import cfg
from database import db, ALL_STATUSES
from fetch_worker import FetchThread
from watchlist import watchlist
from gui.clips_table import ClipsTable
from gui.detail_pane import DetailPane

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dark stylesheet
# ---------------------------------------------------------------------------
DARK_QSS = """
QWidget {
    background-color: #1c1b19;
    color: #cdccca;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #171614;
}
QToolBar {
    background-color: #1c1b19;
    border-bottom: 1px solid #262523;
    padding: 2px 6px;
    spacing: 4px;
}
QToolBar QToolButton {
    background: transparent;
    border: none;
    border-radius: 5px;
    padding: 4px 8px;
    color: #cdccca;
}
QToolBar QToolButton:hover  { background: #2d2c2a; }
QToolBar QToolButton:pressed { background: #393836; }
QStatusBar {
    background-color: #171614;
    border-top: 1px solid #262523;
    color: #797876;
    font-size: 12px;
    padding: 2px 8px;
}
QSplitter::handle { background: #262523; width: 1px; }
QGroupBox {
    border: 1px solid #393836;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
    color: #9a9997;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    top: -1px;
}
QPushButton {
    background-color: #2d2c2a;
    border: 1px solid #393836;
    border-radius: 5px;
    padding: 5px 14px;
    color: #cdccca;
    font-weight: 500;
}
QPushButton:hover   { background-color: #393836; border-color: #4a4947; }
QPushButton:pressed { background-color: #4a4947; }
QPushButton#btn_primary {
    background-color: #01696f;
    border-color: #01696f;
    color: #f9f8f5;
    font-weight: 600;
}
QPushButton#btn_primary:hover   { background-color: #0c4e54; }
QPushButton#btn_primary:pressed { background-color: #0f3638; }
QPushButton#btn_danger {
    background-color: #3d1a1a;
    border-color: #6b2c2c;
    color: #e07070;
}
QPushButton#btn_danger:hover { background-color: #4d2020; }
QLineEdit, QSpinBox, QComboBox {
    background-color: #201f1d;
    border: 1px solid #393836;
    border-radius: 5px;
    padding: 4px 8px;
    color: #cdccca;
    selection-background-color: #01696f;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #4f98a3;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: #201f1d;
    border: 1px solid #393836;
    selection-background-color: #01696f;
}
QListWidget {
    background-color: #201f1d;
    border: 1px solid #393836;
    border-radius: 5px;
    outline: none;
}
QListWidget::item { padding: 5px 8px; border-radius: 4px; }
QListWidget::item:selected { background: #313b3b; color: #4f98a3; }
QListWidget::item:hover { background: #2d2c2a; }
QCheckBox { spacing: 6px; }
QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1px solid #393836;
    border-radius: 3px;
    background: #201f1d;
}
QCheckBox::indicator:checked {
    background: #01696f;
    border-color: #01696f;
}
QScrollBar:vertical {
    background: #1c1b19;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #393836;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #4a4947; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QHeaderView::section {
    background-color: #1c1b19;
    color: #797876;
    border: none;
    border-bottom: 1px solid #262523;
    border-right: 1px solid #262523;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
"""


class CredentialsDialog(QDialog):
    """Simple dialog for entering Twitch Client ID and Secret."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Twitch API Credentials")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        info = QLabel(
            "Enter your Twitch application credentials.\n"
            "Get them at: https://dev.twitch.tv/console/apps"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #797876; margin-bottom: 8px;")
        layout.addWidget(info)

        form = QFormLayout()
        self.id_edit = QLineEdit(cfg.TWITCH_CLIENT_ID)
        self.id_edit.setPlaceholderText("Client ID")
        self.secret_edit = QLineEdit(cfg.TWITCH_CLIENT_SECRET)
        self.secret_edit.setPlaceholderText("Client Secret")
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Client ID:", self.id_edit)
        form.addRow("Client Secret:", self.secret_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        cid = self.id_edit.text().strip()
        secret = self.secret_edit.text().strip()
        if not cid or not secret:
            QMessageBox.warning(self, "Missing fields", "Both fields are required.")
            return
        cfg.save_credentials(cid, secret)
        self.accept()


class SidebarWidget(QWidget):
    """Left sidebar: watchlist manager + fetch controls."""

    fetch_requested = None  # will be replaced with a Signal from MainWindow

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(260)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # --- Watchlist group ---
        wl_group = QGroupBox("Watchlist")
        wl_layout = QVBoxLayout(wl_group)
        wl_layout.setSpacing(6)

        self.wl_list = QListWidget()
        self.wl_list.setMinimumHeight(140)
        wl_layout.addWidget(self.wl_list)

        btn_row = QHBoxLayout()
        self.btn_add_game = QPushButton("+ Game")
        self.btn_add_game.setToolTip("Add a game to the watchlist")
        self.btn_add_bc = QPushButton("+ Streamer")
        self.btn_add_bc.setToolTip("Add a broadcaster/streamer to the watchlist")
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setObjectName("btn_danger")
        btn_row.addWidget(self.btn_add_game)
        btn_row.addWidget(self.btn_add_bc)
        btn_row.addWidget(self.btn_remove)
        wl_layout.addLayout(btn_row)
        root.addWidget(wl_group)

        # --- Fetch settings group ---
        fetch_group = QGroupBox("Fetch Settings")
        fetch_layout = QFormLayout(fetch_group)
        fetch_layout.setSpacing(6)

        self.time_combo = QComboBox()
        self.time_combo.addItems(["Last 24 hours", "Last 7 days", "Last 30 days", "Custom"])
        self.time_combo.setCurrentIndex(1)
        fetch_layout.addRow("Time range:", self.time_combo)

        self.min_views_spin = QSpinBox()
        self.min_views_spin.setRange(0, 1_000_000)
        self.min_views_spin.setSingleStep(50)
        self.min_views_spin.setValue(cfg.MIN_VIEW_COUNT)
        fetch_layout.addRow("Min views:", self.min_views_spin)

        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(10, 1000)
        self.max_results_spin.setSingleStep(50)
        self.max_results_spin.setValue(cfg.MAX_CLIPS_PER_FETCH)
        fetch_layout.addRow("Max clips:", self.max_results_spin)

        self.lang_edit = QLineEdit()
        self.lang_edit.setPlaceholderText("e.g. en, de (optional)")
        self.lang_edit.setMaxLength(5)
        fetch_layout.addRow("Language:", self.lang_edit)

        root.addWidget(fetch_group)

        # --- Filter group ---
        filter_group = QGroupBox("Filter Table")
        filter_layout = QFormLayout(filter_group)
        filter_layout.setSpacing(6)

        self.status_filter = QComboBox()
        self.status_filter.addItem("All statuses", None)
        for s in ALL_STATUSES:
            self.status_filter.addItem(s.capitalize(), s)
        filter_layout.addRow("Status:", self.status_filter)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Title / streamer…")
        self.search_edit.setClearButtonEnabled(True)
        filter_layout.addRow("Search:", self.search_edit)

        root.addWidget(filter_group)

        # --- Auto-refresh group ---
        ar_group = QGroupBox("Auto-Refresh")
        ar_layout = QVBoxLayout(ar_group)
        ar_layout.setSpacing(6)

        self.ar_check = QCheckBox("Enable auto-refresh")
        self.ar_check.setChecked(cfg.AUTO_REFRESH_ENABLED)
        ar_layout.addWidget(self.ar_check)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("Every"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(5, 1440)
        self.interval_spin.setValue(cfg.AUTO_REFRESH_INTERVAL_MINUTES)
        self.interval_spin.setSuffix(" min")
        interval_row.addWidget(self.interval_spin)
        ar_layout.addLayout(interval_row)
        root.addWidget(ar_group)

        root.addStretch()

        # --- Fetch button ---
        self.btn_fetch = QPushButton("▶  Fetch Clips")
        self.btn_fetch.setObjectName("btn_primary")
        self.btn_fetch.setFixedHeight(36)
        root.addWidget(self.btn_fetch)

        # Wire watchlist buttons
        self.btn_add_game.clicked.connect(self._add_game)
        self.btn_add_bc.clicked.connect(self._add_broadcaster)
        self.btn_remove.clicked.connect(self._remove_entry)
        self.ar_check.toggled.connect(self._toggle_auto_refresh)
        self.interval_spin.valueChanged.connect(
            lambda v: watchlist.set_interval(v)
        )
        self._refresh_watchlist()

    # ------------------------------------------------------------------
    def _refresh_watchlist(self) -> None:
        self.wl_list.clear()
        for entry in watchlist.get_entries():
            label = f"[{entry['source_type'][0].upper()}] {entry['display_name']}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            item.setCheckState(
                Qt.CheckState.Checked if entry["enabled"] else Qt.CheckState.Unchecked
            )
            self.wl_list.addItem(item)
        self.wl_list.itemChanged.connect(self._on_item_toggled)

    def _on_item_toggled(self, item: QListWidgetItem) -> None:
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        enabled = item.checkState() == Qt.CheckState.Checked
        watchlist.toggle(entry_id, enabled)

    def _add_game(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, "Add Game", "Enter game name or Twitch game ID:"
        )
        if ok and text.strip():
            val = text.strip()
            # If numeric treat as ID, otherwise look up
            if not val.isdigit():
                from twitch_api import twitch
                gid = twitch.get_game_id(val)
                if not gid:
                    QMessageBox.warning(self, "Not found", f"Game not found: {val}")
                    return
                watchlist.add_game(gid, display_name=val)
            else:
                watchlist.add_game(val, display_name=val)
            self._refresh_watchlist()

    def _add_broadcaster(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        login, ok = QInputDialog.getText(
            self, "Add Streamer", "Enter Twitch login name (e.g. s1mple):"
        )
        if ok and login.strip():
            watchlist.add_broadcaster(login.strip().lower(), display_name=login.strip())
            self._refresh_watchlist()

    def _remove_entry(self) -> None:
        item = self.wl_list.currentItem()
        if not item:
            return
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        watchlist.remove(entry_id)
        self._refresh_watchlist()

    def _toggle_auto_refresh(self, checked: bool) -> None:
        if checked:
            watchlist.start_auto_refresh(self.interval_spin.value())
        else:
            watchlist.stop_auto_refresh()

    # ------------------------------------------------------------------
    @property
    def fetch_days(self) -> int:
        mapping = {0: 1, 1: 7, 2: 30, 3: 7}
        return mapping.get(self.time_combo.currentIndex(), 7)

    @property
    def min_views(self) -> int:
        return self.min_views_spin.value()

    @property
    def max_results(self) -> int:
        return self.max_results_spin.value()

    @property
    def language(self) -> Optional[str]:
        v = self.lang_edit.text().strip()
        return v if v else None


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{cfg.APP_NAME} v{cfg.APP_VERSION}")
        self.resize(cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT)
        self.setStyleSheet(DARK_QSS)

        self._fetch_thread: Optional[FetchThread] = None

        self._build_toolbar()
        self._build_central()
        self._build_status_bar()
        self._connect_signals()

        # Show credentials dialog if not configured
        if not cfg.has_credentials():
            QTimer.singleShot(200, self._open_credentials)

        # Initial table load
        QTimer.singleShot(100, self._reload_table)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main toolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        # SVG-free text icons using unicode
        self.act_fetch = QAction("▶  Fetch Now", self)
        self.act_fetch.setToolTip("Fetch clips from all enabled watchlist sources")
        self.act_fetch.triggered.connect(self._fetch_now)
        tb.addAction(self.act_fetch)

        self.act_cancel = QAction("■  Cancel", self)
        self.act_cancel.setToolTip("Cancel current fetch")
        self.act_cancel.setEnabled(False)
        self.act_cancel.triggered.connect(self._cancel_fetch)
        tb.addAction(self.act_cancel)

        tb.addSeparator()

        self.act_export_csv = QAction("↓  Export CSV", self)
        self.act_export_csv.triggered.connect(self._export_csv)
        tb.addAction(self.act_export_csv)

        self.act_export_json = QAction("↓  Export JSON", self)
        self.act_export_json.triggered.connect(self._export_json)
        tb.addAction(self.act_export_json)

        tb.addSeparator()

        self.act_settings = QAction("⚙  Credentials", self)
        self.act_settings.triggered.connect(self._open_credentials)
        tb.addAction(self.act_settings)

    def _build_central(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Sidebar
        self.sidebar = SidebarWidget()
        self.sidebar.btn_fetch.clicked.connect(self._fetch_now)
        self.sidebar.status_filter.currentIndexChanged.connect(self._reload_table)
        self.sidebar.search_edit.textChanged.connect(self._reload_table)
        splitter.addWidget(self.sidebar)

        # Centre: clips table
        self.clips_table = ClipsTable()
        self.clips_table.clip_selected.connect(self._on_clip_selected)
        splitter.addWidget(self.clips_table)

        # Right: detail pane
        self.detail_pane = DetailPane()
        self.detail_pane.status_changed.connect(self._on_status_changed)
        self.detail_pane.notes_saved.connect(self._on_notes_saved)
        splitter.addWidget(self.detail_pane)

        splitter.setSizes([260, 720, 400])
        self.setCentralWidget(splitter)

    def _build_status_bar(self) -> None:
        self._status_label = QLabel("Ready")
        self._stats_label = QLabel("")
        sb = self.statusBar()
        sb.addWidget(self._status_label, 1)
        sb.addPermanentWidget(self._stats_label)
        self._update_stats()

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        watchlist.progress.connect(self._on_progress)
        watchlist.refresh_finished.connect(self._on_fetch_finished)
        watchlist.refresh_error.connect(self._on_fetch_error)

    # ------------------------------------------------------------------
    # Fetch logic
    # ------------------------------------------------------------------

    def _fetch_now(self) -> None:
        if not cfg.has_credentials():
            QMessageBox.warning(
                self, "No credentials",
                "Please set your Twitch credentials first (toolbar \u2699 Credentials)."
            )
            return

        if self._fetch_thread and self._fetch_thread.isRunning():
            return

        sb = self.sidebar
        entries = watchlist.get_enabled_entries()

        if not entries:
            QMessageBox.information(
                self, "Empty watchlist",
                "Add at least one game or streamer to the watchlist first."
            )
            return

        game_ids = [e["source_value"] for e in entries if e["source_type"] == "game"]
        logins   = [e["source_value"] for e in entries if e["source_type"] == "broadcaster"]

        # Launch one thread covering game + broadcaster logins
        self._fetch_thread = FetchThread(
            game_id=game_ids[0] if game_ids else None,
            broadcaster_logins=logins,
            days=sb.fetch_days,
            max_results=sb.max_results,
            min_views=sb.min_views,
            language=sb.language,
        )
        self._fetch_thread.worker.progress.connect(self._on_progress)
        self._fetch_thread.worker.finished.connect(self._on_fetch_finished)
        self._fetch_thread.worker.error.connect(self._on_fetch_error)
        self._fetch_thread.worker.clip_batch.connect(lambda _: self._reload_table())
        self._fetch_thread.finished.connect(self._on_thread_done)
        self._fetch_thread.start()

        self.act_fetch.setEnabled(False)
        self.act_cancel.setEnabled(True)
        self._status_label.setText("Fetching clips…")

    def _cancel_fetch(self) -> None:
        if self._fetch_thread:
            self._fetch_thread.cancel()
        self._status_label.setText("Cancelling…")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_progress(self, msg: str) -> None:
        self._status_label.setText(msg)

    @Slot(int, int)
    def _on_fetch_finished(self, inserted: int, skipped: int) -> None:
        self._status_label.setText(
            f"Done — {inserted} new clip(s) saved, {skipped} duplicate(s) skipped."
        )
        self._reload_table()
        self._update_stats()

    @Slot(str)
    def _on_fetch_error(self, msg: str) -> None:
        self._status_label.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Fetch error", msg)

    @Slot()
    def _on_thread_done(self) -> None:
        self.act_fetch.setEnabled(True)
        self.act_cancel.setEnabled(False)

    @Slot(object)
    def _on_clip_selected(self, clip: dict) -> None:
        self.detail_pane.load_clip(clip)

    @Slot(str, str)
    def _on_status_changed(self, clip_id: str, status: str) -> None:
        db.update_status(clip_id, status)
        self._reload_table()
        self._update_stats()

    @Slot(str, str)
    def _on_notes_saved(self, clip_id: str, notes: str) -> None:
        db.update_notes(clip_id, notes)

    # ------------------------------------------------------------------
    # Table reload & stats
    # ------------------------------------------------------------------

    def _reload_table(self) -> None:
        status = self.sidebar.status_filter.currentData()
        search = self.sidebar.search_edit.text().strip() or None
        clips = db.get_clips(
            status=status,
            broadcaster_name=search,
            min_views=0,
            order_by="score",
            limit=500,
        )
        # Client-side title search
        if search:
            clips = [
                c for c in clips
                if search.lower() in c.get("title", "").lower()
                or search.lower() in c.get("broadcaster_name", "").lower()
            ]
        self.clips_table.load_clips(clips)

    def _update_stats(self) -> None:
        stats = db.get_stats()
        by_s = stats["by_status"]
        parts = [f"Total: {stats['total']}"]
        for s in ALL_STATUSES:
            n = by_s.get(s, 0)
            if n:
                parts.append(f"{s.capitalize()}: {n}")
        self._stats_label.setText("  ·  ".join(parts))

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "clips.csv", "CSV files (*.csv)"
        )
        if path:
            n = db.export_csv(path)
            self._status_label.setText(f"Exported {n} clips to {path}")

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export JSON", "clips.json", "JSON files (*.json)"
        )
        if path:
            n = db.export_json(path)
            self._status_label.setText(f"Exported {n} clips to {path}")

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_credentials(self) -> None:
        dlg = CredentialsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._status_label.setText("Credentials saved.")

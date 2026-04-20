"""
gui/detail_pane.py
Right-side detail panel — shows clip metadata, thumbnail, notes, and status controls.
"""

import webbrowser
from typing import Optional

from PySide6.QtCore import Qt, Signal, QThread, Slot, QObject, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database import ALL_STATUSES


class ThumbnailLoader(QObject):
    """Loads a thumbnail URL in the background using Qt's network stack."""

    loaded = Signal(QPixmap)
    failed = Signal()

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_finished)

    def fetch(self) -> None:
        if not self._url:
            self.failed.emit()
            return
        self._nam.get(QNetworkRequest(QUrl(self._url)))

    @Slot(QNetworkReply)
    def _on_finished(self, reply: QNetworkReply) -> None:
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            px = QPixmap()
            if px.loadFromData(data):
                self.loaded.emit(px)
                reply.deleteLater()
                return
        self.failed.emit()
        reply.deleteLater()


class DetailPane(QWidget):
    """
    Right panel showing full clip details.

    Signals:
        status_changed(clip_id: str, status: str)
        notes_saved(clip_id: str, notes: str)
    """

    status_changed = Signal(str, str)
    notes_saved    = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._current_clip: Optional[dict] = None
        self._thumb_loader: Optional[ThumbnailLoader] = None

        self._build_ui()
        self._show_empty()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scrollable inner area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #171614; border: none; }")

        container = QWidget()
        container.setStyleSheet("background: #171614;")
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(12)

        # --- Thumbnail ---
        self._thumb_label = QLabel()
        self._thumb_label.setFixedHeight(160)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet(
            "background: #1c1b19; border-radius: 6px; color: #5a5957;"
        )
        self._thumb_label.setText("No clip selected")
        self._layout.addWidget(self._thumb_label)

        # --- Title ---
        self._title_label = QLabel()
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet(
            "color: #cdccca; font-size: 14px; font-weight: 600; line-height: 1.4;"
        )
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._layout.addWidget(self._title_label)

        # --- Metadata form ---
        meta_group = QGroupBox("Details")
        meta_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #262523;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 8px;
                font-weight: 600;
                color: #5a5957;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                top: -1px;
            }
        """)
        meta_form = QFormLayout(meta_group)
        meta_form.setSpacing(6)
        meta_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _meta_val(text="") -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #cdccca; font-size: 12px;")
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return lbl

        def _meta_key(text) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #5a5957; font-size: 11px;")
            return lbl

        self._lbl_streamer  = _meta_val()
        self._lbl_creator   = _meta_val()
        self._lbl_views     = _meta_val()
        self._lbl_duration  = _meta_val()
        self._lbl_language  = _meta_val()
        self._lbl_created   = _meta_val()
        self._lbl_score     = _meta_val()
        self._lbl_clip_id   = _meta_val()

        meta_form.addRow(_meta_key("Streamer:"),  self._lbl_streamer)
        meta_form.addRow(_meta_key("Creator:"),   self._lbl_creator)
        meta_form.addRow(_meta_key("Views:"),      self._lbl_views)
        meta_form.addRow(_meta_key("Duration:"),   self._lbl_duration)
        meta_form.addRow(_meta_key("Language:"),   self._lbl_language)
        meta_form.addRow(_meta_key("Created:"),    self._lbl_created)
        meta_form.addRow(_meta_key("Score:"),      self._lbl_score)
        meta_form.addRow(_meta_key("Clip ID:"),    self._lbl_clip_id)
        self._layout.addWidget(meta_group)

        # --- Status ---
        status_group = QGroupBox("Status")
        status_group.setStyleSheet(meta_group.styleSheet())
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(6)

        self._status_combo = QComboBox()
        for s in ALL_STATUSES:
            self._status_combo.addItem(s.capitalize(), s)
        self._status_combo.setStyleSheet("""
            QComboBox {
                background: #201f1d;
                border: 1px solid #393836;
                border-radius: 5px;
                padding: 4px 8px;
                color: #cdccca;
            }
            QComboBox:focus { border-color: #4f98a3; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background: #201f1d;
                border: 1px solid #393836;
                selection-background-color: #01696f;
            }
        """)

        self._btn_save_status = QPushButton("Save status")
        self._btn_save_status.setObjectName("btn_primary")
        self._btn_save_status.setStyleSheet("""
            QPushButton {
                background-color: #01696f;
                border: none;
                border-radius: 5px;
                padding: 5px 14px;
                color: #f9f8f5;
                font-weight: 600;
            }
            QPushButton:hover   { background-color: #0c4e54; }
            QPushButton:pressed { background-color: #0f3638; }
            QPushButton:disabled { background-color: #2d2c2a; color: #5a5957; }
        """)
        self._btn_save_status.setEnabled(False)
        self._btn_save_status.clicked.connect(self._save_status)

        status_layout.addWidget(self._status_combo)
        status_layout.addWidget(self._btn_save_status)
        self._layout.addWidget(status_group)

        # --- Notes ---
        notes_group = QGroupBox("Notes")
        notes_group.setStyleSheet(meta_group.styleSheet())
        notes_layout = QVBoxLayout(notes_group)
        notes_layout.setSpacing(6)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Add notes, tags, ideas…")
        self._notes_edit.setFixedHeight(90)
        self._notes_edit.setStyleSheet("""
            QTextEdit {
                background: #201f1d;
                border: 1px solid #393836;
                border-radius: 5px;
                padding: 6px 8px;
                color: #cdccca;
                font-size: 12px;
            }
            QTextEdit:focus { border-color: #4f98a3; }
        """)
        self._notes_edit.setEnabled(False)

        self._btn_save_notes = QPushButton("Save notes")
        self._btn_save_notes.setStyleSheet("""
            QPushButton {
                background-color: #2d2c2a;
                border: 1px solid #393836;
                border-radius: 5px;
                padding: 5px 14px;
                color: #cdccca;
                font-weight: 500;
            }
            QPushButton:hover   { background-color: #393836; }
            QPushButton:pressed { background-color: #4a4947; }
            QPushButton:disabled { color: #5a5957; }
        """)
        self._btn_save_notes.setEnabled(False)
        self._btn_save_notes.clicked.connect(self._save_notes)

        notes_layout.addWidget(self._notes_edit)
        notes_layout.addWidget(self._btn_save_notes)
        self._layout.addWidget(notes_group)

        # --- Action buttons ---
        btn_row = QHBoxLayout()
        self._btn_open = QPushButton("🔗  Open in Browser")
        self._btn_open.setStyleSheet("""
            QPushButton {
                background-color: #2d2c2a;
                border: 1px solid #393836;
                border-radius: 5px;
                padding: 5px 14px;
                color: #4f98a3;
                font-weight: 500;
            }
            QPushButton:hover   { background-color: #313b3b; }
            QPushButton:pressed { background-color: #393836; }
            QPushButton:disabled { color: #5a5957; }
        """)
        self._btn_open.setEnabled(False)
        self._btn_open.clicked.connect(self._open_in_browser)

        self._btn_copy_url = QPushButton("Copy URL")
        self._btn_copy_url.setStyleSheet(self._btn_open.styleSheet().replace("#4f98a3", "#cdccca"))
        self._btn_copy_url.setEnabled(False)
        self._btn_copy_url.clicked.connect(self._copy_url)

        btn_row.addWidget(self._btn_open)
        btn_row.addWidget(self._btn_copy_url)
        self._layout.addLayout(btn_row)

        self._layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_clip(self, clip: dict) -> None:
        """Populate the pane with data from a clip dict."""
        self._current_clip = clip

        # Thumbnail
        thumb_url = clip.get("thumbnail_url", "")
        self._thumb_label.setText("Loading…")
        self._thumb_label.setPixmap(QPixmap())  # clear old
        if thumb_url:
            self._thumb_loader = ThumbnailLoader(thumb_url, self)
            self._thumb_loader.loaded.connect(self._on_thumb_loaded)
            self._thumb_loader.failed.connect(self._on_thumb_failed)
            self._thumb_loader.fetch()
        else:
            self._thumb_label.setText("No thumbnail")

        # Title
        self._title_label.setText(clip.get("title", ""))

        # Metadata
        self._lbl_streamer.setText(clip.get("broadcaster_name", ""))
        self._lbl_creator.setText(clip.get("creator_name", ""))
        self._lbl_views.setText(f"{int(clip.get('view_count') or 0):,}")
        self._lbl_duration.setText(f"{float(clip.get('duration') or 0):.1f}s")
        self._lbl_language.setText(clip.get("language", "") or "—")
        created = str(clip.get("created_at", "") or "")[:19].replace("T", "  ")
        self._lbl_created.setText(created or "—")
        self._lbl_score.setText(f"{float(clip.get('score') or 0):.1f}")
        self._lbl_clip_id.setText(clip.get("clip_id", ""))

        # Status combo
        status = clip.get("status", "candidate")
        idx = self._status_combo.findData(status)
        if idx >= 0:
            self._status_combo.setCurrentIndex(idx)

        # Notes
        self._notes_edit.setPlainText(clip.get("notes", "") or "")

        # Enable controls
        self._btn_save_status.setEnabled(True)
        self._btn_save_notes.setEnabled(True)
        self._btn_open.setEnabled(bool(clip.get("url")))
        self._btn_copy_url.setEnabled(bool(clip.get("url")))
        self._notes_edit.setEnabled(True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _show_empty(self) -> None:
        self._title_label.setText("")
        for lbl in (
            self._lbl_streamer, self._lbl_creator, self._lbl_views,
            self._lbl_duration, self._lbl_language, self._lbl_created,
            self._lbl_score, self._lbl_clip_id,
        ):
            lbl.setText("—")
        self._notes_edit.clear()
        self._btn_save_status.setEnabled(False)
        self._btn_save_notes.setEnabled(False)
        self._btn_open.setEnabled(False)
        self._btn_copy_url.setEnabled(False)
        self._notes_edit.setEnabled(False)

    @Slot(QPixmap)
    def _on_thumb_loaded(self, px: QPixmap) -> None:
        scaled = px.scaledToWidth(
            self._thumb_label.width() or 320,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumb_label.setPixmap(scaled)
        self._thumb_label.setText("")

    @Slot()
    def _on_thumb_failed(self) -> None:
        self._thumb_label.setText("Thumbnail unavailable")

    def _save_status(self) -> None:
        if not self._current_clip:
            return
        status = self._status_combo.currentData()
        self.status_changed.emit(self._current_clip["clip_id"], status)

    def _save_notes(self) -> None:
        if not self._current_clip:
            return
        notes = self._notes_edit.toPlainText()
        self.notes_saved.emit(self._current_clip["clip_id"], notes)

    def _open_in_browser(self) -> None:
        if self._current_clip:
            url = self._current_clip.get("url", "")
            if url:
                QDesktopServices.openUrl(QUrl(url))

    def _copy_url(self) -> None:
        if self._current_clip:
            url = self._current_clip.get("url", "")
            if url:
                from PySide6.QtWidgets import QApplication
                QApplication.clipboard().setText(url)

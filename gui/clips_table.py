"""
gui/clips_table.py
Sortable, filterable clips table widget.
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal, QSortFilterProxyModel, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from database import (
    db,
    STATUS_CANDIDATE,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_UPLOADED,
)

logger = logging.getLogger(__name__)

# Column definitions: (header_label, clip_dict_key)
COLUMNS = [
    ("#",           None),          # row number
    ("Title",       "title"),
    ("Streamer",    "broadcaster_name"),
    ("Creator",     "creator_name"),
    ("Views",       "view_count"),
    ("Duration",    "duration"),
    ("Score",       "score"),
    ("Language",    "language"),
    ("Status",      "status"),
    ("Created",     "created_at"),
]

STATUS_COLORS = {
    STATUS_CANDIDATE: QColor("#797876"),
    STATUS_APPROVED:  QColor("#6daa45"),
    STATUS_REJECTED:  QColor("#d163a7"),
    STATUS_UPLOADED:  QColor("#4f98a3"),
}


class ClipsModel(QAbstractTableModel):
    """Qt table model backed by a list of clip dicts."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._clips: list[dict] = []

    def load(self, clips: list[dict]) -> None:
        self.beginResetModel()
        self._clips = clips
        self.endResetModel()

    def clip_at(self, row: int) -> Optional[dict]:
        if 0 <= row < len(self._clips):
            return self._clips[row]
        return None

    # --- QAbstractTableModel interface ---

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._clips)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row, col = index.row(), index.column()
        clip = self._clips[row]
        col_key = COLUMNS[col][1]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(row + 1)
            val = clip.get(col_key, "")
            if col_key == "duration":
                return f"{float(val or 0):.1f}s"
            if col_key == "score":
                return f"{float(val or 0):.0f}"
            if col_key == "created_at" and val:
                return str(val)[:10]   # date only
            if col_key == "view_count":
                return f"{int(val or 0):,}"
            return str(val) if val is not None else ""

        if role == Qt.ItemDataRole.ForegroundRole and col_key == "status":
            status = clip.get("status", STATUS_CANDIDATE)
            return STATUS_COLORS.get(status, QColor("#797876"))

        if role == Qt.ItemDataRole.UserRole:
            return clip  # full clip dict for selection

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col_key in ("view_count", "duration", "score", None):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def sort(self, column: int, order=Qt.SortOrder.DescendingOrder) -> None:
        key = COLUMNS[column][1]
        if key is None:
            return
        reverse = order == Qt.SortOrder.DescendingOrder
        self.beginResetModel()
        self._clips.sort(key=lambda c: (c.get(key) or 0), reverse=reverse)
        self.endResetModel()


class ClipsTable(QWidget):
    """
    Full clips table widget with context menu and selection signal.

    Signals:
        clip_selected(dict)  — emitted when a row is clicked/activated
    """

    clip_selected = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._model = ClipsModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)  # search all columns

        self._view = QTableView()
        self._view.setModel(self._proxy)
        self._view.setSortingEnabled(True)
        self._view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._view.setAlternatingRowColors(False)
        self._view.verticalHeader().setVisible(False)
        self._view.setShowGrid(False)
        self._view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Column sizing
        hh = self._view.horizontalHeader()
        hh.setDefaultSectionSize(100)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)   # Title stretches
        hh.resizeSection(0, 36)   # #
        hh.resizeSection(2, 130)  # Streamer
        hh.resizeSection(3, 110)  # Creator
        hh.resizeSection(4, 80)   # Views
        hh.resizeSection(5, 70)   # Duration
        hh.resizeSection(6, 70)   # Score
        hh.resizeSection(7, 60)   # Language
        hh.resizeSection(8, 90)   # Status
        hh.resizeSection(9, 90)   # Created

        self._view.setStyleSheet("""
            QTableView {
                background-color: #1c1b19;
                alternate-background-color: #201f1d;
                border: none;
                outline: none;
                gridline-color: transparent;
            }
            QTableView::item {
                padding: 4px 8px;
                border: none;
            }
            QTableView::item:selected {
                background-color: #313b3b;
                color: #cdccca;
            }
            QTableView::item:hover {
                background-color: #252422;
            }
        """)

        self._view.clicked.connect(self._on_row_clicked)
        self._view.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self._view)

    def load_clips(self, clips: list[dict]) -> None:
        self._model.load(clips)

    def _on_row_clicked(self, index: QModelIndex) -> None:
        source_index = self._proxy.mapToSource(index)
        clip = self._model.clip_at(source_index.row())
        if clip:
            self.clip_selected.emit(clip)

    def _show_context_menu(self, pos) -> None:
        index = self._view.indexAt(pos)
        if not index.isValid():
            return
        source_index = self._proxy.mapToSource(index)
        clip = self._model.clip_at(source_index.row())
        if not clip:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #201f1d;
                border: 1px solid #393836;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item { padding: 5px 24px 5px 12px; border-radius: 4px; }
            QMenu::item:selected { background: #313b3b; color: #4f98a3; }
            QMenu::separator { height: 1px; background: #393836; margin: 3px 8px; }
        """)

        act_open = menu.addAction("🔗  Open clip in browser")
        menu.addSeparator()
        act_approve  = menu.addAction("✅  Mark Approved")
        act_reject   = menu.addAction("❌  Mark Rejected")
        act_uploaded = menu.addAction("⬆  Mark Uploaded")
        act_candidate = menu.addAction("○  Reset to Candidate")
        menu.addSeparator()
        act_delete = menu.addAction("🗑  Delete from database")

        action = menu.exec(self._view.viewport().mapToGlobal(pos))
        if not action:
            return

        clip_id = clip["clip_id"]
        if action == act_open:
            import webbrowser
            webbrowser.open(clip.get("url", ""))
        elif action == act_approve:
            db.update_status(clip_id, "approved")
        elif action == act_reject:
            db.update_status(clip_id, "rejected")
        elif action == act_uploaded:
            db.update_status(clip_id, "uploaded")
        elif action == act_candidate:
            db.update_status(clip_id, "candidate")
        elif action == act_delete:
            db.delete_clip(clip_id)

        # Refresh parent table via model reload from DB
        self.clip_selected.emit(clip)  # re-emit to keep detail pane in sync

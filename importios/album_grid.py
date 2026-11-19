"""Album and Artist grid view for quick browsing and whole-album / whole-artist selection."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

from .i18n import tr
from .models import text_key


class CollectionGridView(QListWidget):
    """Card grid grouped by Album or Artist; double-click inspects, checkbox marks all songs."""
    groupCheckToggled = Signal(list, bool)
    groupActivated = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('collectionGrid')
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setWrapping(True)
        self.setSpacing(12)
        self.setIconSize(QSize(116, 116))
        self.setGridSize(QSize(156, 186))
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformItemSizes(True)
        self._mode = 'albums'
        self._groups = []
        self._updating = False
        self.itemChanged.connect(self._on_item_changed)
        self.itemDoubleClicked.connect(self._on_double_clicked)

    def populate(self, tracks, checked_ids, icons, default_icon, mode='albums'):
        self._mode = mode
        grouped = {}
        for track in tracks:
            if mode == 'artists':
                artist = track.get('artist') or 'Sin artista'
                key = text_key(artist)
                entry = grouped.setdefault(key, {'title': artist, 'subtitle': '', 'tracks': [], 'ids': []})
            else:
                album = track.get('album') or 'Sin álbum'
                artist = track.get('artist') or 'Sin artista'
                key = (text_key(album), text_key(artist))
                entry = grouped.setdefault(key, {'title': album, 'subtitle': artist, 'tracks': [], 'ids': []})
            entry['tracks'].append(track)
            entry['ids'].append(track['id'])

        groups = sorted(grouped.values(), key=lambda g: text_key(g['title']))
        self._groups = groups
        self._updating = True
        self.blockSignals(True)
        try:
            self.clear()
            for idx, group in enumerate(groups):
                count = len(group['ids'])
                if mode == 'artists':
                    albums = len({text_key(t.get('album') or '') for t in group['tracks']})
                    caption = f"{group['title']}\n{tr(f'{count} canciones')} · {tr(f'{albums} álbumes')}"
                else:
                    caption = f"{group['title']}\n{group['subtitle']} · {count}"
                icon = next((icons[tid] for tid in group['ids'] if tid in icons), None) or default_icon or QIcon()
                item = QListWidgetItem(icon, caption)
                item.setData(Qt.ItemDataRole.UserRole, idx)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                marked = sum(tid in checked_ids for tid in group['ids'])
                state = (
                    Qt.CheckState.Checked if marked == count and count > 0
                    else Qt.CheckState.PartiallyChecked if marked > 0
                    else Qt.CheckState.Unchecked
                )
                item.setCheckState(state)
                item.setToolTip(f"{group['title']} ({count})")
                self.addItem(item)
        finally:
            self.blockSignals(False)
            self._updating = False

    def sync_checks(self, checked_ids):
        """Update checkbox states in-place without destroying QListWidgetItems."""
        self._updating = True
        self.blockSignals(True)
        try:
            for row in range(self.count()):
                item = self.item(row)
                idx = item.data(Qt.ItemDataRole.UserRole)
                if not isinstance(idx, int) or not 0 <= idx < len(self._groups):
                    continue
                ids = self._groups[idx]['ids']
                count = len(ids)
                marked = sum(tid in checked_ids for tid in ids)
                state = (
                    Qt.CheckState.Checked if marked == count and count > 0
                    else Qt.CheckState.PartiallyChecked if marked > 0
                    else Qt.CheckState.Unchecked
                )
                if item.checkState() != state:
                    item.setCheckState(state)
        finally:
            self.blockSignals(False)
            self._updating = False

    def _on_item_changed(self, item):
        if self._updating:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(idx, int) or not 0 <= idx < len(self._groups):
            return
        checked = item.checkState() != Qt.CheckState.Unchecked
        self.groupCheckToggled.emit(list(self._groups[idx]['ids']), checked)

    def _on_double_clicked(self, item):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(idx, int) or not 0 <= idx < len(self._groups):
            return
        self.groupActivated.emit(self._mode, self._groups[idx]['title'])

"""Library rows are rendered on demand; no object is allocated for every cell."""
from PySide6.QtCore import QAbstractTableModel, Qt
from collections import OrderedDict


class LibraryModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks = []
        self.icons = OrderedDict()
        self.default_icon = None

    def replace(self, tracks):
        self.beginResetModel()
        self.tracks = tracks
        self.icons.clear()
        self.endResetModel()

    def set_icon(self, identifier, icon):
        self.icons[identifier] = icon
        self.icons.move_to_end(identifier)
        while len(self.icons)>256:
            old,_ = self.icons.popitem(last=False)
            self._icon_changed(old)
        self._icon_changed(identifier)

    def _icon_changed(self, identifier):
        for row,track in enumerate(self.tracks):
            if track.get('id') == identifier:
                index = self.index(row,0)
                self.dataChanged.emit(index,index,[Qt.ItemDataRole.DecorationRole])
                break

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.tracks)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else 5

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal and 0 <= section < 5:
            return ['Canción', 'Artista', 'Álbum', 'Duración', 'Archivo por USB'][section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and index.column() == 0 and role == Qt.ItemDataRole.DecorationRole:
            return self.icons.get(self.tracks[index.row()].get('id'),self.default_icon)
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        track = self.tracks[index.row()]
        if index.column() < 3:
            return track[['title', 'artist', 'album'][index.column()]]
        if index.column() == 4:
            path = track.get('afc_path')
            return 'Original protegido' if path and path.lower().endswith('.m4p') else 'Disponible' if path else 'No accesible'
        seconds = int(track['duration'])
        return f'{seconds//60}:{seconds%60:02}'

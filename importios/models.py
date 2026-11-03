"""Library rows are rendered on demand; no object is allocated for every cell."""
from PySide6.QtCore import QAbstractTableModel, Qt


class LibraryModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks = []

    def replace(self, tracks):
        self.beginResetModel()
        self.tracks = tracks
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.tracks)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal and 0 <= section < 4:
            return ['Canción', 'Artista', 'Álbum', 'Duración'][section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        track = self.tracks[index.row()]
        if index.column() < 3:
            return track[['title', 'artist', 'album'][index.column()]]
        seconds = int(track['duration'])
        return f'{seconds//60}:{seconds%60:02}'

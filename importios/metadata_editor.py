"""Non-destructive metadata and cover editor dialog for songs queued for import."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QFileDialog, QFormLayout, QHBoxLayout, QVBoxLayout

from .i18n import QLabel, QLineEdit, QPushButton, tr
from .visuals import rounded_cover


class MetadataEditorDialog(QDialog):
    """Edit title, artist, album, genre, year, numbering and cover for one queued song."""
    def __init__(self, track, default_icon, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Editar metadatos antes de importar'))
        self.resize(520, 460)
        self._custom_cover = track.get('custom_artwork_path')
        self._default_icon = default_icon
        self._original_thumbnail = track.get('thumbnail')

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        note = QLabel(tr('Los cambios se aplican solo al enviar la canción al iPhone. El archivo original del ordenador no se modifica.'))
        note.setWordWrap(True)
        note.setObjectName('muted')
        root.addWidget(note)

        body = QHBoxLayout()
        body.setSpacing(18)

        cover_col = QVBoxLayout()
        cover_col.setSpacing(10)
        self.cover_preview = QLabel()
        self.cover_preview.setObjectName('cover')
        self.cover_preview.setFixedSize(136, 136)
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_col.addWidget(self.cover_preview, 0, Qt.AlignmentFlag.AlignHCenter)
        choose_cover = QPushButton(tr('Elegir portada…'))
        choose_cover.clicked.connect(self._pick_cover)
        cover_col.addWidget(choose_cover)
        clear_cover = QPushButton(tr('Quitar cambio'))
        clear_cover.clicked.connect(self._reset_cover)
        cover_col.addWidget(clear_cover)
        cover_col.addStretch()
        body.addLayout(cover_col)

        form = QFormLayout()
        form.setSpacing(10)
        overrides = track.get('metadata_overrides') or {}

        def initial(key, fallback=''):
            val = overrides.get(key, track.get(key, fallback))
            return '' if val is None else str(val)

        self.title_edit = QLineEdit(initial('title'))
        self.artist_edit = QLineEdit(initial('artist'))
        self.album_edit = QLineEdit(initial('album'))
        self.album_artist_edit = QLineEdit(initial('album_artist', initial('artist')))
        self.genre_edit = QLineEdit(initial('genre'))
        self.year_edit = QLineEdit(initial('year'))
        self.year_edit.setPlaceholderText('2026')
        self.track_edit = QLineEdit(initial('track_number'))
        self.track_edit.setPlaceholderText('1')
        self.disc_edit = QLineEdit(initial('disc_number'))
        self.disc_edit.setPlaceholderText('1')

        form.addRow(QLabel(tr('Título')), self.title_edit)
        form.addRow(QLabel(tr('Artista')), self.artist_edit)
        form.addRow(QLabel(tr('Álbum')), self.album_edit)
        form.addRow(QLabel(tr('Artista del álbum')), self.album_artist_edit)
        form.addRow(QLabel(tr('Género')), self.genre_edit)
        form.addRow(QLabel(tr('Año')), self.year_edit)

        nums = QHBoxLayout()
        nums.setSpacing(8)
        nums.addWidget(self.track_edit)
        nums.addWidget(QLabel(tr('Disco')))
        nums.addWidget(self.disc_edit)
        form.addRow(QLabel(tr('Pista')), nums)

        body.addLayout(form, 1)
        root.addLayout(body, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(tr('Cancelar'))
        cancel.clicked.connect(self.reject)
        save = QPushButton(tr('Guardar cambios'))
        save.setObjectName('primary')
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self._refresh_cover()

    def _refresh_cover(self):
        pix = QPixmap()
        if self._custom_cover and Path(self._custom_cover).is_file():
            pix.load(str(self._custom_cover))
        elif self._original_thumbnail:
            pix.loadFromData(self._original_thumbnail)
        if not pix.isNull():
            self.cover_preview.setPixmap(rounded_cover(pix, 136, 12))
        elif self._default_icon is not None:
            self.cover_preview.setPixmap(self._default_icon.pixmap(96, 96))

    def _pick_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Elegir portada'), '', tr('Imágenes (*.jpg *.jpeg *.png)'))
        if path:
            self._custom_cover = path
            self._refresh_cover()

    def _reset_cover(self):
        self._custom_cover = None
        self._refresh_cover()

    def result_values(self):
        overrides = {
            'title': self.title_edit.text().strip(),
            'artist': self.artist_edit.text().strip(),
            'album': self.album_edit.text().strip(),
            'album_artist': self.album_artist_edit.text().strip(),
            'genre': self.genre_edit.text().strip(),
        }
        for key, widget, low, high in (
            ('year', self.year_edit, 1, 9999),
            ('track_number', self.track_edit, 1, 65535),
            ('disc_number', self.disc_edit, 1, 65535),
        ):
            raw = widget.text().strip()
            if raw.isdigit() and low <= int(raw) <= high:
                overrides[key] = int(raw)
            elif not raw:
                overrides[key] = None
        return overrides, self._custom_cover

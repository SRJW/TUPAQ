"""Virtual song rows with stable selection while sorting by values, not labels."""
from collections import OrderedDict
import unicodedata
import math

from PySide6.QtCore import QAbstractTableModel,Qt
from PySide6.QtWidgets import QTableWidgetItem

SORT_ROLE = int(Qt.ItemDataRole.UserRole)+1
HEADERS = ['Canción','Artista','Álbum','Formato','Duración','Tamaño','Archivo por USB']


def duration_label(value):
    if not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:return '—'
    seconds=max(1,round(value));return f'{seconds//60}:{seconds%60:02}'


def text_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value)).casefold() if not unicodedata.combining(c))


def byte_label(size):
    if not isinstance(size,int) or size < 0:return '—'
    if size < 1024:return f'{size} B'
    if size < 1024**2:return f'{size/1024:.1f} KB'
    if size < 1024**3:return f'{size/1024**2:.1f} MB'
    return f'{size/1024**3:.2f} GB'


class SortableItem(QTableWidgetItem):
    def __lt__(self, other):
        left,right = self.data(SORT_ROLE),other.data(SORT_ROLE)
        if isinstance(left,(int,float)) and isinstance(right,(int,float)):
            return left < right
        return text_key(self.text()) < text_key(other.text())


class LibraryModel(QAbstractTableModel):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.tracks=[];self.icons=OrderedDict();self.default_icon=None
        self.sort_column=0;self.sort_order=Qt.SortOrder.AscendingOrder
        self.rows={}

    def replace(self,tracks):
        self.beginResetModel();self.tracks=tracks;self.icons.clear();self.endResetModel()
        self.sort(self.sort_column,self.sort_order)

    def sort(self,column,order=Qt.SortOrder.AscendingOrder):
        if not 0 <= column < len(HEADERS):return
        self.sort_column,self.sort_order=column,order
        self.layoutAboutToBeChanged.emit()
        persistent=self.persistentIndexList()
        old=[(id(self.tracks[index.row()]),index.column()) for index in persistent]
        def value(track):
            if column in (0,1,2):return text_key(track.get(('title','artist','album')[column],''))
            if column == 3:return text_key(track.get('format_label') or '')
            if column == 4:
                value=track.get('duration')
                return value if isinstance(value,(int,float)) and value>0 else (float('inf') if order==Qt.SortOrder.AscendingOrder else float('-inf'))
            if column == 5:
                size=track.get('size')
                return size if type(size) is int else (float('inf') if order==Qt.SortOrder.AscendingOrder else float('-inf'))
            return text_key('Protegido' if str(track.get('afc_path','')).endswith('.m4p') else
                            'Disponible' if track.get('afc_path') else 'No accesible')
        self.tracks.sort(key=value,reverse=order==Qt.SortOrder.DescendingOrder)
        positions={id(track):row for row,track in enumerate(self.tracks)}
        self.rows={track.get('id'):row for row,track in enumerate(self.tracks)}
        self.changePersistentIndexList(persistent,[self.index(positions[token],col) for token,col in old])
        self.layoutChanged.emit()

    def set_icon(self,identifier,icon):
        self.icons[identifier]=icon;self.icons.move_to_end(identifier)
        while len(self.icons)>256:
            old,_=self.icons.popitem(last=False);self._changed(old,0,0)
        self._changed(identifier,0,0)

    def set_details(self,identifier,details):
        row=self.rows.get(identifier)
        if row is None:return
        self.tracks[row].update(details)
        self._changed(identifier,3,6)
        if self.sort_column in (3,4,5):self.sort(self.sort_column,self.sort_order)

    def _changed(self,identifier,first,last):
        row=self.rows.get(identifier)
        if row is not None:self.dataChanged.emit(self.index(row,first),self.index(row,last))

    def rowCount(self,parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.tracks)

    def columnCount(self,parent=None):
        return 0 if parent is not None and parent.isValid() else len(HEADERS)

    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal and 0<=section<len(HEADERS):return HEADERS[section]

    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.tracks):return None
        track=self.tracks[index.row()];column=index.column()
        if column==0 and role==Qt.ItemDataRole.DecorationRole:return self.icons.get(track.get('id'),self.default_icon)
        if role==Qt.ItemDataRole.ToolTipRole and column in (3,5):
            origin=track.get('format_source' if column==3 else 'size_source')
            return 'Comprobado por USB' if origin in ('header','usb') else 'Dato del catálogo; se comprobará al mostrar la fila' if origin else 'No hay información suficiente para determinarlo'
        if role!=Qt.ItemDataRole.DisplayRole:return None
        if column<3:return track[('title','artist','album')[column]]
        if column==3:return track.get('format_label') or '—'
        if column==4:return duration_label(track.get('duration'))
        if column==5:return byte_label(track.get('size'))
        path=track.get('afc_path')
        return 'Original protegido' if path and path.lower().endswith('.m4p') else 'Disponible' if path else 'Sin acceso USB'

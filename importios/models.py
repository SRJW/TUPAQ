"""Virtual song rows with stable selection while sorting by values, not labels."""
from collections import OrderedDict
from .i18n import tr, Text, render
import unicodedata
import math

from PySide6.QtCore import QAbstractTableModel,Qt,Signal
from PySide6.QtWidgets import QTableWidgetItem,QStyledItemDelegate,QStyleOptionViewItem,QStyle,QApplication
from PySide6.QtGui import QPainter,QPen,QPalette,QPainterPath

SORT_ROLE = int(Qt.ItemDataRole.UserRole)+1
LYRICS_ROLE = SORT_ROLE+1
HEADERS = ['Canción','Artista','Álbum','Formato','Duración','Tamaño']


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
    def __init__(self, value):
        self._message=value if isinstance(value,Text) else None
        super().__init__(str(value))

    def retranslate(self):
        if self._message is not None:self.setText(render(self._message.source))

    def __lt__(self, other):
        left,right = self.data(SORT_ROLE),other.data(SORT_ROLE)
        if isinstance(left,(int,float)) and isinstance(right,(int,float)):
            return left < right
        return text_key(self.text()) < text_key(other.text())


class SelectionDelegate(QStyledItemDelegate):
    """Keep native checkbox interaction with a legible indicator in both themes."""
    def paint(self,painter,option,index):
        option=QStyleOptionViewItem(option);self.initStyleOption(option,index)
        super().paint(painter,option,index)
        if index.column()==0 and index.data(LYRICS_ROLE):
            style=option.widget.style() if option.widget else QApplication.style()
            icon=style.subElementRect(QStyle.SubElement.SE_ItemViewItemDecoration,option,option.widget)
            from PySide6.QtCore import QRectF
            rect=QRectF(icon.right()-14,icon.bottom()-13,16,14)
            painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(option.palette.color(QPalette.ColorRole.Base),1));painter.setBrush(option.palette.color(QPalette.ColorRole.Text));painter.drawRoundedRect(rect,3,3)
            painter.setPen(QPen(option.palette.color(QPalette.ColorRole.Base),1))
            for y in (4,7,10):painter.drawLine(int(rect.x()+4),int(rect.y()+y),int(rect.x()+12),int(rect.y()+y))
            painter.restore()
        if not option.features & QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator:return
        style=option.widget.style() if option.widget else QApplication.style()
        rect=style.subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator,option,option.widget).adjusted(0,0,-1,-1)
        if not rect.isValid():return
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(option.palette.color(QPalette.ColorRole.Mid),1))
        painter.setBrush(option.palette.color(QPalette.ColorRole.Highlight if option.checkState!=Qt.CheckState.Unchecked else QPalette.ColorRole.Base))
        painter.drawRoundedRect(rect,3,3)
        painter.setPen(QPen(option.palette.color(QPalette.ColorRole.Text),1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        x,y,w,h=rect.x(),rect.y(),rect.width(),rect.height()
        if option.checkState==Qt.CheckState.Checked:
            path=QPainterPath();path.moveTo(x+w*.22,y+h*.52);path.lineTo(x+w*.43,y+h*.73);path.lineTo(x+w*.8,y+h*.28);painter.drawPath(path)
        elif option.checkState==Qt.CheckState.PartiallyChecked:painter.drawLine(x+3,y+h//2,x+w-3,y+h//2)
        painter.restore()


class LibraryModel(QAbstractTableModel):
    checkedChanged=Signal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.tracks=[];self.icons=OrderedDict();self.default_icon=None
        self.sort_column=0;self.sort_order=Qt.SortOrder.AscendingOrder
        self.rows={};self.checked=set();self.icon_keys={}

    @staticmethod
    def cover_key(track):
        return (track.get('afc_path'),tuple(track.get('artwork_paths') or []),track.get('album'),track.get('title'))

    def replace(self,tracks,preserve_icons=False):
        if not preserve_icons:self.icons.clear();self.icon_keys.clear()
        else:
            for track in tracks:
                identifier=track.get('id')
                if identifier in self.icons and self.icon_keys.get(identifier)!=self.cover_key(track):
                    self.icons.pop(identifier,None);self.icon_keys.pop(identifier,None)
        self.beginResetModel();self.tracks=tracks;self.endResetModel()
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

    def flags(self,index):
        flags=super().flags(index)
        return flags|Qt.ItemFlag.ItemIsUserCheckable if index.isValid() and index.column()==0 else flags

    def setData(self,index,value,role=Qt.ItemDataRole.EditRole):
        if role!=Qt.ItemDataRole.CheckStateRole or not index.isValid() or index.column()!=0:return False
        identifier=self.tracks[index.row()]['id']
        if value in (Qt.CheckState.Checked,Qt.CheckState.Checked.value):self.checked.add(identifier)
        else:self.checked.discard(identifier)
        self.dataChanged.emit(index,index,[Qt.ItemDataRole.CheckStateRole]);self.checkedChanged.emit();return True

    def check_visible(self,checked):
        ids={track['id'] for track in self.tracks}
        if checked:self.checked.update(ids)
        else:self.checked.difference_update(ids)
        if self.tracks:self.dataChanged.emit(self.index(0,0),self.index(len(self.tracks)-1,0),[Qt.ItemDataRole.CheckStateRole])
        self.checkedChanged.emit()

    def set_icon(self,identifier,icon):
        row=self.rows.get(identifier)
        if row is not None:self.icon_keys[identifier]=self.cover_key(self.tracks[row])
        self.icons[identifier]=icon;self.icons.move_to_end(identifier)
        while len(self.icons)>96:
            old,_=self.icons.popitem(last=False);self.icon_keys.pop(old,None);self._changed(old,0,0)
        self._changed(identifier,0,0)

    def set_details(self,identifier,details):
        row=self.rows.get(identifier)
        if row is None:return
        self.tracks[row].update(details)
        self._changed(identifier,0,5)
        if self.sort_column in (3,4,5):self.sort(self.sort_column,self.sort_order)

    def _changed(self,identifier,first,last):
        row=self.rows.get(identifier)
        if row is not None:self.dataChanged.emit(self.index(row,first),self.index(row,last))

    def rowCount(self,parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.tracks)

    def columnCount(self,parent=None):
        return 0 if parent is not None and parent.isValid() else len(HEADERS)

    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal and 0<=section<len(HEADERS):return str(tr(HEADERS[section]))

    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.tracks):return None
        track=self.tracks[index.row()];column=index.column()
        if column==0 and role==LYRICS_ROLE:
            from .lyrics import state
            return state(track)
        if column==0 and role==Qt.ItemDataRole.CheckStateRole:return Qt.CheckState.Checked if track['id'] in self.checked else Qt.CheckState.Unchecked
        if column==0 and role==Qt.ItemDataRole.DecorationRole:return self.icons.get(track.get('id'),self.default_icon)
        if role==Qt.ItemDataRole.ToolTipRole and column<3:
            from .lyrics import label
            return track['title']+'\n'+label(track) if column==0 else track[('title','artist','album')[column]]
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

"""Contextual empty states; no placeholder tracks or simulated USB activity."""
from PySide6.QtCore import Qt,QEvent
from PySide6.QtWidgets import QFrame,QVBoxLayout
from .i18n import QLabel,tr
from .motion import MotionButton


class LibraryEmptyState(QFrame):
    def __init__(self,view,window):
        super().__init__(view.viewport());self.owner=window;self.action=None
        self.setObjectName('emptyState');layout=QVBoxLayout(self);layout.setContentsMargins(24,22,24,22);layout.setSpacing(12)
        self.symbol=QLabel('♫');self.symbol.setObjectName('emptySymbol');self.symbol.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.symbol)
        self.title=QLabel();self.title.setObjectName('emptyTitle');self.title.setWordWrap(True);self.title.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.title)
        self.description=QLabel();self.description.setObjectName('muted');self.description.setWordWrap(True);self.description.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.description)
        self.button=MotionButton();self.button.clicked.connect(self.activate);layout.addWidget(self.button,0,Qt.AlignmentFlag.AlignHCenter)
        view.viewport().installEventFilter(self);self.hide()
    def activate(self):
        if self.action:self.action()
    def refresh(self):
        w=self.owner
        if w.library_model.rowCount():self.hide();return
        if w.format_filter.currentIndex() or w.content_filter.currentIndex():
            title,description,action='Sin coincidencias','Prueba otro título, artista, álbum o formato.','Limpiar filtros';callback=w.clear_filters
        elif w.search.text().strip():
            title,description,action='Sin coincidencias','Prueba otro título, artista, álbum o formato.','Limpiar búsqueda';callback=w.search.clear
        elif w.library_worker is not None or (w.after_artwork and w.after_artwork[0]=='library'):
            title,description,action='Leyendo tu biblioteca','Tus canciones aparecerán aquí cuando termine la lectura.',None;callback=None
        elif w.usb_connected or w.connection_token is not None:
            title,description,action='Sin canciones visibles','Añade música del ordenador o actualiza la biblioteca del iPhone.','Añadir canciones';callback=w.choose_files
        else:
            title,description,action='Tu música empieza aquí','Conecta tu iPhone por USB para ver su biblioteca. También puedes preparar canciones del ordenador.','Comprobar USB';callback=w.check_device
        self.title.setText(tr(title));self.description.setText(tr(description));self.action=callback
        self.button.setVisible(bool(action))
        if action:self.button.setText(tr(action))
        self.position();self.show();self.raise_()
    def position(self):
        area=self.parentWidget().rect();width=min(420,max(0,area.width()-32));height=min(270,max(0,area.height()-24))
        self.symbol.setVisible(height>=240);self.description.setVisible(height>=170)
        self.layout().setContentsMargins(*((16,12,16,12) if height<220 else (24,22,24,22)))
        self.setGeometry((area.width()-width)//2,(area.height()-height)//2,width,height)
    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.Resize:self.position()
        return False


class DropVeil(QFrame):
    def __init__(self,parent):
        super().__init__(parent);self.setObjectName('dropVeil')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout=QVBoxLayout(self);layout.setSpacing(14);layout.addStretch()
        title=QLabel(tr('Suelta tus canciones aquí'));title.setObjectName('emptyTitle');title.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(title)
        note=QLabel(tr('Se añadirán a la cola. Tú decides cuándo importarlas.'));note.setObjectName('muted');note.setAlignment(Qt.AlignmentFlag.AlignCenter);note.setWordWrap(True);layout.addWidget(note)
        layout.addStretch();self.hide()
    def reveal(self):self.setGeometry(self.parentWidget().rect().adjusted(14,14,-14,-14));self.show();self.raise_()

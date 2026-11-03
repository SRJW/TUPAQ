"""Organized native sidebar interface, with light/dark system-aware themes."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QPushButton,
    QButtonGroup,QStackedWidget,QComboBox,QCheckBox,QGridLayout,QHeaderView,
    QTableView,QTableWidget,QTabWidget,QAbstractItemView,QProgressBar,QListWidget,QApplication)

from .models import LibraryModel
from .visuals import music_icon,line_icon


def build(window):
    root = QWidget();root.setObjectName('shell');window.setCentralWidget(root)
    outer = QHBoxLayout(root);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
    sidebar = QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(218)
    side = QVBoxLayout(sidebar);side.setContentsMargins(20,28,20,20);side.setSpacing(8)
    brand_row = QHBoxLayout()
    mark = QLabel();mark.setPixmap(music_icon(40).pixmap(40,40))
    brand = QLabel('TUPAQ');brand.setObjectName('brand')
    brand_row.addWidget(mark);brand_row.addWidget(brand);brand_row.addStretch()
    side.addLayout(brand_row);side.addSpacing(32)
    window.navigation = QButtonGroup(window);window.nav_buttons=[]
    for number,(label,icon) in enumerate([('Inicio','home'),('Biblioteca','library'),('Importación USB','usb'),('Preferencias','settings')]):
        button=QPushButton(label);button.setObjectName('nav');button.setCheckable(True)
        button.setIconSize(QSize(22,22));button.setMinimumHeight(48)
        button.setProperty('iconKind',icon)
        window.navigation.addButton(button,number);window.nav_buttons.append(button);side.addWidget(button)
    side.addStretch()
    card=QFrame();card.setObjectName('deviceCard');card_layout=QVBoxLayout(card);card_layout.setContentsMargins(12,14,12,14)
    window.device_name=QLabel('iPhone');window.device_name.setObjectName('deviceName')
    window.device_name.setWordWrap(True);window.device_name.setTextFormat(Qt.TextFormat.PlainText)
    window.connection_badge=QLabel('○ Sin conexión USB');window.connection_badge.setObjectName('connectionBadge');window.connection_badge.setWordWrap(True)
    card_layout.addWidget(window.device_name);card_layout.addWidget(window.connection_badge)
    window.device_button=QPushButton('Comprobar USB');window.device_button.clicked.connect(window.check_device)
    card_layout.addWidget(window.device_button);side.addWidget(card)
    outer.addWidget(sidebar)
    window.pages=QStackedWidget();outer.addWidget(window.pages,1)
    workspace=QWidget();layout=QVBoxLayout(workspace);layout.setContentsMargins(26,24,26,20);layout.setSpacing(12)
    hero=QHBoxLayout();hero.setSpacing(16)
    hero_icon=QLabel();hero_icon.setPixmap(music_icon(64).pixmap(64,64));hero.addWidget(hero_icon)
    hero_text=QVBoxLayout();hero_text.setSpacing(5)
    window.heading=QLabel('Tu música, en un solo lugar.');window.heading.setObjectName('title');window.heading.setWordWrap(True)
    intro=QLabel('Elige o arrastra MP3, WAV, M4A (AAC/ALAC) y AIFF. Los originales se conservan.');intro.setWordWrap(True);intro.setObjectName('muted')
    hero_text.addWidget(window.heading);hero_text.addWidget(intro);hero.addLayout(hero_text,1);layout.addLayout(hero)
    notice=QLabel('Importación experimental por USB, con copia previa del catálogo y comprobación del resultado.\n'
                  'Exporta los originales al ordenador. Los archivos protegidos conservan su protección.')
    notice.setObjectName('notice');notice.setWordWrap(True);layout.addWidget(notice)
    connection=QHBoxLayout()
    window.device_status=QLabel('Conecta tu iPhone. Su biblioteca aparecerá automáticamente.');window.device_status.setWordWrap(True)
    window.device_status.setTextFormat(Qt.TextFormat.PlainText);connection.addWidget(window.device_status,1)
    window.library_button=QPushButton('Actualizar');window.library_button.setProperty('iconKind','refresh');window.library_button.clicked.connect(window.load_library)
    window.copy_diagnostic=QPushButton('Copiar diagnóstico');window.copy_diagnostic.setProperty('iconKind','copy')
    window.last_diagnostic='';window.copy_diagnostic.setEnabled(False)
    window.copy_diagnostic.clicked.connect(lambda:QApplication.clipboard().setText(window.last_diagnostic))
    connection.addWidget(window.library_button);connection.addWidget(window.copy_diagnostic);layout.addLayout(connection)
    window.local_tools=QWidget();buttons=QHBoxLayout(window.local_tools);buttons.setContentsMargins(0,0,0,0)
    window.choose=QPushButton('Elegir canciones');window.choose.setObjectName('primary');window.choose.setProperty('iconKind','plus');window.choose.clicked.connect(window.choose_files)
    window.remove=QPushButton('Quitar selección');window.remove.setProperty('iconKind','trash');window.remove.clicked.connect(window.remove_selection)
    window.clear=QPushButton('Vaciar lista');window.clear.setProperty('iconKind','close');window.clear.clicked.connect(window.clear_tracks)
    window.export=QPushButton('Guardar lista CSV');window.export.setProperty('iconKind','folder');window.export.clicked.connect(window.choose_export)
    for button in (window.choose,window.remove,window.clear):buttons.addWidget(button)
    buttons.addStretch();buttons.addWidget(window.export);layout.addWidget(window.local_tools)
    preview=QFrame();preview.setObjectName('preview');preview_layout=QHBoxLayout(preview);preview_layout.setContentsMargins(0,0,0,0)
    window.now_cover=QLabel('♪');window.now_cover.setFixedSize(64,64);window.now_cover.setAlignment(Qt.AlignmentFlag.AlignCenter);window.now_cover.setObjectName('cover')
    window.now_title=QLabel('La portada de la canción aparecerá aquí.');window.now_title.setWordWrap(True);window.now_title.setTextFormat(Qt.TextFormat.PlainText)
    preview_layout.addWidget(window.now_cover);preview_layout.addSpacing(8);preview_layout.addWidget(window.now_title,1);layout.addWidget(preview)
    actions=QHBoxLayout()
    window.import_phone=QPushButton('Importar al iPhone');window.import_phone.setObjectName('primary');window.import_phone.setProperty('iconKind','upload');window.import_phone.clicked.connect(window.import_songs)
    window.export_phone=QPushButton('Exportar selección');window.export_phone.setObjectName('primary');window.export_phone.setProperty('iconKind','download');window.export_phone.clicked.connect(window.export_songs)
    actions.addWidget(window.import_phone);actions.addWidget(window.export_phone);actions.addStretch();layout.addLayout(actions)
    window.table=QTableWidget(0,6);window.table.setHorizontalHeaderLabels(['Canción','Artista','Álbum','Formato','Duración','Tamaño'])
    window.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    window.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
    window.table.itemSelectionChanged.connect(window.update_buttons)
    window.library_model=LibraryModel(window);window.library_table=QTableView();window.library_table.setModel(window.library_model)
    window.library_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    window.library_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
    for section,width in [(1,175),(2,155),(3,75),(4,125)]:window.library_table.setColumnWidth(section,width)
    window.library_table.selectionModel().selectionChanged.connect(window.library_selection_changed)
    for table in (window.table,window.library_table):
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide();table.setShowGrid(False);table.setAlternatingRowColors(True)
        table.setIconSize(QSize(40,40));table.verticalHeader().setDefaultSectionSize(56)
    window.tabs=QTabWidget();window.tabs.addTab(window.table,'Ordenador');window.tabs.addTab(window.library_table,'iPhone');window.tabs.tabBar().hide()
    window.tabs.currentChanged.connect(window.view_changed)
    frame=QFrame();frame.setObjectName('tableCard');frame_layout=QVBoxLayout(frame);frame_layout.setContentsMargins(8,6,8,6);frame_layout.addWidget(window.tabs);layout.addWidget(frame,1)
    window.status=QLabel('Sin canciones. Puedes arrastrar archivos sobre esta ventana.');window.status.setWordWrap(True);window.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(window.status)
    window.progress=QProgressBar();window.progress.hide();layout.addWidget(window.progress)
    window.errors=QListWidget();window.errors.setMaximumHeight(68);window.errors.hide();layout.addWidget(window.errors)
    footer=QLabel('Procesamiento local y transferencia por USB · No se envían canciones a Internet');footer.setObjectName('muted');footer.setWordWrap(True);layout.addWidget(footer)
    window.pages.addWidget(workspace)
    settings=QWidget();settings_layout=QVBoxLayout(settings);settings_layout.setContentsMargins(30,30,30,30);settings_layout.setSpacing(20)
    settings_title=QLabel('Preferencias');settings_title.setObjectName('title');settings_layout.addWidget(settings_title)
    settings_card=QFrame();settings_card.setObjectName('tableCard');grid=QGridLayout(settings_card);grid.setContentsMargins(20,20,20,20);grid.setSpacing(18)
    grid.addWidget(QLabel('Apariencia'),0,0)
    window.theme_choice=QComboBox();window.theme_choice.addItems(['Sistema','Claro','Oscuro']);grid.addWidget(window.theme_choice,0,1)
    window.auto_read=QCheckBox('Detectar el iPhone y abrir su biblioteca automáticamente');window.auto_read.setChecked(True);grid.addWidget(window.auto_read,1,0,1,2)
    note=QLabel('Las miniaturas se cargan al ver las canciones. La detección automática no inicia importaciones.');note.setObjectName('muted');note.setWordWrap(True);grid.addWidget(note,2,0,1,2)
    settings_layout.addWidget(settings_card)
    maintenance=QFrame();maintenance.setObjectName('tableCard');maintenance_layout=QVBoxLayout(maintenance);maintenance_layout.setContentsMargins(20,20,20,20)
    maintenance_layout.addWidget(QLabel('Transferencias y copia del catálogo'))
    window.verify_import=QPushButton('Revisar importación pendiente');window.verify_import.setProperty('iconKind','refresh');window.verify_import.clicked.connect(lambda:window.start_transfer('verify',[],window.backup_root))
    window.open_backup=QPushButton('Ver respaldo del catálogo');window.open_backup.setProperty('iconKind','folder')
    window.open_backup.clicked.connect(window.open_backup_folder)
    maintenance_layout.addWidget(window.verify_import);maintenance_layout.addWidget(window.open_backup);settings_layout.addWidget(maintenance);settings_layout.addStretch()
    window.pages.addWidget(settings)
    window.navigation.idClicked.connect(window.navigate)
    window.nav_buttons[0].setChecked(True)
    window.setWindowIcon(music_icon())


def apply_theme(window):
    selection=window.theme_choice.currentIndex()
    dark=selection==2 or (selection==0 and QApplication.styleHints().colorScheme()==Qt.ColorScheme.Dark)
    colors = ({'bg':'#101116','side1':'#171621','side2':'#202134','card':'#191b24','text':'#f2f3fa','muted':'#a1a8bd',
               'border':'#333744','button':'#242631','hover':'#303449','selected':'#34385e','notice':'#20233a','row':'#1d202b','blue':'#5ba0ff'} if dark else
              {'bg':'#f7f8fd','side1':'#f3edfd','side2':'#eaf1fc','card':'#ffffff','text':'#172034','muted':'#697187',
               'border':'#e0e3ec','button':'#ffffff','hover':'#f0f3fd','selected':'#e0e3ff','notice':'#edf0ff','row':'#fafbfe','blue':'#006cff'})
    c=colors
    palette=QPalette()
    for role,key in [(QPalette.ColorRole.Window,'bg'),(QPalette.ColorRole.WindowText,'text'),(QPalette.ColorRole.Base,'card'),
                     (QPalette.ColorRole.Text,'text'),(QPalette.ColorRole.Button,'button'),(QPalette.ColorRole.ButtonText,'text'),
                     (QPalette.ColorRole.Highlight,'selected'),(QPalette.ColorRole.HighlightedText,'text')]:palette.setColor(role,QColor(c[key]))
    window.setPalette(palette)
    window.setStyleSheet(f'''
        QWidget {{color:{c['text']};font-size:14px;}}
        QWidget#shell,QStackedWidget {{background:{c['bg']};}}
        QFrame#sidebar {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {c['side1']},stop:1 {c['side2']});border-right:1px solid {c['border']};}}
        QLabel#brand {{font-size:23px;font-weight:700;}}
        QLabel#title {{font-size:27px;font-weight:700;}}
        QLabel#muted {{color:{c['muted']};font-size:12px;}}
        QLabel#notice {{background:{c['notice']};padding:14px;border-radius:12px;}}
        QFrame#deviceCard,QFrame#tableCard {{background:{c['card']};border:1px solid {c['border']};border-radius:14px;}}
        QLabel#deviceName {{font-weight:600;}}
        QLabel#connectionBadge {{color:{c['muted']};font-size:12px;}}
        QLabel#cover {{background:{c['selected']};color:{c['blue']};border-radius:12px;font-size:28px;}}
        QPushButton {{background:{c['button']};border:1px solid {c['border']};border-radius:10px;padding:9px 13px;font-weight:500;}}
        QPushButton:hover {{background:{c['hover']};}}
        QPushButton:focus {{border:1px solid {c['blue']};}}
        QPushButton#primary {{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2487ff,stop:1 #0059f5);border:1px solid #368bff;color:white;font-weight:600;}}
        QPushButton:disabled {{background:{c['bg']};color:{c['muted']};border-color:{c['border']};}}
        QPushButton#nav {{background:transparent;border:0;text-align:left;padding:12px;font-size:15px;}}
        QPushButton#nav:checked {{background:{c['selected']};color:{c['blue']};font-weight:600;}}
        QTableWidget,QTableView {{background:{c['card']};alternate-background-color:{c['row']};border:0;selection-background-color:{c['selected']};selection-color:{c['text']};outline:0;}}
        QTableWidget::item,QTableView::item {{padding:7px;border-bottom:1px solid {c['border']};}}
        QHeaderView::section {{background:{c['bg']};color:{c['muted']};padding:12px 8px;border:0;font-weight:500;}}
        QTabWidget::pane {{border:0;}}
        QComboBox {{background:{c['button']};border:1px solid {c['border']};padding:9px;border-radius:8px;}}
        QComboBox QAbstractItemView {{background:{c['card']};color:{c['text']};}}
        QProgressBar {{background:{c['border']};border:0;border-radius:5px;text-align:center;}}
        QProgressBar::chunk {{background:#007aff;border-radius:5px;}}
        QListWidget {{background:{c['notice']};color:{c['text']};border:1px solid {c['border']};border-radius:8px;}}
    ''')
    for button in window.findChildren(QPushButton):
        kind=button.property('iconKind')
        if kind:button.setIcon(line_icon(kind,'#ffffff' if button.objectName()=='primary' else c['muted']))
    for button in window.nav_buttons:
        button.setIcon(line_icon(button.property('iconKind'),c['blue'] if button.isChecked() else c['text']))
    window.default_music_icon=line_icon('music',c['blue'],40)
    window.library_model.default_icon=window.default_music_icon
    if window.library_model.rowCount():
        window.library_model.dataChanged.emit(window.library_model.index(0,0),window.library_model.index(window.library_model.rowCount()-1,0),[Qt.ItemDataRole.DecorationRole])
    window.theme_dark=dark

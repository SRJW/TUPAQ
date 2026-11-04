"""Compact native sidebar, collection list and inspector, inspired by Peel."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QPushButton,
    QButtonGroup,QStackedWidget,QComboBox,QCheckBox,QGridLayout,QHeaderView,
    QTableView,QTableWidget,QSplitter,QAbstractItemView,QProgressBar,QListWidget,QApplication,
    QLineEdit,QScrollArea,QFormLayout)
from .models import LibraryModel,SelectionDelegate
from .visuals import music_icon,line_icon
from .version import VERSION


def button(text,kind=None,handler=None):
    value=QPushButton(text)
    if kind:value.setProperty('iconKind',kind)
    if handler:value.clicked.connect(handler)
    value.setIconSize(QSize(17,17))
    return value


def build(window):
    root=QWidget();root.setObjectName('shell');window.setCentralWidget(root)
    outer=QHBoxLayout(root);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
    sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(208)
    side=QVBoxLayout(sidebar);side.setContentsMargins(14,18,14,16);side.setSpacing(6)
    brand_card=QFrame();brand_card.setObjectName('brandCard');brand_row=QHBoxLayout(brand_card);brand_row.setContentsMargins(10,10,10,10)
    mark=QLabel();mark.setPixmap(music_icon(34).pixmap(34,34));brand_row.addWidget(mark)
    brand_labels=QVBoxLayout();brand_labels.setSpacing(0)
    brand=QLabel('TUPAQ');brand.setObjectName('brand');brand_labels.addWidget(brand)
    version=QLabel(VERSION);version.setObjectName('muted');brand_labels.addWidget(version);brand_row.addLayout(brand_labels,1)
    side.addWidget(brand_card);side.addSpacing(14)
    section=QLabel('COLECCIÓN');section.setObjectName('section');side.addWidget(section)
    window.navigation=QButtonGroup(window);window.nav_buttons=[]
    for number,(label,kind) in enumerate([('Biblioteca','library'),('Preferencias','settings')]):
        value=button(label,kind);value.setObjectName('nav');value.setCheckable(True);value.setMinimumHeight(36)
        window.navigation.addButton(value,number);window.nav_buttons.append(value);side.addWidget(value)
    side.addStretch()
    card=QFrame();card.setObjectName('deviceCard');device_layout=QVBoxLayout(card);device_layout.setContentsMargins(10,12,10,12)
    window.device_name=QLabel('iPhone');window.device_name.setObjectName('deviceName');window.device_name.setWordWrap(True);window.device_name.setTextFormat(Qt.TextFormat.PlainText)
    window.connection_badge=QLabel('Sin conexión USB');window.connection_badge.setObjectName('muted');window.connection_badge.setWordWrap(True)
    window.device_button=button('Comprobar USB','phone',window.check_device)
    device_layout.addWidget(window.device_name);device_layout.addWidget(window.connection_badge);device_layout.addWidget(window.device_button);side.addWidget(card)
    privacy=QLabel('Música local · conexión por USB');privacy.setObjectName('muted');privacy.setWordWrap(True);side.addWidget(privacy)
    outer.addWidget(sidebar)
    window.pages=QStackedWidget();outer.addWidget(window.pages,1)
    workspace=QWidget();layout=QVBoxLayout(workspace);layout.setContentsMargins(16,14,16,12);layout.setSpacing(10)
    window.local_tools=QWidget();toolbar=QHBoxLayout(window.local_tools);toolbar.setContentsMargins(0,0,0,0);toolbar.setSpacing(7)
    window.heading=QLabel('Biblioteca');window.heading.setObjectName('title');toolbar.addWidget(window.heading);toolbar.addStretch()
    window.choose=button('Añadir canciones','plus',window.choose_files)
    window.import_phone=button('Importar','upload',window.import_songs);window.import_phone.setObjectName('primary')
    window.import_phone.setToolTip('Enviar la selección de la cola del ordenador; sin selección, enviar toda la cola.')
    window.export_phone=button('Exportar','download',window.export_songs)
    window.export_phone.setToolTip('Exportar al ordenador las canciones seleccionadas del iPhone.')
    window.delete_phone=button('Eliminar','trash',window.delete_songs)
    window.delete_phone.setToolTip('Eliminar de Música las canciones marcadas; pide confirmación.')
    window.library_button=button('','refresh',window.load_library);window.library_button.setToolTip('Volver a leer la biblioteca y comprobar sus archivos')
    window.copy_diagnostic=button('Diagnóstico','copy');window.last_diagnostic='';window.copy_diagnostic.setEnabled(False)
    window.copy_diagnostic.clicked.connect(lambda:QApplication.clipboard().setText(window.last_diagnostic))
    window.inspector_toggle=button('Detalles','library');window.inspector_toggle.setCheckable(True);window.inspector_toggle.setChecked(True)
    for value in (window.choose,window.import_phone,window.export_phone,window.delete_phone,window.inspector_toggle,window.library_button,window.copy_diagnostic):toolbar.addWidget(value)
    layout.addWidget(window.local_tools)
    window.device_status=QLabel('Conecta tu iPhone para mostrar su música.');window.device_status.setObjectName('muted')
    window.device_status.setWordWrap(True);window.device_status.setTextFormat(Qt.TextFormat.PlainText);window.device_status.setMaximumHeight(74);layout.addWidget(window.device_status)
    window.main_splitter=QSplitter(Qt.Orientation.Horizontal)
    center=QWidget();center_layout=QVBoxLayout(center);center_layout.setContentsMargins(0,0,0,0);center_layout.setSpacing(8)
    window.search=QLineEdit();window.search.setPlaceholderText('Buscar canción, artista, álbum o formato (.m4a, .mp3…)');window.search.setClearButtonEnabled(True);center_layout.addWidget(window.search)
    collection_header=QHBoxLayout();window.library_heading=QLabel('En el iPhone');window.library_heading.setObjectName('section')
    collection_header.addWidget(window.library_heading,1)
    window.selection_count=QLabel('');window.selection_count.setObjectName('muted');collection_header.addWidget(window.selection_count)
    window.select_visible=QCheckBox('Seleccionar visibles');window.select_visible.setTristate(True);collection_header.addWidget(window.select_visible)
    center_layout.addLayout(collection_header)
    splitter=QSplitter(Qt.Orientation.Vertical);splitter.splitterMoved.connect(window.schedule_artwork)
    window.library_panel=QFrame();phone_layout=QVBoxLayout(window.library_panel);phone_layout.setContentsMargins(0,0,0,0)
    window.library_model=LibraryModel(window);window.library_table=QTableView();window.library_table.setModel(window.library_model);window.library_table.setItemDelegateForColumn(0,SelectionDelegate(window.library_table))
    phone_layout.addWidget(window.library_table);splitter.addWidget(window.library_panel)
    window.queue_panel=QFrame();window.queue_panel.setObjectName('queuePanel');queue_layout=QVBoxLayout(window.queue_panel);queue_layout.setContentsMargins(0,8,0,0)
    queue_header=QHBoxLayout();queue_title=QLabel('PARA IMPORTAR');queue_title.setObjectName('section');queue_header.addWidget(queue_title,1)
    window.remove=button('Quitar','trash',window.remove_selection);window.clear=button('Vaciar','close',window.clear_tracks)
    window.export=button('CSV','folder',window.choose_export)
    for value in (window.remove,window.clear,window.export):queue_header.addWidget(value)
    queue_layout.addLayout(queue_header)
    window.table=QTableWidget(0,6);window.table.setHorizontalHeaderLabels(['Canción','Artista','Álbum','Formato','Duración','Tamaño']);queue_layout.addWidget(window.table)
    window.queue_panel.setMaximumHeight(250);splitter.addWidget(window.queue_panel);splitter.setStretchFactor(0,3);splitter.setStretchFactor(1,1)
    center_layout.addWidget(splitter,1);window.main_splitter.addWidget(center)
    window.inspector=QScrollArea();window.inspector.setObjectName('inspector');window.inspector.setWidgetResizable(True);window.inspector.setMinimumWidth(260);window.inspector.setMaximumWidth(330)
    inspector_body=QWidget();inspector_layout=QVBoxLayout(inspector_body);inspector_layout.setContentsMargins(20,20,16,16);inspector_layout.setSpacing(12)
    window.info_origin=QLabel('DETALLES');window.info_origin.setObjectName('section');inspector_layout.addWidget(window.info_origin)
    window.now_cover=QLabel('♪');window.now_cover.setFixedSize(96,96);window.now_cover.setObjectName('cover');window.now_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
    inspector_layout.addWidget(window.now_cover)
    window.now_title=QLabel('Selecciona una canción');window.now_title.setObjectName('inspectorTitle');window.now_title.setWordWrap(True);window.now_title.setTextFormat(Qt.TextFormat.PlainText);inspector_layout.addWidget(window.now_title)
    window.info_artist=QLabel('');window.info_artist.setObjectName('muted');window.info_artist.setWordWrap(True);window.info_artist.setTextFormat(Qt.TextFormat.PlainText);inspector_layout.addWidget(window.info_artist)
    form=QFormLayout();form.setVerticalSpacing(14);window.info_fields={}
    for key,label in [('album','Álbum'),('format','Formato'),('duration','Duración'),('size','Tamaño')]:
        name=QLabel(label);name.setObjectName('muted');value=QLabel('—');value.setWordWrap(True);value.setTextFormat(Qt.TextFormat.PlainText)
        form.addRow(name,value);window.info_fields[key]=value
    inspector_layout.addSpacing(8);inspector_layout.addLayout(form);inspector_layout.addStretch()
    note=QLabel('Los originales se conservan.\nNo se envían canciones a Internet.');note.setObjectName('muted');note.setWordWrap(True);inspector_layout.addWidget(note)
    window.inspector.setWidget(inspector_body);window.main_splitter.addWidget(window.inspector)
    window.main_splitter.setStretchFactor(0,1);window.main_splitter.setSizes([860,280]);window.main_splitter.splitterMoved.connect(window.schedule_artwork)
    window.inspector_toggle.toggled.connect(window.inspector.setVisible);layout.addWidget(window.main_splitter,1)
    window.status=QLabel('Sin canciones para importar.');window.status.setObjectName('muted');window.status.setWordWrap(True);window.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(window.status)
    window.progress=QProgressBar();window.progress.hide();layout.addWidget(window.progress)
    window.errors=QListWidget();window.errors.setMaximumHeight(68);window.errors.hide();layout.addWidget(window.errors)
    window.pages.addWidget(workspace)
    for table in (window.table,window.library_table):
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.verticalHeader().hide();table.setShowGrid(False);table.setAlternatingRowColors(False)
        table.setIconSize(QSize(30,30));table.verticalHeader().setDefaultSectionSize(44);table.setWordWrap(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionsClickable(True);table.setSortingEnabled(True)
    for section,width in [(1,116),(2,118),(3,100),(4,70),(5,78)]:window.library_table.setColumnWidth(section,width)
    for section,width in [(1,110),(2,110),(3,100),(4,70),(5,78)]:window.table.setColumnWidth(section,width)
    window.library_table.sortByColumn(0,Qt.SortOrder.AscendingOrder);window.table.sortItems(0,Qt.SortOrder.AscendingOrder)
    window.library_table.selectionModel().selectionChanged.connect(window.library_selection_changed)
    window.table.itemSelectionChanged.connect(window.local_selection_changed)
    window.library_table.horizontalHeader().sortIndicatorChanged.connect(window.schedule_artwork)
    window.search.textChanged.connect(window.filter_library)
    window.library_model.checkedChanged.connect(window.checks_changed)
    window.select_visible.clicked.connect(window.library_model.check_visible)
    settings=QWidget();settings_layout=QVBoxLayout(settings);settings_layout.setContentsMargins(30,30,30,30);settings_layout.setSpacing(20)
    settings_title=QLabel('Preferencias');settings_title.setObjectName('title');settings_layout.addWidget(settings_title)
    settings_card=QFrame();settings_card.setObjectName('tableCard');grid=QGridLayout(settings_card);grid.setContentsMargins(20,20,20,20);grid.setSpacing(18)
    grid.addWidget(QLabel('Apariencia'),0,0)
    window.theme_choice=QComboBox();window.theme_choice.addItems(['Sistema','Claro','Oscuro']);window.theme_choice.setCurrentIndex(2);grid.addWidget(window.theme_choice,0,1)
    window.auto_read=QCheckBox('Detectar el iPhone y abrir su biblioteca automáticamente');window.auto_read.setChecked(True);grid.addWidget(window.auto_read,1,0,1,2)
    note=QLabel('Las miniaturas se cargan al ver las canciones. La detección automática no inicia importaciones.');note.setObjectName('muted');note.setWordWrap(True);grid.addWidget(note,2,0,1,2)
    window.font_status=QLabel(getattr(QApplication.instance(),'typography_status','Fuente del sistema'));window.font_status.setTextFormat(Qt.TextFormat.PlainText);window.font_status.setObjectName('muted');window.font_status.setWordWrap(True);grid.addWidget(window.font_status,3,0,1,2)
    window.choose_font_button=button('Cargar fuente autorizada…','folder',window.choose_font);grid.addWidget(window.choose_font_button,4,0)
    window.reset_font_button=button('Usar fuente nativa','refresh',window.reset_font);grid.addWidget(window.reset_font_button,4,1)
    settings_layout.addWidget(settings_card)
    maintenance=QFrame();maintenance.setObjectName('tableCard');maintenance_layout=QVBoxLayout(maintenance);maintenance_layout.setContentsMargins(20,20,20,20)
    window.advanced=QCheckBox('Mostrar opciones avanzadas de recuperación');settings_layout.addWidget(window.advanced)
    window.advanced.toggled.connect(maintenance.setVisible);maintenance.hide()
    maintenance_layout.addWidget(QLabel('Recuperación y registros de transferencias'))
    explanation=QLabel('No necesitas estas herramientas para importar normalmente. Sirven para comprobar o recuperar un envío interrumpido. La copia del catálogo guarda el estado de la biblioteca; no incluye todos los audios ni es una restauración automática.')
    explanation.setWordWrap(True);explanation.setObjectName('muted');maintenance_layout.addWidget(explanation)
    window.verify_import=QPushButton('Revisar operación pendiente');window.verify_import.setProperty('iconKind','refresh');window.verify_import.clicked.connect(lambda:window.start_transfer('verify',[],window.backup_root))
    window.open_backup=QPushButton('Ver respaldo del catálogo');window.open_backup.setProperty('iconKind','folder')
    window.open_backup.clicked.connect(window.open_backup_folder)
    window.verify_import.setToolTip('Comprueba el resultado de un envío o una eliminación sin reenviar canciones.')
    window.open_backup.setToolTip('Abre los registros y copias locales del catálogo. No incluye una copia completa de tus audios.')
    maintenance_layout.addWidget(window.verify_import);maintenance_layout.addWidget(window.open_backup);settings_layout.addWidget(maintenance);settings_layout.addStretch()
    window.resume_import=QPushButton('Completar importación pendiente');window.resume_import.setProperty('iconKind','upload')
    window.resume_import.clicked.connect(lambda:window.start_transfer('resume',list(window.tracks.values()),window.backup_root))
    window.resume_import.setToolTip('Intenta terminar la entrega de audio que falta usando el archivo original y el registro guardado.')
    maintenance_layout.addWidget(window.resume_import)
    window.repair_metadata=QPushButton('Actualizar portadas y fecha');window.repair_metadata.setProperty('iconKind','refresh')
    window.repair_metadata.clicked.connect(lambda:window.start_transfer('repair',list(window.tracks.values()),window.backup_root))
    window.repair_metadata.setToolTip('Reenvía portada y fecha de canciones previamente importadas por TUPAQ en este ordenador.')
    maintenance_layout.addWidget(window.repair_metadata)
    ownership_note=QLabel('Actualizar portadas y fecha se aplica solo a importaciones registradas por TUPAQ en este ordenador.')
    ownership_note.setWordWrap(True);ownership_note.setObjectName('muted');maintenance_layout.addWidget(ownership_note)
    recovery_note=QLabel('Completar usa el archivo original y el registro guardado de la operación. Función experimental: conserva los respaldos.')
    recovery_note.setWordWrap(True);recovery_note.setObjectName('muted');maintenance_layout.addWidget(recovery_note)
    settings_scroll=QScrollArea();settings_scroll.setWidgetResizable(True);settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
    settings_scroll.setWidget(settings);window.pages.addWidget(settings_scroll)
    window.navigation.idClicked.connect(window.navigate)
    window.nav_buttons[0].setChecked(True)
    window.setWindowIcon(music_icon())


def apply_theme(window):
    selection=window.theme_choice.currentIndex()
    dark=selection==2 or selection==0 and QApplication.styleHints().colorScheme()==Qt.ColorScheme.Dark
    c=({'bg':'#1e1e1e','side':'#1b1b1b','card':'#252525','text':'#ededed','muted':'#969696','border':'#363636',
        'button':'#333333','hover':'#414141','selected':'#464646','blue':'#58a6ff'} if dark else
       {'bg':'#fafafa','side':'#f0f0ef','card':'#ffffff','text':'#252525','muted':'#777777','border':'#dededc',
        'button':'#ebebea','hover':'#dfdfdd','selected':'#d8d8d5','blue':'#007aff'})
    palette=QPalette()
    for role,key in [(QPalette.ColorRole.Window,'bg'),(QPalette.ColorRole.WindowText,'text'),(QPalette.ColorRole.Base,'bg'),
                     (QPalette.ColorRole.Text,'text'),(QPalette.ColorRole.Button,'button'),(QPalette.ColorRole.ButtonText,'text'),
                     (QPalette.ColorRole.Mid,'muted'),(QPalette.ColorRole.Dark,'muted'),
                     (QPalette.ColorRole.Shadow,'border'),(QPalette.ColorRole.Light,'hover'),
                     (QPalette.ColorRole.Highlight,'selected'),(QPalette.ColorRole.HighlightedText,'text')]:palette.setColor(role,QColor(c[key]))
    window.setPalette(palette)
    window.setStyleSheet(f'''
        QWidget {{color:{c['text']};font-size:13px;}}
        QWidget#shell,QStackedWidget {{background:{c['bg']};}}
        QFrame#sidebar {{background:{c['side']};border-right:1px solid {c['border']};}}
        QFrame#brandCard {{border:1px solid {c['border']};border-radius:20px;background:transparent;}}
        QLabel#brand {{font-size:16px;font-weight:600;}}
        QLabel#title {{font-size:18px;font-weight:600;}}
        QLabel#inspectorTitle {{font-size:21px;font-weight:600;}}
        QLabel#section {{font-size:12px;font-weight:600;color:{c['muted']};}}
        QLabel#muted {{font-size:12px;color:{c['muted']};}}
        QFrame#deviceCard {{border:1px solid {c['border']};border-radius:12px;background:{c['side']};}}
        QLabel#deviceName {{font-weight:600;}}
        QLabel#cover {{background:{c['card']};color:{c['muted']};border:1px solid {c['border']};border-radius:14px;font-size:40px;}}
        QPushButton {{background:{c['button']};border:1px solid transparent;border-radius:13px;padding:6px 11px;font-weight:500;}}
        QPushButton:hover {{background:{c['hover']};}}
        QPushButton:focus {{border:1px solid {c['muted']};}}
        QPushButton#primary {{background:{c['selected']};font-weight:600;}}
        QPushButton:disabled,QPushButton#primary:disabled {{background:{c['bg']};color:{c['muted']};border:1px solid {c['border']};}}
        QPushButton#nav {{background:transparent;border:0;text-align:left;border-radius:8px;padding:8px 10px;}}
        QPushButton#nav:checked {{background:{c['selected']};font-weight:600;}}
        QTableWidget,QTableView {{background:{c['bg']};border:0;selection-background-color:{c['selected']};selection-color:{c['text']};outline:0;}}
        QTableWidget::item,QTableView::item {{padding:5px;border-bottom:1px solid {c['border']};}}
        QHeaderView::section {{background:{c['bg']};color:{c['muted']};padding:8px 5px;border:0;border-bottom:1px solid {c['border']};font-size:12px;font-weight:500;}}
        QLineEdit {{background:{c['side']};border:1px solid {c['border']};border-radius:13px;padding:6px 12px;}}
        QComboBox {{background:{c['button']};border:1px solid {c['border']};padding:5px 9px;border-radius:11px;}}
        QComboBox QAbstractItemView {{background:{c['card']};color:{c['text']};}}
        QFrame#tableCard {{background:{c['card']};border:1px solid {c['border']};border-radius:12px;}}
        QFrame#queuePanel {{border-top:1px solid {c['border']};}}
        QScrollArea#inspector {{background:{c['bg']};border:0;border-left:1px solid {c['border']};}}
        QScrollArea#inspector > QWidget > QWidget {{background:{c['bg']};}}
        QProgressBar {{background:{c['border']};border:0;border-radius:3px;text-align:center;}}
        QProgressBar::chunk {{background:{c['blue']};border-radius:3px;}}
        QListWidget {{background:{c['card']};border:1px solid {c['border']};border-radius:8px;}}
        QSplitter::handle {{background:{c['border']};width:1px;height:1px;}}
    ''')
    for value in window.findChildren(QPushButton):
        kind=value.property('iconKind')
        if kind:value.setIcon(line_icon(kind,c['muted'],18))
    window.default_music_icon=line_icon('music',c['muted'],36);window.library_model.default_icon=window.default_music_icon
    if window.library_model.rowCount():window.library_model.dataChanged.emit(window.library_model.index(0,0),window.library_model.index(window.library_model.rowCount()-1,0),[Qt.ItemDataRole.DecorationRole])
    window.theme_dark=dark

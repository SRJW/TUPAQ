"""Compact native sidebar, collection list and inspector, inspired by Apple Music."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QPushButton,
    QButtonGroup,QStackedWidget,QComboBox,QFontComboBox,QCheckBox,QGridLayout,QHeaderView,
    QTableView,QTableWidget,QSplitter,QAbstractItemView,QProgressBar,QListWidget,QApplication,
    QLineEdit,QScrollArea,QFormLayout,QGraphicsDropShadowEffect)
from .models import LibraryModel,SelectionDelegate
from .visuals import app_icon,line_icon
from .version import VERSION
from .surfaces import Atmosphere
from .i18n import tr, QLabel, QPushButton, QCheckBox, QComboBox, QLineEdit, QTableWidget, QListWidget


def button(text,kind=None,handler=None):
    value=QPushButton(tr(text))
    if kind:value.setProperty('iconKind',kind)
    if handler:value.clicked.connect(handler)
    value.setIconSize(QSize(17,17))
    return value


def build(window):
    root=Atmosphere();window.scene=root;window.setCentralWidget(root)
    shell_layout=QVBoxLayout(root);window.shell_layout=shell_layout;shell_layout.setContentsMargins(14,14,14,14);shell_layout.setSpacing(12)
    outer=QHBoxLayout();window.top_layout=outer;outer.setContentsMargins(0,0,0,0);outer.setSpacing(14);shell_layout.addLayout(outer,1)
    sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(224)
    side=QVBoxLayout(sidebar);side.setContentsMargins(14,18,14,16);side.setSpacing(6)
    brand_card=QFrame();brand_card.setObjectName('brandCard');brand_row=QHBoxLayout(brand_card);brand_row.setContentsMargins(10,10,10,10)
    mark=QLabel();mark.setPixmap(app_icon().pixmap(40,40));brand_row.addWidget(mark)
    brand_labels=QVBoxLayout();brand_labels.setSpacing(0)
    brand=QLabel('TUPAQ');brand.setObjectName('brand');brand_labels.addWidget(brand)
    version=QLabel(VERSION);version.setObjectName('muted');brand_labels.addWidget(version);brand_row.addLayout(brand_labels,1)
    side.addWidget(brand_card);side.addSpacing(14)
    section=QLabel(tr('COLECCIÓN'));section.setObjectName('section');side.addWidget(section)
    window.navigation=QButtonGroup(window);window.nav_buttons=[]
    for number,(label,kind) in enumerate([('Biblioteca','library'),('Preferencias','settings')]):
        value=button(label,kind);value.setObjectName('nav');value.setCheckable(True);value.setMinimumHeight(36)
        window.navigation.addButton(value,number);window.nav_buttons.append(value);side.addWidget(value)
    side.addStretch(1)
    card=QFrame();card.setObjectName('deviceCard');device_layout=QVBoxLayout(card);device_layout.setContentsMargins(10,12,10,12)
    window.device_name=QLabel(tr('iPhone'));window.device_name.setObjectName('deviceName');window.device_name.setWordWrap(True);window.device_name.setTextFormat(Qt.TextFormat.PlainText)
    window.connection_badge=QLabel(tr('Sin conexión USB'));window.connection_badge.setObjectName('muted');window.connection_badge.setWordWrap(True)
    window.device_button=button('Comprobar USB','phone',window.check_device)
    device_layout.addWidget(window.device_name);device_layout.addWidget(window.connection_badge);device_layout.addWidget(window.device_button);side.addWidget(card);side.removeWidget(card);side.insertWidget(2,card)
    privacy=QLabel(tr('Música local · conexión por USB'));privacy.setObjectName('muted');privacy.setWordWrap(True);side.addWidget(privacy)
    outer.addWidget(sidebar)
    window.pages=QStackedWidget();outer.addWidget(window.pages,1)
    workspace=QWidget();workspace.setObjectName('workspace');layout=QVBoxLayout(workspace);layout.setContentsMargins(16,16,16,12);layout.setSpacing(10)
    window.local_tools=QWidget();toolbar=QHBoxLayout(window.local_tools);toolbar.setContentsMargins(0,0,0,0);toolbar.setSpacing(7)
    window.heading=QLabel(tr('Biblioteca'));window.heading.setObjectName('title');toolbar.addWidget(window.heading);toolbar.addStretch()
    window.choose=button('Añadir canciones','plus',window.choose_files)
    window.import_phone=button('Importar','upload',window.import_songs);window.import_phone.setObjectName('primary')
    window.import_phone.setToolTip(tr('Enviar la selección de la cola del ordenador; sin selección, enviar toda la cola.'))
    window.export_phone=button('Exportar','download',window.export_songs)
    window.export_phone.setToolTip(tr('Exportar al ordenador las canciones seleccionadas del iPhone.'))
    window.delete_phone=button('Eliminar','trash',window.delete_songs)
    window.delete_phone.setToolTip(tr('Eliminar de Música las canciones marcadas; pide confirmación.'))
    window.queue_toggle=button('Cola','library');window.queue_toggle.setCheckable(True);window.queue_toggle.setChecked(True)
    window.library_button=button('','refresh',window.load_library);window.library_button.setToolTip(tr('Volver a leer la biblioteca y comprobar sus archivos'))
    window.copy_diagnostic=button('Diagnóstico','copy');window.last_diagnostic='';window.copy_diagnostic.setEnabled(False)
    window.copy_diagnostic.clicked.connect(lambda:QApplication.clipboard().setText(window.last_diagnostic))
    window.inspector_toggle=button('Detalles','library');window.inspector_toggle.setCheckable(True);window.inspector_toggle.setChecked(True)
    for value in (window.inspector_toggle,window.queue_toggle,window.library_button,window.copy_diagnostic):toolbar.addWidget(value)
    layout.addWidget(window.local_tools)
    window.device_status=QLabel(tr('Conecta tu iPhone para mostrar su música.'));window.device_status.setObjectName('muted')
    window.device_status.setWordWrap(True);window.device_status.setTextFormat(Qt.TextFormat.PlainText);window.device_status.setMaximumHeight(74);layout.addWidget(window.device_status)
    window.main_splitter=QSplitter(Qt.Orientation.Horizontal)
    center=QWidget();center.setMinimumWidth(360);center_layout=QVBoxLayout(center);center_layout.setContentsMargins(0,0,0,0);center_layout.setSpacing(8)
    window.search=QLineEdit();window.search.setPlaceholderText(tr('Buscar canción, artista, álbum o formato (.m4a, .mp3…)'));window.search.setClearButtonEnabled(True);center_layout.addWidget(window.search)
    collection_header=QHBoxLayout();window.library_heading=QLabel(tr('En el iPhone'));window.library_heading.setObjectName('section')
    collection_header.addWidget(window.library_heading,1)
    window.selection_count=QLabel('');window.selection_count.setObjectName('muted');collection_header.addWidget(window.selection_count)
    window.select_visible=QCheckBox(tr('Seleccionar visibles'));window.select_visible.setTristate(True);collection_header.addWidget(window.select_visible)
    center_layout.addLayout(collection_header)
    splitter=QSplitter(Qt.Orientation.Vertical);splitter.splitterMoved.connect(window.schedule_artwork)
    window.library_panel=QFrame();phone_layout=QVBoxLayout(window.library_panel);phone_layout.setContentsMargins(0,0,0,0)
    window.library_model=LibraryModel(window);window.library_table=QTableView();window.library_table.setModel(window.library_model);window.library_table.setItemDelegateForColumn(0,SelectionDelegate(window.library_table))
    phone_layout.addWidget(window.library_table);splitter.addWidget(window.library_panel)
    window.queue_panel=QFrame();window.queue_panel.setObjectName('queuePanel');queue_layout=QVBoxLayout(window.queue_panel);queue_layout.setContentsMargins(0,8,0,0)
    queue_header=QHBoxLayout();queue_title=QLabel(tr('PARA IMPORTAR'));queue_title.setObjectName('section');queue_header.addWidget(queue_title,1)
    window.remove=button('Quitar','trash',window.remove_selection);window.clear=button('Vaciar','close',window.clear_tracks)
    window.export=button('CSV','folder',window.choose_export)
    for value in (window.remove,window.clear,window.export):queue_header.addWidget(value)
    queue_layout.addLayout(queue_header)
    window.table=QTableWidget(0,6);window.table.setHorizontalHeaderLabels(['Canción','Artista','Álbum','Formato','Duración','Tamaño']);queue_layout.addWidget(window.table);window.table.setItemDelegateForColumn(0,SelectionDelegate(window.table))
    window.queue_panel.setMaximumHeight(250);splitter.addWidget(window.queue_panel);splitter.setStretchFactor(0,3);splitter.setStretchFactor(1,1)
    center_layout.addWidget(splitter,1);window.main_splitter.addWidget(center)
    window.inspector=QFrame();window.inspector.setObjectName('hero')
    hero_layout=QVBoxLayout(window.inspector);hero_layout.setContentsMargins(16,18,16,18);hero_layout.setSpacing(12)
    window.info_origin=QLabel(tr('TU COLECCIÓN'));window.info_origin.setObjectName('section');hero_layout.addWidget(window.info_origin)
    window.now_title=QLabel(tr('Tu música, siempre contigo.'));window.now_title.setObjectName('inspectorTitle');window.now_title.setWordWrap(True);window.now_title.setTextFormat(Qt.TextFormat.PlainText);hero_layout.addWidget(window.now_title)
    window.info_artist=QLabel(tr('Selecciona una canción para ver sus detalles.'));window.info_artist.setObjectName('muted');window.info_artist.setWordWrap(True);window.info_artist.setTextFormat(Qt.TextFormat.PlainText);hero_layout.addWidget(window.info_artist)
    window.now_cover=QLabel('♪');window.now_cover.setFixedSize(224,224);window.now_cover.setObjectName('cover');window.now_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hero_layout.addWidget(window.now_cover,0,Qt.AlignmentFlag.AlignHCenter)
    window.cover_metadata=QLabel('—');window.cover_metadata.setObjectName('muted');window.cover_metadata.setWordWrap(True);window.cover_metadata.setTextFormat(Qt.TextFormat.PlainText);hero_layout.addWidget(window.cover_metadata)
    window.view_cover=button('Ver carátula original',handler=window.open_cover);window.view_cover.setEnabled(False);hero_layout.addWidget(window.view_cover)
    window.lyrics_status=QLabel(tr('No se ha detectado letra'));window.lyrics_status.setWordWrap(True);window.lyrics_status.setTextFormat(Qt.TextFormat.PlainText);hero_layout.addWidget(window.lyrics_status)
    window.view_lyrics=button('Ver letra incluida',handler=window.open_lyrics);window.view_lyrics.setEnabled(False);hero_layout.addWidget(window.view_lyrics)
    properties_title=QLabel(tr('PROPIEDADES DE AUDIO'));properties_title.setObjectName('section');hero_layout.addSpacing(10);hero_layout.addWidget(properties_title)
    properties=QFrame();properties.setObjectName('propertiesCard');details=QGridLayout(properties);details.setContentsMargins(12,12,12,12);details.setHorizontalSpacing(12);details.setVerticalSpacing(12)
    window.info_fields={}
    for row,(key,label) in enumerate((('album','Álbum'),('format','Formato'),('duration','Duración'),('size','Tamaño'),('quality','Calidad'),('bitrate','Tasa de bits'),('genre','Género'),('year','Año'))):
        caption=QLabel(tr(label));caption.setObjectName('muted');details.addWidget(caption,row,0,Qt.AlignmentFlag.AlignTop)
        value=QLabel('—');value.setTextFormat(Qt.TextFormat.PlainText);value.setObjectName('metadata');value.setWordWrap(True);value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTop);value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.addWidget(value,row,1);window.info_fields[key]=value
    details.setColumnStretch(1,1);hero_layout.addWidget(properties)
    description=QLabel(tr('Lleva tus canciones a Música y conserva tus originales en el ordenador.'));description.setObjectName('heroDescription');description.setWordWrap(True);hero_layout.addWidget(description);hero_layout.addStretch()
    window.inspector_scroll=QScrollArea();window.inspector_scroll.setObjectName('inspector');window.inspector_scroll.setWidgetResizable(True);window.inspector_scroll.setFrameShape(QFrame.Shape.NoFrame);window.inspector_scroll.setMinimumWidth(258);window.inspector_scroll.setMaximumWidth(360);window.inspector_scroll.setWidget(window.inspector)
    window.main_splitter.addWidget(window.inspector_scroll);window.main_splitter.setStretchFactor(0,1);window.main_splitter.setStretchFactor(1,0);window.main_splitter.setSizes([800,280]);window.main_splitter.setChildrenCollapsible(False)
    window.transfer_actions=QGridLayout();window.transfer_actions.setContentsMargins(0,0,0,0);window.transfer_actions.setSpacing(8)
    center_layout.insertLayout(0,window.transfer_actions);layout_transfer_actions(window)
    window.inspector_toggle.toggled.connect(window.inspector_scroll.setVisible);layout.addWidget(window.main_splitter,1)
    activity=QFrame();activity.setObjectName('activityBar');activity_layout=QHBoxLayout(activity);activity_layout.setContentsMargins(16,12,16,12);activity_layout.setSpacing(12)
    activity_icon=QLabel();activity_icon.setPixmap(app_icon().pixmap(25,25));activity_layout.addWidget(activity_icon)
    window.status=QLabel(tr('Sin canciones para importar.'));window.status.setObjectName('muted');window.status.setWordWrap(True);window.status.setTextFormat(Qt.TextFormat.PlainText);activity_layout.addWidget(window.status,1)
    window.progress=QProgressBar();window.progress.setFixedWidth(180);window.progress.setFixedHeight(12);window.progress.setTextVisible(False);window.progress.hide();activity_layout.addWidget(window.progress)
    window.cancel_transfer_button=button('Cancelar','close',window.cancel_transfer);window.cancel_transfer_button.hide()
    window.cancel_transfer_button.setToolTip(tr('Detiene la preparación o exportación. Si ya se enviaron cambios a Música, termina el lote para no dejarlo incompleto.'))
    activity_layout.addWidget(window.cancel_transfer_button)
    privacy=QLabel(tr('Local · USB'));privacy.setObjectName('muted');activity_layout.addWidget(privacy)
    shell_layout.addWidget(activity)
    window.errors=QListWidget();window.errors.setMaximumHeight(68);window.errors.hide();layout.addWidget(window.errors)
    window.pages.addWidget(workspace)
    for table in (window.table,window.library_table):
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.verticalHeader().hide();table.setShowGrid(False);table.setAlternatingRowColors(False)
        table.setIconSize(QSize(30,30));table.verticalHeader().setDefaultSectionSize(48);table.setWordWrap(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionsClickable(True);table.setSortingEnabled(True)
    for section,width in [(1,130),(2,120),(3,95),(4,64),(5,76)]:window.library_table.setColumnWidth(section,width)
    for section,width in [(1,130),(2,120),(3,95),(4,64),(5,76)]:window.table.setColumnWidth(section,width)
    window.library_table.sortByColumn(0,Qt.SortOrder.AscendingOrder);window.table.sortItems(0,Qt.SortOrder.AscendingOrder)
    window.library_table.selectionModel().selectionChanged.connect(window.library_selection_changed)
    window.table.itemSelectionChanged.connect(window.local_selection_changed)
    window.library_table.horizontalHeader().sortIndicatorChanged.connect(window.schedule_artwork)
    window.search.textChanged.connect(window.filter_library)
    window.library_model.checkedChanged.connect(window.checks_changed)
    window.select_visible.clicked.connect(window.library_model.check_visible)
    settings=QWidget();settings.setObjectName('settingsPage');settings_layout=QVBoxLayout(settings);settings_layout.setContentsMargins(30,30,30,30);settings_layout.setSpacing(20)
    settings_title=QLabel(tr('Preferencias'));settings_title.setObjectName('title');settings_layout.addWidget(settings_title)
    settings_card=QFrame();settings_card.setObjectName('tableCard');grid=QGridLayout(settings_card);grid.setContentsMargins(20,20,20,20);grid.setSpacing(18)
    grid.addWidget(QLabel(tr('Apariencia')),0,0)
    window.theme_choice=QComboBox();window.theme_choice.addItems(['Sistema','Claro','Oscuro']);window.theme_choice.setCurrentIndex(2);grid.addWidget(window.theme_choice,0,1)
    window.mood_choice=QComboBox();window.mood_choice.addItems(['Nocturno','Aurora','Atardecer','Estudio']);window.mood_choice.setCurrentIndex(3)
    grid.addWidget(QLabel(tr('Estilo visual')),8,0);grid.addWidget(window.mood_choice,8,1)
    window.mood_choice.currentIndexChanged.connect(window.change_mood)
    window.language_choice=QComboBox()
    from .i18n import LANGUAGES
    for code,label in LANGUAGES: window.language_choice.addItem(label,code)
    grid.addWidget(QLabel(tr('Idioma')),9,0);grid.addWidget(window.language_choice,9,1)
    language_note=QLabel(tr('El idioma se aplica al instante y se conserva al volver a abrir TUPAQ.'))
    language_note.setWordWrap(True);language_note.setObjectName('muted');grid.addWidget(language_note,10,0,1,2)
    window.auto_read=QCheckBox(tr('Detectar el iPhone y abrir su biblioteca automáticamente'));window.auto_read.setChecked(True);grid.addWidget(window.auto_read,1,0,1,2)
    note=QLabel(tr('Las miniaturas se cargan al ver las canciones. La detección automática no inicia importaciones.'));note.setObjectName('muted');note.setWordWrap(True);grid.addWidget(note,2,0,1,2)
    window.font_status=QLabel(tr(getattr(QApplication.instance(),'typography_status','Fuente del sistema')));window.font_status.setTextFormat(Qt.TextFormat.PlainText);window.font_status.setObjectName('muted');window.font_status.setWordWrap(True);grid.addWidget(window.font_status,3,0,1,2)
    import sys
    if sys.platform!='darwin':
        window.font_choice=QFontComboBox();window.font_choice.setCurrentFont(QApplication.instance().font());grid.addWidget(QLabel(tr('Fuente de la interfaz')),4,0);grid.addWidget(window.font_choice,4,1)
        window.font_choice.currentFontChanged.connect(window.stage_font)
        window.font_preview=QLabel(tr('Tu música, en un solo lugar. · Aa Bb 123'));window.font_preview.setTextFormat(Qt.TextFormat.PlainText);window.font_preview.setWordWrap(True);window.font_preview.setObjectName('fontPreview');grid.addWidget(window.font_preview,5,0,1,2)
        window.font_pending=QLabel(tr('Elige una fuente y pulsa Aplicar.'));window.font_pending.setObjectName('muted');window.font_pending.setWordWrap(True);grid.addWidget(window.font_pending,6,0,1,2)
        actions=QHBoxLayout()
        window.choose_font_button=button('Abrir archivo de fuente…','folder',window.choose_font)
        window.reset_font_button=button('Fuente del sistema','refresh',window.reset_font)
        window.apply_font_button=button('Aplicar',None,window.apply_font);window.apply_font_button.setObjectName('primary');window.apply_font_button.setEnabled(False)
        for item in (window.choose_font_button,window.reset_font_button,window.apply_font_button):actions.addWidget(item)
        grid.addLayout(actions,7,0,1,2)
    else:
        native_note=QLabel(tr('TUPAQ utiliza siempre la fuente del sistema de macOS.'));native_note.setObjectName('muted');native_note.setWordWrap(True);grid.addWidget(native_note,4,0,1,2)
    settings_layout.addWidget(settings_card)
    maintenance=QFrame();maintenance.setObjectName('tableCard');maintenance_layout=QVBoxLayout(maintenance);maintenance_layout.setContentsMargins(20,20,20,20)
    window.advanced=QCheckBox(tr('Mostrar opciones avanzadas de recuperación'));settings_layout.addWidget(window.advanced)
    window.advanced.toggled.connect(maintenance.setVisible);maintenance.hide()
    maintenance_layout.addWidget(QLabel(tr('Recuperación y registros de transferencias')))
    explanation=QLabel(tr('No necesitas estas herramientas para importar normalmente. Sirven para comprobar o recuperar un envío interrumpido. La copia del catálogo guarda el estado de la biblioteca; no incluye todos los audios ni es una restauración automática.'))
    explanation.setWordWrap(True);explanation.setObjectName('muted');maintenance_layout.addWidget(explanation)
    window.verify_import=QPushButton(tr('Revisar operación pendiente'));window.verify_import.setProperty('iconKind','refresh');window.verify_import.clicked.connect(lambda:window.start_transfer('verify',[],window.backup_root))
    window.open_backup=QPushButton(tr('Ver respaldo del catálogo'));window.open_backup.setProperty('iconKind','folder')
    window.open_backup.clicked.connect(window.open_backup_folder)
    window.verify_import.setToolTip(tr('Comprueba el resultado de un envío o una eliminación sin reenviar canciones.'))
    window.open_backup.setToolTip(tr('Abre los registros y copias locales del catálogo. No incluye una copia completa de tus audios.'))
    maintenance_layout.addWidget(window.verify_import);maintenance_layout.addWidget(window.open_backup);settings_layout.addWidget(maintenance);settings_layout.addStretch()
    window.resume_import=QPushButton(tr('Completar importación pendiente'));window.resume_import.setProperty('iconKind','upload')
    window.resume_import.clicked.connect(lambda:window.start_transfer('resume',list(window.tracks.values()),window.backup_root))
    window.resume_import.setToolTip(tr('Intenta terminar la entrega de audio que falta usando el archivo original y el registro guardado.'))
    maintenance_layout.addWidget(window.resume_import)
    window.repair_metadata=QPushButton(tr('Actualizar portadas y fecha'));window.repair_metadata.setProperty('iconKind','refresh')
    window.repair_metadata.clicked.connect(lambda:window.start_transfer('repair',list(window.tracks.values()),window.backup_root))
    window.repair_metadata.setToolTip(tr('Reenvía portada y fecha de canciones previamente importadas por TUPAQ en este ordenador.'))
    maintenance_layout.addWidget(window.repair_metadata)
    ownership_note=QLabel(tr('Actualizar portadas y fecha se aplica solo a importaciones registradas por TUPAQ en este ordenador.'))
    ownership_note.setWordWrap(True);ownership_note.setObjectName('muted');maintenance_layout.addWidget(ownership_note)
    recovery_note=QLabel(tr('Completar usa el archivo original y el registro guardado de la operación. Función experimental: conserva los respaldos.'))
    recovery_note.setWordWrap(True);recovery_note.setObjectName('muted');maintenance_layout.addWidget(recovery_note)
    settings_scroll=QScrollArea();settings_scroll.setObjectName('settingsScroll');settings_scroll.setWidgetResizable(True);settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
    settings_scroll.setWidget(settings);window.pages.addWidget(settings_scroll)
    window.navigation.idClicked.connect(window.navigate)
    window.nav_buttons[0].setChecked(True)
    for surface in (sidebar,window.inspector,activity):
        shadow=QGraphicsDropShadowEffect(surface);shadow.setBlurRadius(22);shadow.setOffset(0,6);shadow.setColor(QColor(0,0,0,65));surface.setGraphicsEffect(shadow)
    window.queue_toggle.toggled.connect(window.update_buttons)
    window.setWindowIcon(app_icon())


def layout_transfer_actions(window):
    columns=4 if window.width()>=1340 else 2
    if getattr(window,'action_columns',None)==columns:return
    window.action_columns=columns
    for index,value in enumerate((window.choose,window.import_phone,window.export_phone,window.delete_phone)):
        window.transfer_actions.removeWidget(value);window.transfer_actions.addWidget(value,index//columns,index%columns)


def apply_theme(window):
    selection=window.theme_choice.currentIndex()
    dark=selection==2 or selection==0 and QApplication.styleHints().colorScheme()==Qt.ColorScheme.Dark
    c=({'bg':'#111925','side':'#101d2c','card':'#182436','text':'#f4f5fa','muted':'#a7b2c3','border':'#304052',
        'button':'#263346','hover':'#34445b','selected':'#36465c','blue':'#F09A58','accent':'#B8430A',
        'top':'#223c53','bottom':'#222137','hero':'#1d3144','heroEnd':'#1b2331'} if dark else
       {'bg':'#f6f7fb','side':'#eaeef5','card':'#ffffff','text':'#222633','muted':'#626c7d','border':'#d9deea',
        'button':'#ffffff','hover':'#edf0f6','selected':'#e2e7f2','blue':'#B8430A','accent':'#B8430A',
        'top':'#e1eaf4','bottom':'#efe7f1','hero':'#ffffff','heroEnd':'#edf2fa'})
    studio=window.mood_choice.currentIndex()==3
    if studio:
        c.update(bg='#101113' if dark else '#f5f5f7',side='#363739' if dark else '#e4e4e7',
                 card='#1d1f22' if dark else '#ffffff',border='#303236' if dark else '#d4d4d8',
                 button='#242629' if dark else '#e7e7eb',hover='#303237' if dark else '#dddde2',
                 selected='#32353a' if dark else '#dddde3')
    palette=QPalette()
    for role,key in [(QPalette.ColorRole.Window,'bg'),(QPalette.ColorRole.WindowText,'text'),(QPalette.ColorRole.Base,'bg'),
                     (QPalette.ColorRole.AlternateBase,'card'),(QPalette.ColorRole.Text,'text'),(QPalette.ColorRole.Button,'button'),(QPalette.ColorRole.ButtonText,'text'),
                     (QPalette.ColorRole.Mid,'muted'),(QPalette.ColorRole.Dark,'muted'),
                     (QPalette.ColorRole.Shadow,'border'),(QPalette.ColorRole.Light,'hover'),
                     (QPalette.ColorRole.Highlight,'selected'),(QPalette.ColorRole.HighlightedText,'text')]:palette.setColor(role,QColor(c[key]))
    window.setPalette(palette)
    window.scene.set_scene(dark,window.mood_choice.currentIndex())
    warm=window.mood_choice.currentIndex()==2
    glass='rgba(31,12,18,160)' if dark and warm else 'rgba(8,17,30,155)' if dark else 'rgba(255,255,255,175)'
    soft='rgba(255,255,255,10)' if dark else 'rgba(255,255,255,150)'
    line='rgba(255,255,255,38)' if dark else 'rgba(255,255,255,200)'
    header='#351821' if dark and warm else '#172638' if dark else '#edf2f8'
    selected='rgba(255,255,255,40)' if dark else 'rgba(35,63,103,25)'
    if studio:
        glass=c['bg'];soft=c['card'];line=c['border'];header=c['bg'];selected=c['selected']
    window.shell_layout.setContentsMargins(*((0,0,0,0) if studio else (14,14,14,14)))
    window.shell_layout.setSpacing(0 if studio else 12);window.top_layout.setSpacing(0 if studio else 14)
    radius=0 if studio else 22
    for widget in (window.inspector,window.status.parentWidget(),window.nav_buttons[0].parentWidget()):
        if widget.graphicsEffect():widget.graphicsEffect().setEnabled(not studio)
    from .typography import css_family
    family=css_family(QApplication.instance().font().family())
    window.setStyleSheet(f'''
        QWidget {{color:{c['text']};font-family:"{family}";font-size:13px;}}
        QWidget#shell {{background:transparent;}}
        QStackedWidget {{background:transparent;}}
        QFrame#sidebar {{background:{c['side'] if studio else glass};border:1px solid {line};border-radius:{radius}px;}}
        QWidget#workspace {{background:{glass};border:1px solid {line};border-radius:{radius}px;}}
        QScrollArea#settingsScroll {{background:transparent;border:0;}}
        QScrollArea#settingsScroll > QWidget {{background:transparent;}}
        QWidget#settingsPage {{background:{glass};border:1px solid {line};border-radius:{radius}px;}}
        QFrame#hero {{background:{glass};border:0;border-radius:0;}}
        QFrame#propertiesCard {{background:{soft};border:1px solid {line};border-radius:12px;}}
        QFrame#activityBar {{background:{glass};border:1px solid {line};border-radius:18px;}}
        QFrame#brandCard {{border:0;background:transparent;}}
        QLabel#brand {{font-size:16px;font-weight:600;}}
        QLabel#title {{font-size:18px;font-weight:600;}}
        QLabel#inspectorTitle {{font-size:19px;font-weight:650;}}
        QLabel#heroDescription {{color:{c['muted']};font-size:13px;}}
        QLabel#metadata {{color:{c['muted']};font-size:12px;}}
        QLabel#section {{font-size:12px;font-weight:600;color:{c['muted']};}}
        QLabel#muted {{font-size:12px;color:{c['muted']};}}
        QFrame#deviceCard {{border:1px solid {line};border-radius:14px;background:{soft};}}
        QLabel#deviceName {{font-weight:600;}}
        QLabel#cover {{background:{c['card']};color:{c['muted']};border:1px solid {c['border']};border-radius:14px;font-size:40px;}}
        QPushButton {{background:{selected};border:1px solid {line};border-radius:17px;padding:8px 15px;font-weight:500;}}
        QPushButton:hover {{background:{c['hover']};}}
        QPushButton:focus {{border:1px solid {c['muted']};}}
        QPushButton#primary {{background:{c['accent']};color:white;font-weight:600;border:1px solid rgba(255,255,255,35);padding:10px 22px;}}
        QPushButton#primary:hover {{background:#A93A08;}}
        QPushButton:disabled,QPushButton#primary:disabled {{background:{c['bg']};color:{c['muted']};border:1px solid {c['border']};}}
        QPushButton#nav {{background:transparent;border:0;text-align:left;border-radius:8px;padding:8px 10px;}}
        QPushButton#nav:checked {{background:{selected};font-weight:600;}}

        QTableWidget,QTableView {{background:{c['bg'] if studio else 'rgba(0,0,0,22)'};border:1px solid {line};border-radius:15px;selection-background-color:{selected};selection-color:{c['text']};outline:0;}}
        QTableWidget::item,QTableView::item {{padding:7px;background:{c['card'] if studio else 'transparent'};border-bottom:{4 if studio else 1}px solid {c['bg'] if studio else 'rgba(150,160,180,18)'};}}
        QTableWidget::item:selected,QTableView::item:selected {{background:{selected};}}
        QTableWidget::item:hover,QTableView::item:hover {{background:{c['hover']};}}
        QHeaderView {{background:{header};border:0;}}
        QHeaderView::section {{background:{header};color:{c['muted']};padding:8px 5px;border:0;border-bottom:1px solid {c['border']};font-size:12px;font-weight:500;}}
        QLineEdit {{background:{selected};border:1px solid {line};border-radius:13px;padding:8px 12px;}}
        QLineEdit:focus {{border:1px solid {c['accent']};}}
        QComboBox {{background:{c['button']};border:1px solid {c['border']};padding:5px 9px;border-radius:11px;}}
        QComboBox QAbstractItemView {{background:{c['card']};color:{c['text']};}}
        QFrame#tableCard {{background:{c['card']};border:1px solid {c['border']};border-radius:12px;}}
        QFrame#queuePanel {{border-top:1px solid {line};}}
        QScrollArea#inspector {{background:{c['bg']};border:0;border-left:1px solid {c['border']};}}
        QScrollArea#inspector > QWidget > QWidget {{background:{c['bg']};}}
        QProgressBar {{background:{c['border']};border:0;border-radius:3px;text-align:center;}}
        QProgressBar::chunk {{background:{c['blue']};border-radius:3px;}}
        QListWidget {{background:{c['card']};border:1px solid {c['border']};border-radius:8px;}}
        QTableCornerButton::section {{background:{header};border:0;}}
        QScrollBar:vertical {{background:transparent;width:8px;margin:0;}}
        QScrollBar::handle:vertical {{background:rgba(150,160,180,100);min-height:24px;border-radius:4px;}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
        QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:transparent;}}
        QSplitter::handle {{background:{c['border']};width:1px;height:1px;}}
    ''')
    for value in window.findChildren(QPushButton):
        kind=value.property('iconKind')
        if kind:value.setIcon(line_icon(kind,c['muted'],18))
    window.default_music_icon=line_icon('music',c['muted'],36);window.library_model.default_icon=window.default_music_icon
    if window.library_model.rowCount():window.library_model.dataChanged.emit(window.library_model.index(0,0),window.library_model.index(window.library_model.rowCount()-1,0),[Qt.ItemDataRole.DecorationRole])
    window.theme_dark=dark

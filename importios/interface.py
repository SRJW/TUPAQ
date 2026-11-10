"""Native teal/orange desktop composition shared by light and dark appearances."""
from pathlib import Path
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QColor,QPalette,QFontMetrics,QPainter,QPixmap,QPen
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QButtonGroup,QStackedWidget,
    QGridLayout,QHeaderView,QTableView,QSplitter,QAbstractItemView,QProgressBar,QApplication,
    QScrollArea,QDialog,QSizePolicy)
from .models import LibraryModel,SelectionDelegate
from .visuals import app_icon,line_icon
from .surfaces import Atmosphere
from .motion import MotionButton,CoverView
from .i18n import tr,QLabel,QPushButton,QCheckBox,QComboBox,QLineEdit,QTableWidget,QListWidget


def button(text,kind=None,handler=None):
    value=MotionButton(tr(text));value.setIconSize(QSize(18,18))
    if kind:value.setProperty('iconKind',kind)
    if handler:value.clicked.connect(handler)
    value.setMinimumHeight(36)
    value.setMinimumWidth(QFontMetrics(value.font()).horizontalAdvance(str(value.text()))+(48 if kind else 30))
    return value


def text_label(text,role=None,wrap=False):
    value=QLabel(tr(text));value.setTextFormat(Qt.TextFormat.PlainText);value.setWordWrap(wrap)
    if role:value.setObjectName(role)
    return value


def panel(title=None,description=None):
    value=QFrame();value.setObjectName('tableCard');layout=QVBoxLayout(value)
    layout.setContentsMargins(20,18,20,18);layout.setSpacing(14)
    if title:layout.addWidget(text_label(title,'cardTitle'))
    if description:layout.addWidget(text_label(description,'muted',True))
    return value,layout


def page(title,description=None):
    value=QWidget();value.setObjectName('workspace');layout=QVBoxLayout(value)
    layout.setContentsMargins(24,20,24,16);layout.setSpacing(16)
    header=QHBoxLayout();header.setSpacing(8);heading=text_label(title,'title');header.addWidget(heading);header.addStretch()
    layout.addLayout(header)
    if description:layout.addWidget(text_label(description,'muted',True))
    return value,layout,header,heading


def theme_thumbnail(dark):
    image=QPixmap(212,116);image.setDevicePixelRatio(2);image.fill(Qt.GlobalColor.transparent)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor('#527172' if dark else '#d4deda'),.8));painter.setBrush(QColor('#102326' if dark else '#fbfaf8'));painter.drawRoundedRect(1,1,104,56,6,6)
    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#233c3e' if dark else '#eeeae4'));painter.drawRoundedRect(3,3,23,52,4,4)
    painter.setBrush(QColor('#755035' if dark else '#3b7b7b'));painter.drawRoundedRect(5,17,19,7,2,2)
    painter.setBrush(QColor('#345657' if dark else '#e4eeeb'));painter.drawRoundedRect(30,8,69,14,3,3)
    painter.setBrush(QColor('#ed751c'));painter.drawRoundedRect(31,27,20,6,2,2)
    painter.setPen(QPen(QColor('#466263' if dark else '#d8e2de'),1))
    for y in (38,44,50):painter.drawLine(31,y,97,y)
    painter.end();return image


def build(window):
    root=Atmosphere();window.scene=root;window.setCentralWidget(root)
    shell=QVBoxLayout(root);window.shell_layout=shell;shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
    outer=QHBoxLayout();window.top_layout=outer;outer.setSpacing(0);outer.setContentsMargins(0,0,0,0);shell.addLayout(outer,1)
    sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(180);window.sidebar=sidebar
    side=QVBoxLayout(sidebar);side.setContentsMargins(14,26,14,18);side.setSpacing(8)
    brand_row=QHBoxLayout();brand_row.setSpacing(10);mark=QLabel();mark.setPixmap(app_icon().pixmap(34,34));brand_row.addWidget(mark)
    brand=text_label('TUPAQ','brand');brand_row.addWidget(brand);brand_row.addStretch();side.addLayout(brand_row);side.addSpacing(26)
    window.navigation=QButtonGroup(window);window.nav_buttons=[None]*4
    # Keep stable page identities for saved/controller references; order matches the design.
    for index,text,kind in [(0,'Biblioteca','library'),(2,'Importar','upload'),(3,'Diagnóstico','pulse'),(1,'Preferencias','settings')]:
        value=button(text,kind);value.setObjectName('nav');value.setCheckable(True);value.setMinimumHeight(42)
        window.navigation.addButton(value,index);window.nav_buttons[index]=value;side.addWidget(value)
    side.addStretch()
    footer=QFrame();footer.setObjectName('connectionPill');footer_layout=QHBoxLayout(footer);footer_layout.setContentsMargins(10,10,10,10);footer_layout.setSpacing(6)
    window.sidebar_dot=text_label('●','connectionDot');window.sidebar_dot.setProperty('connected',False);footer_layout.addWidget(window.sidebar_dot)
    window.sidebar_connection=text_label('Sin conexión USB','small');footer_layout.addWidget(window.sidebar_connection,1);side.addWidget(footer)
    side.addWidget(text_label('Local · USB','muted'))
    outer.addWidget(sidebar)
    window.pages=QStackedWidget();outer.addWidget(window.pages,1)

    workspace,layout,toolbar,window.heading=page('Biblioteca');window.local_tools=workspace
    window.inspector_toggle=button('Detalles','info');window.inspector_toggle.setCheckable(True)
    window.library_button=button('','refresh',window.load_library);window.library_button.setToolTip(tr('Volver a leer la biblioteca y comprobar sus archivos'))
    diagnostics_link=button('Diagnóstico','pulse',lambda:window.navigate(3))
    for value in (window.inspector_toggle,window.library_button,diagnostics_link):toolbar.addWidget(value)
    window.device_hero=QFrame();window.device_hero.setObjectName('deviceHero');hero=QHBoxLayout(window.device_hero);hero.setContentsMargins(18,16,18,16);hero.setSpacing(16)
    window.device_symbol=QLabel();window.device_symbol.setObjectName('deviceSymbol');window.device_symbol.setFixedSize(48,56);window.device_symbol.setAlignment(Qt.AlignmentFlag.AlignCenter);hero.addWidget(window.device_symbol)
    identity=QVBoxLayout();identity.setSpacing(6)
    window.device_name=text_label('iPhone','deviceName');window.device_name.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);window.device_name.setWordWrap(True);identity.addWidget(window.device_name)
    state=QHBoxLayout();state.setSpacing(6);window.connection_dot=text_label('●','connectionDot');window.connection_dot.setProperty('connected',False)
    window.connection_badge=text_label('Sin conexión USB','muted');state.addWidget(window.connection_dot);state.addWidget(window.connection_badge);state.addStretch();identity.addLayout(state);hero.addLayout(identity,1)
    window.device_metric=text_label('Tu biblioteca por USB','deviceMetric');hero.addWidget(window.device_metric)
    window.device_button=button('Comprobar USB','phone',window.check_device);hero.addWidget(window.device_button);layout.addWidget(window.device_hero)
    window.choose=button('Añadir canciones','plus',window.choose_files);window.choose.setObjectName('primary')
    window.import_phone=button('Importar','upload',window.import_songs)
    window.import_phone.setToolTip(tr('Enviar la selección de la cola del ordenador; sin selección, enviar toda la cola.'))
    window.export_phone=button('Exportar','download',window.export_songs)
    window.export_phone.setToolTip(tr('Exportar al ordenador las canciones seleccionadas del iPhone.'))
    window.transfer_actions=QGridLayout();window.transfer_actions.setSpacing(12);window.transfer_actions.setContentsMargins(0,0,0,0)
    layout.addLayout(window.transfer_actions);layout_transfer_actions(window)
    window.device_status=text_label('Conecta tu iPhone para mostrar su música.','muted',True);window.device_status.setMaximumHeight(64);window.device_status.hide();layout.addWidget(window.device_status)
    window.search=QLineEdit();window.search.setPlaceholderText(tr('Buscar canción, artista, álbum o formato (.m4a, .mp3…)'));window.search.setClearButtonEnabled(True);window.search.setMinimumHeight(38)
    search_row=QHBoxLayout();search_row.setSpacing(10);search_row.addWidget(window.search,1)
    window.format_filter=QComboBox();window.format_filter.addItems(['Todos los formatos','M4A','MP3','AAC','ALAC','WAV','AIFF','M4P']);search_row.addWidget(window.format_filter)
    window.content_filter=QComboBox();window.content_filter.addItems(['Toda la música','Con carátula','Con letra']);search_row.addWidget(window.content_filter);layout.addLayout(search_row)
    window.main_splitter=QSplitter(Qt.Orientation.Vertical)
    window.library_panel=QFrame();window.library_panel.setObjectName('libraryCard');phone_layout=QVBoxLayout(window.library_panel);phone_layout.setContentsMargins(0,0,0,0);phone_layout.setSpacing(0)
    window.library_model=LibraryModel(window);window.library_table=QTableView();window.library_table.setModel(window.library_model);window.library_table.setItemDelegateForColumn(0,SelectionDelegate(window.library_table));phone_layout.addWidget(window.library_table)
    from .presentation import LibraryEmptyState
    window.library_empty=LibraryEmptyState(window.library_table,window)
    window.main_splitter.addWidget(window.library_panel);window.main_splitter.setChildrenCollapsible(False);layout.addWidget(window.main_splitter,1)
    collection=QHBoxLayout();collection.setSpacing(12)
    window.library_heading=text_label('En el iPhone','muted');window.selection_count=text_label('','muted');collection.addWidget(window.library_heading);collection.addWidget(window.selection_count);collection.addStretch()
    window.delete_phone=button('Eliminar','trash',window.delete_songs);window.delete_phone.setObjectName('destructive')
    window.delete_phone.setToolTip(tr('Eliminar de Música las canciones marcadas; pide confirmación.'));collection.addWidget(window.delete_phone)
    window.select_visible=QCheckBox(tr('Seleccionar visibles'));window.select_visible.setTristate(True);collection.addWidget(window.select_visible);layout.addLayout(collection)
    window.pages.addWidget(workspace)

    settings,settings_layout,_,_=page('Preferencias','Personaliza TUPAQ y la gestión de tu música.')
    settings_body=QHBoxLayout();settings_body.setSpacing(18);settings_layout.addLayout(settings_body,1)
    settings_menu=QFrame();settings_menu.setObjectName('settingsMenu');settings_menu.setFixedWidth(176);window.settings_menu=settings_menu;menu=QVBoxLayout(settings_menu);menu.setContentsMargins(8,10,8,10);menu.setSpacing(6)
    window.settings_pages=QStackedWidget();window.settings_navigation=QButtonGroup(window)
    window.settings_buttons=[]
    for index,(title,kind) in enumerate([('Apariencia','sun'),('Rutas de biblioteca','folder'),('Metadatos','tag'),('Carátulas','image'),('Idioma','globe'),('Sincronización','refresh')]):
        nav=button(title,kind);nav.setObjectName('settingsNav');nav.setCheckable(True);window.settings_navigation.addButton(nav,index);menu.addWidget(nav);window.settings_buttons.append(nav)
        content=QWidget();content_layout=QVBoxLayout(content);content_layout.setContentsMargins(0,0,0,0);content_layout.setSpacing(14)
        surface,body=panel(title);content_layout.addWidget(surface);content_layout.addStretch()
        window.settings_pages.addWidget(content)
        if index==0:appearance=body
        elif index==1:paths=body
        elif index==2:metadata=body
        elif index==3:artwork=body
        elif index==4:languages=body
        else:sync=body
    menu.addStretch();settings_body.addWidget(settings_menu);settings_body.addWidget(window.settings_pages,1)
    window.settings_navigation.idClicked.connect(window.settings_pages.setCurrentIndex);window.settings_buttons[0].setChecked(True)
    window.theme_choice=QComboBox(settings);window.theme_choice.addItems(['Sistema','Claro','Oscuro']);window.theme_choice.setCurrentIndex(2);window.theme_choice.hide()
    window.mood_choice=QComboBox(settings);window.mood_choice.addItems(['Nocturno','Aurora','Atardecer','Tonal']);window.mood_choice.setCurrentIndex(3);window.mood_choice.hide()
    window.theme_options={};theme_row=QHBoxLayout();theme_row.setSpacing(12)
    window.theme_group=QButtonGroup(window)
    for index,title in [(1,'Claro'),(2,'Oscuro'),(0,'Sistema')]:
        option=button('');option.setProperty('themeCard',True);option.setCheckable(True);option.setMinimumSize(126,112);option.setAccessibleName(tr(title))
        inner=QVBoxLayout(option);inner.setContentsMargins(12,14,12,12);inner.setSpacing(9)
        preview=QLabel();preview.setAlignment(Qt.AlignmentFlag.AlignCenter);preview.setPixmap(theme_thumbnail(index==2));inner.addWidget(preview)
        caption=text_label(title);caption.setAlignment(Qt.AlignmentFlag.AlignCenter);inner.addWidget(caption)
        for child in (preview,caption):child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        window.theme_group.addButton(option,index);theme_row.addWidget(option,1);window.theme_options[index]=option
    window.theme_group.idClicked.connect(window.theme_choice.setCurrentIndex);appearance.addLayout(theme_row)
    window.use_accent=QCheckBox(tr('Usar el color naranja de TUPAQ'));window.use_accent.setChecked(True);appearance.addWidget(window.use_accent)
    window.reduce_transparency=QCheckBox(tr('Reducir transparencia'));appearance.addWidget(window.reduce_transparency)
    window.reduce_motion=QCheckBox(tr('Reducir movimiento'));window.reduce_motion.setChecked(not window.motion.enabled);appearance.addWidget(window.reduce_motion)
    window.font_status=text_label(getattr(QApplication.instance(),'typography_status','Fuente del sistema'),'muted',True);appearance.addWidget(window.font_status)
    appearance.addWidget(text_label('TUPAQ utiliza la fuente del sistema en toda la interfaz.','muted',True))
    window.reduce_motion.toggled.connect(window.change_motion)
    window.use_accent.toggled.connect(window.change_visual_options);window.reduce_transparency.toggled.connect(window.change_visual_options)
    paths.addWidget(text_label('Carpeta inicial para elegir y exportar música.','muted',True))
    window.library_path=QLineEdit();window.library_path.setReadOnly(True);paths.addWidget(window.library_path)
    paths.addWidget(button('Cambiar carpeta…','folder',window.choose_library_path))
    metadata.addWidget(text_label('Se aplica a los próximos envíos. Los archivos originales se conservan.','muted',True))
    window.metadata_choice=QComboBox();window.metadata_choice.addItems(['Conservar metadatos (recomendado)','Usar nombre de archivo como título']);metadata.addWidget(window.metadata_choice)
    window.import_artwork=QCheckBox(tr('Importar carátulas cuando estén disponibles'));window.import_artwork.setChecked(True);artwork.addWidget(window.import_artwork)
    artwork.addWidget(text_label('Controla el envío al catálogo. Las carátulas ya incrustadas en los originales se conservan.','muted',True))
    window.embed_artwork=QCheckBox(tr('Incrustar carátulas en las copias exportadas'));artwork.addWidget(window.embed_artwork)
    artwork.addWidget(text_label('Completa la carátula de la copia exportada cuando exista en el catálogo. El audio del iPhone no se modifica.','muted',True))
    window.language_choice=QComboBox()
    from .i18n import LANGUAGES
    for code,title in LANGUAGES:window.language_choice.addItem(title,code)
    languages.addWidget(window.language_choice);languages.addWidget(text_label('El idioma se aplica al instante y se conserva al volver a abrir TUPAQ.','muted',True))
    window.auto_read=QCheckBox(tr('Detectar el iPhone y abrir su biblioteca automáticamente'));window.auto_read.setChecked(True);sync.addWidget(window.auto_read)
    window.auto_import=QCheckBox(tr('Importar automáticamente al preparar canciones'));sync.addWidget(window.auto_import)
    sync.addWidget(text_label('Solo con el mismo iPhone conectado y su biblioteca leída. Desactivado inicialmente.','muted',True))
    window.refresh_after_transfer=QCheckBox(tr('Actualizar la biblioteca al detectar cambios'));window.refresh_after_transfer.setChecked(True);sync.addWidget(window.refresh_after_transfer)
    sync.addWidget(text_label('La comprobación de cada transferencia siempre permanece activa.','muted',True))
    settings_scroll=QScrollArea();settings_scroll.setObjectName('settingsScroll');settings_scroll.setWidgetResizable(True);settings_scroll.setFrameShape(QFrame.Shape.NoFrame);settings_scroll.setWidget(settings);window.pages.addWidget(settings_scroll)

    import_page,import_layout,import_header,_=page('Importar','Añade música a la biblioteca de tu iPhone.')
    history_button=button('Historial','history',window.open_history);import_header.addWidget(history_button)
    top=QHBoxLayout();top.setSpacing(16)
    drop,drop_layout=panel();drop.setObjectName('importDrop');drop_layout.setContentsMargins(24,26,24,26)
    window.drop_symbol=QLabel();window.drop_symbol.setAlignment(Qt.AlignmentFlag.AlignCenter);drop_layout.addWidget(window.drop_symbol)
    title=text_label('Arrastra archivos o carpetas de música aquí','cardTitle',True);title.setAlignment(Qt.AlignmentFlag.AlignCenter);drop_layout.addWidget(title)
    note=text_label('O elige una opción para preparar tus canciones.','muted',True);note.setAlignment(Qt.AlignmentFlag.AlignCenter);drop_layout.addWidget(note)
    choices=QHBoxLayout();window.import_choose=button('Elegir archivos…','file',window.choose_files);window.import_choose.setObjectName('primary')
    window.folder_choose=button('Elegir carpeta…','folder',window.choose_folder);choices.addStretch();choices.addWidget(window.import_choose);choices.addWidget(window.folder_choose);choices.addStretch();drop_layout.addLayout(choices);top.addWidget(drop,1)
    formats,formats_layout=panel('Formatos compatibles');formats.setFixedWidth(202)
    chips=QGridLayout()
    for i,text in enumerate(('M4A','MP3','AAC','ALAC','WAV','AIFF')):
        chip=text_label(text,'formatChip');chip.setAlignment(Qt.AlignmentFlag.AlignCenter);chips.addWidget(chip,i//3,i%3)
    formats_layout.addLayout(chips);formats_layout.addWidget(text_label('AAC y ALAC dentro de M4A. Los originales se conservan.','muted',True));formats_layout.addStretch();top.addWidget(formats);import_layout.addLayout(top)
    bottom=QHBoxLayout();bottom.setSpacing(16)
    window.queue_panel,queue_layout=panel();queue_layout.setContentsMargins(14,14,14,14)
    queue_header=QHBoxLayout();queue_header.addWidget(text_label('Cola de importación','cardTitle'),1)
    window.queue_toggle=button('Cola','library');window.queue_toggle.setCheckable(True);window.queue_toggle.setChecked(True)
    window.remove=button('Quitar','trash',window.remove_selection);window.clear=button('Vaciar','close',window.clear_tracks);window.export=button('CSV','folder',window.choose_export)
    for value in (window.remove,window.clear,window.export):queue_header.addWidget(value)
    queue_layout.addLayout(queue_header)
    window.table=QTableWidget(0,7);window.table.setHorizontalHeaderLabels(['Canción','Artista','Álbum','Formato','Duración','Tamaño','Estado']);window.table.setItemDelegateForColumn(0,SelectionDelegate(window.table));queue_layout.addWidget(window.table,1)
    window.table.setColumnHidden(1,True);window.table.setColumnHidden(2,True)
    bottom.addWidget(window.queue_panel,1)
    queue_summary,summary_layout=panel('Sincronización');queue_summary.setFixedWidth(226)
    window.queue_summary=text_label('Sin canciones para importar.','muted',True);summary_layout.addWidget(window.queue_summary)
    window.import_submit=button('Importar al iPhone','upload',window.import_songs);window.import_submit.setObjectName('primary');summary_layout.addWidget(window.import_submit)
    window.import_progress=QProgressBar();window.import_progress.setRange(0,100);window.import_progress.setTextVisible(False);window.import_progress.setFixedHeight(8);window.import_progress.hide();summary_layout.addWidget(window.import_progress)
    window.transfer_stage=text_label('Selecciona canciones para preparar la importación.','muted',True);summary_layout.addWidget(window.transfer_stage)
    window.stage_labels=[]
    for title in ('Preparación','Transferencia','Comprobación'):
        stage=text_label(title,'muted');window.stage_labels.append(stage);summary_layout.addWidget(stage)
    summary_layout.addStretch()
    bottom.addWidget(queue_summary);import_layout.addLayout(bottom,1);window.pages.addWidget(import_page)
    window.queue_toggle.setParent(import_page);window.queue_toggle.hide()

    diagnostics,diagnostics_layout,diagnostic_header,_=page('Diagnóstico','Estado del dispositivo y comprobaciones de lectura.')
    window.diagnostic_refresh=button('Actualizar','refresh',window.refresh_device_details);diagnostic_header.addWidget(window.diagnostic_refresh)
    window.diagnostic_run=button('Comprobar todo','pulse',window.run_diagnostics);window.diagnostic_run.setObjectName('secondaryAccent');diagnostic_header.addWidget(window.diagnostic_run)
    device,device_layout=panel();device_row=QHBoxLayout();window.diagnostic_symbol=QLabel();window.diagnostic_symbol.setFixedSize(58,78);device_row.addWidget(window.diagnostic_symbol)
    diag_identity=QVBoxLayout();window.diagnostic_name=text_label('iPhone','deviceName');window.diagnostic_model=text_label('Información pendiente de lectura.','muted',True);diag_identity.addWidget(window.diagnostic_name);diag_identity.addWidget(window.diagnostic_model);device_row.addLayout(diag_identity,1)
    window.diagnostic_state=text_label('Sin conexión USB','statusPill');device_row.addWidget(window.diagnostic_state);device_layout.addLayout(device_row);diagnostics_layout.addWidget(device)
    grid=QGridLayout();grid.setSpacing(16);window.diagnostic_fields={};window.health_fields={}
    storage,storage_layout=panel('Almacenamiento (datos)','Última lectura del volumen de datos del dispositivo.')
    window.diagnostic_fields['storage']=text_label('Pendiente','metric');storage_layout.addWidget(window.diagnostic_fields['storage'])
    window.storage_bar=QProgressBar();window.storage_bar.setRange(0,1000);window.storage_bar.setTextVisible(False);window.storage_bar.setFixedHeight(10);window.storage_bar.hide();storage_layout.addWidget(window.storage_bar)
    window.diagnostic_fields['library']=text_label('Pendiente','muted');storage_layout.addWidget(window.diagnostic_fields['library']);grid.addWidget(storage,0,0)
    checks,checks_layout=panel('Comprobaciones');checks_grid=QGridLayout();checks_grid.setVerticalSpacing(12)
    for row,(key,title) in enumerate([('connection','Conexión del dispositivo'),('database','Base de datos'),('permissions','Permisos del catálogo'),('integrity','Integridad con recibos')]):
        checks_grid.addWidget(text_label(title,'muted'),row,0);value=text_label('Pendiente','checkState');value.setAlignment(Qt.AlignmentFlag.AlignRight);value.setWordWrap(True);checks_grid.addWidget(value,row,1);window.health_fields[key]=value
    checks_grid.setColumnStretch(1,1);checks_layout.addLayout(checks_grid);grid.addWidget(checks,0,1)
    compatibility,compatibility_layout=panel('Compatibilidad','MP3 · WAV · M4A (AAC/ALAC) · AIFF')
    window.diagnostic_fields['formats']=text_label('Formatos admitidos','metric');compatibility_layout.addWidget(window.diagnostic_fields['formats'])
    window.diagnostic_fields['files']=text_label('Pendiente','muted',True);compatibility_layout.addWidget(window.diagnostic_fields['files']);grid.addWidget(compatibility,1,0)
    usb,usb_layout=panel('Conexión USB','Detección y acceso al dispositivo.')
    window.diagnostic_fields['connection']=text_label('Sin conexión USB','metric');usb_layout.addWidget(window.diagnostic_fields['connection']);grid.addWidget(usb,1,1)
    diagnostics_layout.addLayout(grid)
    window.copy_diagnostic=button('Copiar diagnóstico','copy');window.last_diagnostic='';window.copy_diagnostic.setEnabled(False);window.copy_diagnostic.clicked.connect(lambda:QApplication.clipboard().setText(window.last_diagnostic));diagnostics_layout.addWidget(window.copy_diagnostic,0,Qt.AlignmentFlag.AlignLeft)
    window.diagnostic_note=text_label('Las comprobaciones solo leen el dispositivo; no modifican su biblioteca.','muted',True);diagnostics_layout.addWidget(window.diagnostic_note)
    maintenance=QFrame();maintenance.setObjectName('tableCard');maintenance_layout=QVBoxLayout(maintenance);maintenance_layout.setContentsMargins(20,20,20,20)
    window.advanced=QCheckBox(tr('Mostrar opciones avanzadas de recuperación'));diagnostics_layout.addWidget(window.advanced)
    window.advanced.toggled.connect(maintenance.setVisible);maintenance.hide()
    maintenance_layout.addWidget(QLabel(tr('Recuperación y registros de transferencias')))
    explanation=QLabel(tr('No necesitas estas herramientas para importar normalmente. Sirven para comprobar o recuperar un envío interrumpido. La copia del catálogo guarda el estado de la biblioteca; no incluye todos los audios ni es una restauración automática.'))
    explanation.setWordWrap(True);explanation.setObjectName('muted');maintenance_layout.addWidget(explanation)
    window.verify_import=QPushButton(tr('Revisar operación pendiente'));window.verify_import.setProperty('iconKind','refresh');window.verify_import.clicked.connect(lambda:window.start_transfer('verify',[],window.backup_root))
    window.open_backup=QPushButton(tr('Ver respaldo del catálogo'));window.open_backup.setProperty('iconKind','folder')
    window.open_backup.clicked.connect(window.open_backup_folder)
    window.verify_import.setToolTip(tr('Comprueba el resultado de un envío o una eliminación sin reenviar canciones.'))
    window.open_backup.setToolTip(tr('Abre los registros y copias locales del catálogo. No incluye una copia completa de tus audios.'))
    maintenance_layout.addWidget(window.verify_import);maintenance_layout.addWidget(window.open_backup);diagnostics_layout.addWidget(maintenance);diagnostics_layout.addStretch()
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

    diagnostics_scroll=QScrollArea();diagnostics_scroll.setObjectName('settingsScroll');diagnostics_scroll.setWidgetResizable(True);diagnostics_scroll.setFrameShape(QFrame.Shape.NoFrame);diagnostics_scroll.setWidget(diagnostics);window.pages.addWidget(diagnostics_scroll)
    window.inspector_dialog=QDialog(window);window.inspector_dialog.setWindowTitle(tr('Detalles de la canción'));window.inspector_dialog.resize(500,720)
    dialog_layout=QVBoxLayout(window.inspector_dialog);dialog_layout.setContentsMargins(16,16,16,16)
    window.inspector=QFrame();window.inspector.setObjectName('hero')
    hero_layout=QVBoxLayout(window.inspector);hero_layout.setContentsMargins(16,18,16,18);hero_layout.setSpacing(12)
    window.info_origin=QLabel(tr('TU COLECCIÓN'));window.info_origin.setObjectName('section');hero_layout.addWidget(window.info_origin)
    window.now_title=QLabel(tr('Tu música, siempre contigo.'));window.now_title.setObjectName('inspectorTitle');window.now_title.setWordWrap(True);window.now_title.setTextFormat(Qt.TextFormat.PlainText);hero_layout.addWidget(window.now_title)
    window.info_artist=QLabel(tr('Selecciona una canción para ver sus detalles.'));window.info_artist.setObjectName('muted');window.info_artist.setWordWrap(True);window.info_artist.setTextFormat(Qt.TextFormat.PlainText);hero_layout.addWidget(window.info_artist)
    window.now_cover=CoverView('♪');window.now_cover.setFixedSize(224,224);window.now_cover.setObjectName('cover');window.now_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
    window.inspector_details=[window.cover_metadata,window.view_cover,window.lyrics_status,window.view_lyrics,properties_title,properties]
    for value in window.inspector_details:value.hide()
    description=QLabel(tr('Lleva tus canciones a Música y conserva tus originales en el ordenador.'));description.setObjectName('heroDescription');description.setWordWrap(True);hero_layout.addWidget(description);hero_layout.addStretch()
    window.inspector_scroll=QScrollArea();window.inspector_scroll.setObjectName('inspector');window.inspector_scroll.setWidgetResizable(True);window.inspector_scroll.setFrameShape(QFrame.Shape.NoFrame);window.inspector_scroll.setMinimumWidth(360);window.inspector_scroll.setWidget(window.inspector)
    dialog_layout.addWidget(window.inspector_scroll)
    close_details=button('Cerrar','close',window.inspector_dialog.close);dialog_layout.addWidget(close_details)
    window.inspector_toggle.setChecked(False);window.inspector_toggle.toggled.connect(window.inspector_dialog.setVisible)
    window.inspector_dialog.finished.connect(lambda _:window.inspector_toggle.setChecked(False))
    activity=QFrame();activity.setObjectName('activityBar');activity_layout=QHBoxLayout(activity);activity_layout.setContentsMargins(18,8,18,8);activity_layout.setSpacing(12)
    window.status=text_label('Sin canciones para importar.','muted',True);activity_layout.addWidget(window.status,1)
    window.progress=QProgressBar();window.progress.setFixedWidth(180);window.progress.setFixedHeight(8);window.progress.setTextVisible(False);window.progress.hide();activity_layout.addWidget(window.progress)
    window.pause_transfer_button=button('Pausar','pause',window.pause_transfer);window.pause_transfer_button.hide();activity_layout.addWidget(window.pause_transfer_button)
    window.cancel_transfer_button=button('Cancelar','close',window.cancel_transfer);window.cancel_transfer_button.hide();activity_layout.addWidget(window.cancel_transfer_button);shell.addWidget(activity)
    window.errors=QListWidget();window.errors.setMaximumHeight(80);window.errors.hide();import_layout.addWidget(window.errors)
    for table in (window.table,window.library_table):
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.verticalHeader().hide();table.setShowGrid(False);table.setAlternatingRowColors(True)
        table.setIconSize(QSize(28,28));table.verticalHeader().setDefaultSectionSize(max(42,QFontMetrics(table.font()).height()+16));table.setWordWrap(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionsClickable(True);table.setSortingEnabled(True);table.horizontalHeader().setMinimumHeight(38)
    set_column_metrics(window)
    window.table.setColumnWidth(6,QFontMetrics(window.table.font()).horizontalAdvance('Comprobando…')+28)
    window.library_table.sortByColumn(0,Qt.SortOrder.AscendingOrder);window.table.sortItems(0,Qt.SortOrder.AscendingOrder)
    window.library_table.selectionModel().selectionChanged.connect(window.library_selection_changed);window.table.itemSelectionChanged.connect(window.local_selection_changed)
    window.library_table.horizontalHeader().sortIndicatorChanged.connect(window.schedule_artwork);window.search.textChanged.connect(window.filter_library);window.format_filter.currentIndexChanged.connect(window.filter_library);window.content_filter.currentIndexChanged.connect(window.filter_library)
    window.library_model.checkedChanged.connect(window.checks_changed);window.select_visible.clicked.connect(window.library_model.check_visible)
    window.navigation.idClicked.connect(window.navigate);window.nav_buttons[0].setChecked(True)
    for control in (window.metadata_choice,):control.currentIndexChanged.connect(window.save_transfer_preferences)
    for control in (window.import_artwork,window.embed_artwork,window.auto_import,window.refresh_after_transfer):control.toggled.connect(window.save_transfer_preferences)
    from .presentation import DropVeil
    window.drop_veil=DropVeil(root);window.setWindowIcon(app_icon())


def set_column_metrics(window):
    """Reserve intrinsic text width, including sort arrows, padding and DPI scaling."""
    for table in (window.library_table,window.table):
        metrics=QFontMetrics(table.font())
        for column,sample in ((1,'Artista de la canción'),(2,'Nombre del álbum'),(3,'M4A · ALAC'),(4,'Duración'),(5,'999.9 MB')):
            table.setColumnWidth(column,metrics.horizontalAdvance(sample)+32)


def layout_transfer_actions(window):
    window.action_columns=3
    for index,value in enumerate((window.choose,window.import_phone,window.export_phone)):
        value.setMinimumHeight(44);window.transfer_actions.addWidget(value,0,index);window.transfer_actions.setColumnStretch(index,1)


def apply_theme(window):
    selection=window.theme_choice.currentIndex()
    dark=selection==2 or selection==0 and QApplication.styleHints().colorScheme()==Qt.ColorScheme.Dark
    c=({'bg':'#0f1b1d','side':'#0c2225','card':'#173437','cardEnd':'#142e31','text':'#f0f6f5','muted':'#adc3c2',
        'border':'#2d494c','button':'#1e3c40','hover':'#2a4e52','selected':'#284b4e','alternate':'#13292c',
        'orange':'#f27620','primaryText':'#241309','primaryHover':'#ff973d','nav':'#61412b','navBorder':'#936135'} if dark else
       {'bg':'#fbfaf8','side':'#f2efea','card':'#ffffff','cardEnd':'#f6f0ea','text':'#153536','muted':'#536a6c',
        'border':'#deded8','button':'#fcfaf7','hover':'#f0e9e1','selected':'#e3efed','alternate':'#f6f8f5',
        'orange':'#bf4c00','primaryText':'#ffffff','primaryHover':'#a64100','nav':'#276a6d','navBorder':'#367f80'})
    accent=window.use_accent.isChecked();reduced=window.reduce_transparency.isChecked()
    if not accent:c.update(orange='#58b9b5' if dark else '#246d70',primaryText='#10292b' if dark else '#ffffff',primaryHover='#7bcbc7' if dark else '#16575b',nav='#285b5d' if dark else '#276a6d',navBorder='#367f80')
    window.colors=c
    palette=QPalette(window.palette())
    for role,key in [(QPalette.ColorRole.Window,'bg'),(QPalette.ColorRole.WindowText,'text'),(QPalette.ColorRole.Base,'bg'),(QPalette.ColorRole.AlternateBase,'alternate'),
                     (QPalette.ColorRole.Text,'text'),(QPalette.ColorRole.Button,'button'),(QPalette.ColorRole.ButtonText,'text'),(QPalette.ColorRole.Mid,'muted'),
                     (QPalette.ColorRole.Dark,'muted'),(QPalette.ColorRole.Shadow,'border'),(QPalette.ColorRole.Light,'hover'),(QPalette.ColorRole.Highlight,'selected'),(QPalette.ColorRole.HighlightedText,'text')]:palette.setColor(role,QColor(c[key]))
    window.setPalette(palette)
    window.scene.set_scene(dark,3)
    if getattr(window.scene,'reduced',False)!=reduced:window.scene.reduced=reduced;window.scene.cache=None;window.scene.update()
    from .typography import css_family
    app=QApplication.instance();family=css_family(getattr(app,'typography_family',app.font().family()));base=app.font().pointSizeF()
    material=lambda color:'rgba('+','.join(str(v) for v in QColor(color).getRgb()[:3])+',238)'
    panel_bg=c['card'] if reduced else f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {material(c['card'])},stop:1 {material(c['cardEnd'])})"
    check=(Path(__file__).with_name('assets')/('check-dark.svg' if dark else 'check-light.svg')).as_posix()
    chevron=(Path(__file__).with_name('assets')/('chevron-dark.svg' if dark else 'chevron-light.svg')).as_posix()
    window.setStyleSheet(f'''
        QWidget {{color:{c['text']};font-family:"{family}";font-size:{base}pt;}}
        QWidget#shell,QStackedWidget {{background:transparent;}}
        QFrame#sidebar {{background:{c['side']};border:0;border-right:1px solid {c['border']};}}
        QWidget#workspace {{background:transparent;}}
        QFrame#tableCard,QFrame#deviceHero {{background:{panel_bg};border:1px solid {c['border']};border-radius:13px;}}
        QFrame#deviceHero {{border-radius:14px;}}
        QFrame#settingsMenu {{background:{c['side']};border:1px solid {c['border']};border-radius:12px;}}
        QScrollArea#settingsScroll,QScrollArea#settingsScroll > QWidget {{background:transparent;border:0;}}
        QLabel#brand {{font-size:{base+1}pt;font-weight:700;}}
        QLabel#title {{font-size:{base+8}pt;font-weight:600;}}
        QLabel#cardTitle {{font-size:{base+1}pt;font-weight:600;}}
        QLabel#deviceName {{font-size:{base+2}pt;font-weight:600;}}
        QLabel#deviceMetric {{font-weight:600;}}
        QLabel#metric {{font-size:{base+3}pt;font-weight:600;}}
        QLabel#muted,QLabel#metadata,QLabel#heroDescription {{color:{c['muted']};}}
        QLabel#checkState[passed="true"] {{color:{'#63d489' if dark else '#2b7b42'};}}
        QLabel#checkState[failed="true"] {{color:{'#ffbc7f' if dark else '#a53e00'};}}
        QLabel#small,QLabel#section {{font-size:{base-.5}pt;color:{c['muted']};}}
        QLabel#section {{font-weight:600;}}
        QLabel#connectionDot {{color:#969696;}}
        QLabel#connectionDot[connected="true"] {{color:{'#49d46b' if dark else '#2b9b4a'};}}
        QFrame#connectionPill,QLabel#statusPill {{background:{c['button']};border:1px solid {c['border']};border-radius:10px;}}
        QLabel#statusPill {{padding:8px 12px;}}
        QLabel#statusPill[connected="true"] {{color:{'#68df8a' if dark else '#25763c'};}}
        QLabel#deviceSymbol {{background:{c['selected']};border-radius:10px;}}
        QPushButton {{background:{c['button']};border:1px solid {c['border']};border-radius:9px;padding:6px 13px;font-weight:500;}}
        QPushButton:hover {{background:{c['hover']};}}
        QPushButton:pressed {{background:{c['selected']};}}
        QPushButton:focus {{border:2px solid {c['orange']};}}
        QPushButton#primary {{background:{c['orange']};color:{c['primaryText']};font-weight:600;border:1px solid {c['orange']};}}
        QPushButton#primary:hover {{background:{c['primaryHover']};}}
        QPushButton#secondaryAccent {{background:{'#245e61' if dark else '#276a6d'};color:#ffffff;}}
        QPushButton#destructive {{color:{'#ffb47d' if dark else '#a53c00'};}}
        QPushButton:disabled,QPushButton#primary:disabled {{background:{c['bg']};color:{c['muted']};border:1px solid {c['border']};}}
        QPushButton#nav,QPushButton#settingsNav {{background:transparent;border:1px solid transparent;text-align:left;padding:8px 12px;}}
        QPushButton#nav:checked {{background:{c['nav']};border:1px solid {c['navBorder']};color:#ffffff;font-weight:600;}}
        QPushButton#settingsNav:checked {{background:{c['selected']};font-weight:600;}}
        QPushButton#nav:hover,QPushButton#settingsNav:hover {{border-color:{c['border']};}}
        QPushButton[themeCard="true"] {{background:{c['bg']};border-radius:12px;padding:0;}}
        QPushButton[themeCard="true"]:checked {{border:2px solid {c['orange']};}}
        QLabel#formatChip {{background:{c['selected']};border-radius:7px;padding:5px 7px;font-size:{base-1}pt;font-weight:600;}}
        QFrame#importDrop {{background:{c['card'] if reduced else ('#122c30' if dark else '#fff7ef')};border:1px dashed {c['border'] if dark else '#e9b997'};border-radius:14px;}}
        QTableView,QTableWidget {{background:{c['card']};alternate-background-color:{c['alternate']};border:1px solid {c['border']};border-radius:10px;selection-background-color:{c['selected']};selection-color:{c['text']};outline:0;}}
        QTableView::item,QTableWidget::item {{padding:5px 7px;border-bottom:1px solid {c['border']};}}
        QTableView::item:selected,QTableWidget::item:selected {{background:{c['selected']};}}
        QTableView::item:hover,QTableWidget::item:hover {{background:{c['hover']};}}
        QHeaderView,QTableCornerButton::section {{background:{c['card']};border:0;}}
        QHeaderView::section {{background:{c['card']};color:{c['muted']};padding:8px 6px;border:0;border-bottom:1px solid {c['border']};font-size:{base-.5}pt;font-weight:600;}}
        QLineEdit,QComboBox {{background:{c['button']};border:1px solid {c['border']};border-radius:9px;padding:7px 11px;selection-background-color:{c['selected']};}}
        QLineEdit:focus,QComboBox:focus {{border:1px solid {c['orange']};}}
        QComboBox {{padding-right:30px;min-height:22px;}}
        QComboBox::drop-down {{subcontrol-origin:padding;subcontrol-position:top right;width:28px;border:0;background:transparent;}}
        QComboBox::down-arrow {{image:url("{chevron}");width:16px;height:16px;}}
        QFrame#comboPopup {{background:{c['card']};border:0;border-radius:9px;}}
        QComboBox QAbstractItemView {{background:{c['card']};color:{c['text']};border:1px solid {c['border']};border-radius:9px;padding:5px;outline:0;selection-background-color:{c['selected']};selection-color:{c['text']};}}
        QComboBox QAbstractItemView::item {{min-height:30px;padding:3px 10px;border-radius:6px;}}
        QComboBox QAbstractItemView::item:hover {{background:{c['hover']};}}
        QComboBox QAbstractItemView::item:selected {{background:{c['selected']};color:{c['text']};}}
        QDialog,QMessageBox {{background:{c['bg']};}}
        QMenu {{background:{c['card']};border:1px solid {c['border']};border-radius:9px;padding:5px;}}
        QMenu::item {{padding:7px 18px;border-radius:6px;}}
        QMenu::item:selected {{background:{c['selected']};}}
        QToolTip {{background:{c['card']};color:{c['text']};border:1px solid {c['border']};padding:6px;border-radius:6px;}}
        QPlainTextEdit {{background:{c['card']};color:{c['text']};border:1px solid {c['border']};border-radius:9px;padding:8px;}}
        QTableView::indicator,QTableWidget::indicator {{width:15px;height:15px;border:1px solid {c['muted']};border-radius:4px;background:{c['card']};}}
        QTableView::indicator:checked,QTableWidget::indicator:checked {{background:{c['orange']};border-color:{c['orange']};image:url("{check}");}}
        QCheckBox {{spacing:8px;padding:4px 0;}}
        QCheckBox::indicator {{width:16px;height:16px;border:1px solid {c['muted']};border-radius:4px;background:{c['card']};}}
        QCheckBox::indicator:checked {{background:{c['orange']};border-color:{c['orange']};image:url("{check}");}}
        QCheckBox::indicator:indeterminate {{background:{c['selected']};border-color:{c['orange']};}}
        QFrame#activityBar {{background:{c['side']};border-top:1px solid {c['border']};}}
        QProgressBar {{background:{c['border']};border:0;border-radius:4px;}}
        QProgressBar::chunk {{background:{c['orange']};border-radius:4px;}}
        QFrame#hero,QFrame#propertiesCard {{background:{c['card']};border:1px solid {c['border']};border-radius:12px;}}
        QLabel#inspectorTitle {{font-size:{base+5}pt;font-weight:600;}}
        QLabel#cover {{background:{c['selected']};border-radius:12px;font-size:32pt;}}
        QScrollArea#inspector,QScrollArea#inspector > QWidget > QWidget {{background:{c['bg']};border:0;}}
        QFrame#emptyState {{background:{c['card']};border:0;border-radius:12px;}}
        QLabel#emptyTitle {{font-size:{base+3}pt;font-weight:600;}}
        QLabel#emptySymbol {{font-size:26pt;color:{c['orange']};}}
        QFrame#dropVeil {{background:{c['bg']};border:2px dashed {c['orange']};border-radius:16px;}}
        QListWidget {{background:{c['card']};border:1px solid {c['border']};border-radius:8px;}}
        QScrollBar:vertical {{background:transparent;width:10px;margin:0;}}
        QScrollBar::handle:vertical {{background:{c['border']};min-height:28px;border-radius:5px;}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
        QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:transparent;}}
        QScrollBar:horizontal {{background:transparent;height:10px;margin:0;}}
        QScrollBar::handle:horizontal {{background:{c['border']};min-width:28px;border-radius:5px;}}
        QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal {{width:0;}}
        QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal {{background:transparent;}}
        QSplitter::handle {{background:{c['border']};height:1px;width:1px;}}
    ''')
    for value in window.findChildren(QPushButton):
        if isinstance(value,MotionButton):value.tone=QColor(c['orange'])
        kind=value.property('iconKind')
        if kind:
            color=c['primaryText'] if value.objectName()=='primary' else '#ffffff' if value.objectName()=='secondaryAccent' or value.objectName()=='nav' and value.isChecked() else c['text']
            value.setIcon(line_icon(kind,color,18))
    window.device_symbol.setPixmap(line_icon('phone','#a6d7d5' if dark else '#18565a',32).pixmap(32,32))
    window.diagnostic_symbol.setPixmap(line_icon('phone','#a6d7d5' if dark else '#18565a',54).pixmap(54,72))
    window.drop_symbol.setPixmap(line_icon('upload',c['orange'],38).pixmap(38,38))
    for table in (window.library_table,window.table):table.setProperty('checkAccent',c['orange']);table.setProperty('checkForeground',c['primaryText'])
    window.default_music_icon=line_icon('music',c['muted'],28);window.library_model.default_icon=window.default_music_icon
    if window.library_model.rowCount():window.library_model.dataChanged.emit(window.library_model.index(0,0),window.library_model.index(window.library_model.rowCount()-1,0),[Qt.ItemDataRole.DecorationRole])
    window.theme_options[selection].setChecked(True);window.theme_dark=dark
    fit_controls(window);window.paint_transfer_stages()


def fit_controls(window):
    for control in window.findChildren(QPushButton):
        if not control.text():continue
        metrics=QFontMetrics(control.font())
        control.setMinimumWidth(metrics.horizontalAdvance(control.text())+(48 if control.property('iconKind') else 30))
    window.sidebar.setFixedWidth(max(180,max(nav.minimumWidth() for nav in window.nav_buttons)+28))
    window.settings_menu.setFixedWidth(max(176,max(nav.minimumWidth() for nav in window.settings_buttons)+20))

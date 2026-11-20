"""Native teal/orange desktop composition shared by light and dark appearances."""
from pathlib import Path
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QColor,QPalette,QFont,QFontMetrics,QPainter,QPixmap,QPen
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QButtonGroup,QStackedWidget,
    QGridLayout,QHeaderView,QTableView,QSplitter,QAbstractItemView,QProgressBar,QApplication,
    QScrollArea,QDialog,QSizePolicy)
from .models import LibraryModel,SelectionDelegate,FormatBadgeDelegate,StatusBadgeDelegate
from .visuals import app_icon,line_icon,music_placeholder_icon
from .surfaces import Atmosphere
from .motion import MotionButton,CoverView
from .i18n import tr,QLabel,QPushButton,QCheckBox,QComboBox,QLineEdit,QTableWidget,QListWidget


def button(text,kind=None,handler=None):
    value=MotionButton(tr(text));value.setIconSize(QSize(17,17))
    if kind:value.setProperty('iconKind',kind)
    if handler:value.clicked.connect(handler)
    value.setMinimumHeight(34)
    value.setMinimumWidth(QFontMetrics(value.font()).horizontalAdvance(str(value.text()))+(44 if kind else 28))
    return value


def text_label(text,role=None,wrap=False):
    value=QLabel(tr(text));value.setTextFormat(Qt.TextFormat.PlainText);value.setWordWrap(wrap)
    if role:value.setObjectName(role)
    return value


def panel(title=None,description=None):
    value=QFrame();value.setObjectName('tableCard');layout=QVBoxLayout(value)
    layout.setContentsMargins(18,16,18,16);layout.setSpacing(10)
    if title:layout.addWidget(text_label(title,'cardTitle'))
    if description:layout.addWidget(text_label(description,'muted',True))
    return value,layout


def page(title,description=None):
    value=QWidget();value.setObjectName('workspace');layout=QVBoxLayout(value)
    layout.setContentsMargins(24,18,24,14);layout.setSpacing(12)
    header=QHBoxLayout();header.setSpacing(10);heading=text_label(title,'title');header.addWidget(heading);header.addStretch()
    layout.addLayout(header)
    if description:layout.addWidget(text_label(description,'muted',True))
    return value,layout,header,heading


def _paint_theme_preview(painter,dark):
    painter.setPen(QPen(QColor('#527172' if dark else '#d4deda'),.8));painter.setBrush(QColor('#102326' if dark else '#fbfaf8'));painter.drawRoundedRect(1,1,104,56,6,6)
    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#233c3e' if dark else '#eeeae4'));painter.drawRoundedRect(3,3,23,52,4,4)
    painter.setBrush(QColor('#1d484c' if dark else '#246266'));painter.drawRoundedRect(5,17,19,7,2,2)
    painter.setBrush(QColor('#ed751c'));painter.drawRoundedRect(5,17,2.5,7,1,1)
    painter.setBrush(QColor('#345657' if dark else '#e4eeeb'));painter.drawRoundedRect(30,8,69,14,3,3)
    painter.setBrush(QColor('#ed751c'));painter.drawRoundedRect(31,27,20,6,2,2)
    painter.setPen(QPen(QColor('#466263' if dark else '#d8e2de'),1))
    for y in (38,44,50):painter.drawLine(31,y,97,y)


def theme_thumbnail(mode):
    image=QPixmap(212,116);image.setDevicePixelRatio(2);image.fill(Qt.GlobalColor.transparent)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if mode=='system':
        painter.save();painter.setClipRect(0,0,53,58);_paint_theme_preview(painter,False);painter.restore()
        painter.save();painter.setClipRect(53,0,53,58);_paint_theme_preview(painter,True);painter.restore()
        painter.setPen(QPen(QColor('#6c898a'),.9));painter.drawLine(53,2,53,56)
    else:
        _paint_theme_preview(painter,mode=='dark' or mode is True)
    painter.end();return image


def build(window):
    root=Atmosphere();window.scene=root;window.setCentralWidget(root)
    shell=QVBoxLayout(root);window.shell_layout=shell;shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
    outer=QHBoxLayout();window.top_layout=outer;outer.setSpacing(0);outer.setContentsMargins(0,0,0,0);shell.addLayout(outer,1)
    sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(180);window.sidebar=sidebar
    side=QVBoxLayout(sidebar);side.setContentsMargins(14,22,14,16);side.setSpacing(6)
    brand_row=QHBoxLayout();brand_row.setSpacing(10);mark=QLabel();mark.setPixmap(app_icon().pixmap(32,32));brand_row.addWidget(mark)
    brand=text_label('TUPAQ','brand');brand_row.addWidget(brand);brand_row.addStretch();side.addLayout(brand_row);side.addSpacing(22)
    window.navigation=QButtonGroup(window);window.nav_buttons=[None]*5
    # Keep stable page identities for saved/controller references; order matches the design.
    for index,text,kind in [(0,'Biblioteca','library'),(2,'Importar','upload'),(4,'Archivos de apps','folder'),(3,'Diagnóstico','pulse'),(1,'Preferencias','settings')]:
        value=button(text,kind);value.setObjectName('nav');value.setCheckable(True);value.setMinimumHeight(40)
        window.navigation.addButton(value,index);window.nav_buttons[index]=value;side.addWidget(value)
    side.addStretch()
    footer=QFrame();footer.setObjectName('sidebarFooter');footer_layout=QHBoxLayout(footer);footer_layout.setContentsMargins(8,6,8,6);footer_layout.setSpacing(7)
    window.sidebar_dot=text_label('●','connectionDot');window.sidebar_dot.setProperty('connected',False);footer_layout.addWidget(window.sidebar_dot)
    window.sidebar_connection=text_label('Sin conexión USB','small');footer_layout.addWidget(window.sidebar_connection,1);side.addWidget(footer)
    outer.addWidget(sidebar)
    window.pages=QStackedWidget();outer.addWidget(window.pages,1)

    workspace,layout,toolbar,window.heading=page('Biblioteca');window.local_tools=workspace
    # Compact inline device status pill next to the Library title (replaces tall hero card).
    window.device_hero=QFrame();window.device_hero.setObjectName('devicePill')
    hero=QHBoxLayout(window.device_hero);hero.setContentsMargins(11,5,11,5);hero.setSpacing(7)
    window.device_symbol=QLabel(window.device_hero);window.device_symbol.hide()
    window.connection_dot=text_label('●','connectionDot');window.connection_dot.setProperty('connected',False);hero.addWidget(window.connection_dot)
    window.device_name=text_label('iPhone','devicePillName');hero.addWidget(window.device_name)
    hero.addWidget(text_label('·','muted'))
    window.device_metric=text_label('Tu biblioteca por USB','small');hero.addWidget(window.device_metric)
    window.connection_badge=text_label('Sin conexión USB','muted');window.connection_badge.setParent(window.device_hero);window.connection_badge.hide()
    toolbar.insertWidget(1,window.device_hero,0,Qt.AlignmentFlag.AlignVCenter)
    window.device_button=button('','phone',window.check_device);window.device_button.setFixedWidth(34);window.device_button.setToolTip(tr('Comprobar USB'))
    window.library_button=button('','refresh',window.load_library);window.library_button.setFixedWidth(34);window.library_button.setToolTip(tr('Volver a leer la biblioteca y comprobar sus archivos'))
    toolbar.insertWidget(2,window.device_button,0,Qt.AlignmentFlag.AlignVCenter)
    toolbar.insertWidget(3,window.library_button,0,Qt.AlignmentFlag.AlignVCenter)
    window.choose=button('Añadir canciones','plus',window.choose_files);window.choose.setObjectName('primary')
    window.import_phone=button('Importar','upload',window.import_songs)
    window.import_phone.setToolTip(tr('Enviar la selección de la cola del ordenador; sin selección, enviar toda la cola.'))
    window.export_phone=button('Exportar','download',window.export_songs)
    window.export_phone.setToolTip(tr('Exportar al ordenador las canciones seleccionadas del iPhone.'))
    window.inspector_toggle=button('Detalles','info');window.inspector_toggle.setCheckable(True)
    window.transfer_actions=QHBoxLayout();window.transfer_actions.setSpacing(8);window.transfer_actions.setContentsMargins(0,0,0,0)
    layout_transfer_actions(window)
    toolbar.addLayout(window.transfer_actions)
    toolbar.addWidget(window.inspector_toggle)
    window.update_banner=QFrame();window.update_banner.setObjectName('updateBanner')
    banner_row=QHBoxLayout(window.update_banner);banner_row.setContentsMargins(14,8,14,8);banner_row.setSpacing(10)
    window.update_banner_label=text_label('Nueva versión disponible','deviceMetric');banner_row.addWidget(window.update_banner_label,1)
    window.update_banner_open=button('Descargar actualización','download',window.open_update_release);window.update_banner_open.setObjectName('primary');banner_row.addWidget(window.update_banner_open)
    banner_close=button('','close',window.update_banner.hide);banner_close.setFixedWidth(34);banner_row.addWidget(banner_close)
    window.update_banner.hide();layout.addWidget(window.update_banner)
    window.device_status=text_label('Conecta tu iPhone para mostrar su música.','muted',True);window.device_status.setMaximumHeight(54);window.device_status.hide();layout.addWidget(window.device_status)
    # Unified single-row explore toolbar: segmented view pill + search + filters + playlists.
    explore_row=QHBoxLayout();explore_row.setSpacing(10)
    seg_bar=QFrame();seg_bar.setObjectName('segmentBar')
    seg_layout=QHBoxLayout(seg_bar);seg_layout.setContentsMargins(3,3,3,3);seg_layout.setSpacing(2)
    window.view_mode_group=QButtonGroup(window);window.view_mode_buttons=[]
    for idx,label in enumerate(('Canciones','Álbumes','Artistas')):
        seg=button(label);seg.setObjectName('segment');seg.setCheckable(True);seg.setMinimumHeight(28)
        window.view_mode_group.addButton(seg,idx);window.view_mode_buttons.append(seg);seg_layout.addWidget(seg)
    window.view_mode_buttons[0].setChecked(True)
    explore_row.addWidget(seg_bar)
    window.search=QLineEdit();window.search.setPlaceholderText(tr('Buscar canción, artista, álbum o formato (.m4a, .mp3…)'));window.search.setClearButtonEnabled(True);window.search.setMinimumHeight(36)
    explore_row.addWidget(window.search,1)
    window.format_filter=QComboBox();window.format_filter.addItems(['Todos los formatos','M4A','MP3','AAC','ALAC','WAV','AIFF']);explore_row.addWidget(window.format_filter)
    window.content_filter=QComboBox();window.content_filter.addItems(['Toda la música','Con carátula','Con letra','Posibles duplicados']);explore_row.addWidget(window.content_filter)
    window.playlist_filter=QComboBox();window.playlist_filter.addItem(str(tr('Todas las playlists')),'');window.playlist_filter.setMinimumWidth(160);window.playlist_filter.hide()
    explore_row.addWidget(window.playlist_filter)
    layout.addLayout(explore_row)
    window.main_splitter=QSplitter(Qt.Orientation.Vertical)
    window.library_panel=QFrame();window.library_panel.setObjectName('libraryCard');phone_layout=QVBoxLayout(window.library_panel);phone_layout.setContentsMargins(0,0,0,0);phone_layout.setSpacing(0)
    window.library_views=QStackedWidget()
    window.library_model=LibraryModel(window);window.library_table=QTableView();window.library_table.setModel(window.library_model);window.library_table.setItemDelegateForColumn(0,SelectionDelegate(window.library_table));window.library_table.setItemDelegateForColumn(3,FormatBadgeDelegate(window.library_table));window.library_views.addWidget(window.library_table)
    from .album_grid import CollectionGridView
    window.collection_grid=CollectionGridView(window);window.library_views.addWidget(window.collection_grid)
    phone_layout.addWidget(window.library_views)
    from .presentation import LibraryEmptyState
    window.library_empty=LibraryEmptyState(window.library_table,window)
    window.main_splitter.addWidget(window.library_panel);window.main_splitter.setChildrenCollapsible(False);layout.addWidget(window.main_splitter,1)
    collection=QHBoxLayout();collection.setSpacing(12)
    window.library_heading=text_label('En el iPhone','muted');window.selection_count=text_label('','muted');collection.addWidget(window.library_heading);collection.addWidget(window.selection_count);collection.addStretch()
    window.delete_phone=button('Eliminar','trash',window.delete_songs);window.delete_phone.setObjectName('destructive')
    window.delete_phone.setToolTip(tr('Eliminar de Música las canciones marcadas; pide confirmación.'));collection.addWidget(window.delete_phone)
    window.select_visible=QCheckBox(tr('Seleccionar todo'));window.select_visible.setToolTip(tr('Marcar o desmarcar todas las canciones de la lista actual.'));window.select_visible.setTristate(True);collection.addWidget(window.select_visible);layout.addLayout(collection)
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
        preview=QLabel();preview.setAlignment(Qt.AlignmentFlag.AlignCenter);preview.setPixmap(theme_thumbnail('dark' if index==2 else 'light' if index==1 else 'system'));inner.addWidget(preview)
        caption=text_label(title);caption.setAlignment(Qt.AlignmentFlag.AlignCenter);inner.addWidget(caption)
        for child in (preview,caption):child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        window.theme_group.addButton(option,index);theme_row.addWidget(option,1);window.theme_options[index]=option
    window.theme_group.idClicked.connect(window.theme_choice.setCurrentIndex);appearance.addLayout(theme_row)
    window.use_accent=QCheckBox(tr('Usar el color naranja de TUPAQ'));window.use_accent.setChecked(True);appearance.addWidget(window.use_accent)
    window.reduce_transparency=QCheckBox(tr('Reducir transparencia'));appearance.addWidget(window.reduce_transparency)
    window.reduce_motion=QCheckBox(tr('Reducir movimiento'));window.reduce_motion.setChecked(not window.motion.enabled);appearance.addWidget(window.reduce_motion)
    window.reduce_motion.toggled.connect(window.change_motion)
    window.use_accent.toggled.connect(window.change_visual_options);window.reduce_transparency.toggled.connect(window.change_visual_options)
    paths.addWidget(text_label('Carpeta inicial para elegir y exportar música.','muted',True))
    window.library_path=QLineEdit();window.library_path.setReadOnly(True);paths.addWidget(window.library_path)
    paths.addWidget(button('Cambiar carpeta…','folder',window.choose_library_path))
    paths.addWidget(text_label('Organización al exportar canciones del iPhone.','muted',True))
    window.export_structure=QComboBox();window.export_structure.addItems(['Todo en la misma carpeta','Organizar por Artista / Álbum']);paths.addWidget(window.export_structure)
    window.export_incremental=QCheckBox(tr('Modo respaldo incremental (omitir archivos ya exportados)'));paths.addWidget(window.export_incremental)
    paths.addWidget(text_label('Evita duplicados (2) al volver a exportar a la misma carpeta. Al filtrar una playlist también guarda su archivo .m3u8.','muted',True))
    metadata.addWidget(text_label('Se aplica a los próximos envíos. Los archivos originales se conservan.','muted',True))
    window.import_lyrics=QCheckBox(tr('Importar las letras incrustadas en las canciones'));window.import_lyrics.setChecked(True);metadata.addWidget(window.import_lyrics)
    metadata.addWidget(text_label('Envía la letra de texto a Música con las canciones nuevas. No descarga letras ni activa karaoke.','muted',True))
    window.metadata_choice=QComboBox();window.metadata_choice.addItems(['Conservar metadatos (recomendado)','Usar nombre de archivo como título']);metadata.addWidget(window.metadata_choice)
    window.convert_audio=QCheckBox(tr('Convertir FLAC y otros formatos automáticamente al importar'));metadata.addWidget(window.convert_audio)
    window.convert_codec=QComboBox();window.convert_codec.addItems(['ALAC · sin pérdida (M4A)','AAC · 256 kbps (M4A)']);metadata.addWidget(window.convert_codec)
    ffmpeg_row=QHBoxLayout();ffmpeg_row.setSpacing(8)
    window.ffmpeg_path=QLineEdit();window.ffmpeg_path.setPlaceholderText(tr('Detección automática de ffmpeg'));ffmpeg_row.addWidget(window.ffmpeg_path,1)
    ffmpeg_row.addWidget(button('Elegir ffmpeg…','folder',window.choose_ffmpeg_path))
    metadata.addLayout(ffmpeg_row)
    metadata.addWidget(text_label('Convierte FLAC, OGG, Opus o WMA en una copia temporal conservando metadatos, portada y letra. Tus originales nunca se modifican.','muted',True))
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
    window.auto_check_updates=QCheckBox(tr('Comprobar si hay nuevas versiones al abrir TUPAQ'));window.auto_check_updates.setChecked(True);sync.addWidget(window.auto_check_updates)
    update_row=QHBoxLayout();update_row.setSpacing(10)
    window.check_updates_button=button('Buscar actualizaciones','refresh',window.check_updates);update_row.addWidget(window.check_updates_button)
    window.open_update_button=button('Abrir descarga en GitHub','download',window.open_update_release);window.open_update_button.setObjectName('primary');window.open_update_button.hide();update_row.addWidget(window.open_update_button)
    update_row.addStretch();sync.addLayout(update_row)
    window.update_status_label=text_label('Solo avisa con el enlace oficial de GitHub Releases; nunca descarga ejecutables automáticamente.','muted',True);sync.addWidget(window.update_status_label)
    settings_scroll=QScrollArea();settings_scroll.setObjectName('settingsScroll');settings_scroll.setWidgetResizable(True);settings_scroll.setFrameShape(QFrame.Shape.NoFrame);settings_scroll.setWidget(settings);window.pages.addWidget(settings_scroll)

    import_page,import_layout,import_header,_=page('Importar','Añade música a la biblioteca de tu iPhone.')
    history_button=button('Historial','history',window.open_history);import_header.addWidget(history_button)
    top=QHBoxLayout();top.setSpacing(14)
    drop,drop_layout=panel();drop.setObjectName('importDrop');drop_layout.setContentsMargins(20,18,20,18);drop_layout.setSpacing(8)
    window.drop_symbol=QLabel();window.drop_symbol.setAlignment(Qt.AlignmentFlag.AlignCenter);drop_layout.addWidget(window.drop_symbol)
    title=text_label('Arrastra archivos o carpetas de música aquí','cardTitle',True);title.setAlignment(Qt.AlignmentFlag.AlignCenter);drop_layout.addWidget(title)
    note=text_label('O elige una opción para preparar tus canciones.','muted',True);note.setAlignment(Qt.AlignmentFlag.AlignCenter);drop_layout.addWidget(note)
    choices=QHBoxLayout();choices.setSpacing(8)
    window.import_choose=button('Elegir archivos…','file',window.choose_files);window.import_choose.setObjectName('primary')
    window.folder_choose=button('Elegir carpeta…','folder',window.choose_folder);choices.addStretch();choices.addWidget(window.import_choose);choices.addWidget(window.folder_choose);choices.addStretch();drop_layout.addLayout(choices);top.addWidget(drop,1)
    formats,formats_layout=panel('Formatos compatibles');window.formats_card=formats;formats.setFixedWidth(256)
    chips=QGridLayout();chips.setSpacing(6)
    for i,text in enumerate(('M4A','MP3','AAC','ALAC','WAV','AIFF')):
        chip=text_label(text,'formatChip');chip.setAlignment(Qt.AlignmentFlag.AlignCenter);chips.addWidget(chip,i//3,i%3)
    formats_layout.addLayout(chips);formats_layout.addWidget(text_label('AAC y ALAC dentro de M4A. Los originales se conservan.','muted',True));formats_layout.addStretch();top.addWidget(formats);import_layout.addLayout(top)
    bottom=QHBoxLayout();bottom.setSpacing(14)
    window.queue_panel,queue_layout=panel();queue_layout.setContentsMargins(14,14,14,14)
    queue_header=QHBoxLayout();queue_header.setSpacing(8);queue_header.addWidget(text_label('Cola de importación','cardTitle'),1)
    window.queue_toggle=button('Cola','library');window.queue_toggle.setCheckable(True);window.queue_toggle.setChecked(True)
    window.edit_metadata=button('Editar','tag',window.edit_selected_metadata)
    window.edit_metadata.setToolTip(tr('Editar metadatos y portada de la canción seleccionada antes de importar.'))
    window.remove_duplicates=button('Quitar repetidas','close',window.remove_duplicate_tracks)
    window.remove_duplicates.setToolTip(tr('Quitar de la cola las canciones que ya existen en el iPhone.'))
    window.remove_duplicates.hide()
    window.remove=button('Quitar','trash',window.remove_selection);window.clear=button('Vaciar','close',window.clear_tracks);window.export=button('CSV','folder',window.choose_export)
    for value in (window.edit_metadata,window.remove_duplicates,window.remove,window.clear,window.export):queue_header.addWidget(value)
    queue_layout.addLayout(queue_header)
    window.table=QTableWidget(0,7);window.table.setHorizontalHeaderLabels(['Canción','Artista','Álbum','Formato','Duración','Tamaño','Estado']);window.table.setItemDelegateForColumn(0,SelectionDelegate(window.table));window.table.setItemDelegateForColumn(3,FormatBadgeDelegate(window.table));window.table.setItemDelegateForColumn(6,StatusBadgeDelegate(window.table));queue_layout.addWidget(window.table,1)
    for col,align in ((0,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter),(1,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter),(2,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter),(3,Qt.AlignmentFlag.AlignCenter),(4,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter),(5,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter),(6,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)):
        item=window.table.horizontalHeaderItem(col)
        if item is not None:item.setTextAlignment(align)
    window.table.setColumnHidden(1,True);window.table.setColumnHidden(2,True)
    bottom.addWidget(window.queue_panel,1)
    queue_summary,summary_layout=panel('Sincronización');window.queue_summary_card=queue_summary;queue_summary.setFixedWidth(256)
    window.queue_summary=text_label('Sin canciones para importar.','muted',True);summary_layout.addWidget(window.queue_summary)
    window.import_submit=button('Importar al iPhone','upload',window.import_songs);window.import_submit.setObjectName('primary');summary_layout.addWidget(window.import_submit)
    window.import_progress=QProgressBar();window.import_progress.setRange(0,100);window.import_progress.setTextVisible(False);window.import_progress.setFixedHeight(7);window.import_progress.hide();summary_layout.addWidget(window.import_progress)
    window.transfer_stage=text_label('Selecciona canciones para preparar la importación.','muted',True);summary_layout.addWidget(window.transfer_stage)
    window.stage_labels=[]
    for title in ('Preparación','Transferencia','Comprobación'):
        stage=text_label(title,'muted');window.stage_labels.append(stage);summary_layout.addWidget(stage)
    summary_layout.addStretch()
    bottom.addWidget(queue_summary);import_layout.addLayout(bottom,1);window.pages.addWidget(import_page)
    window.queue_toggle.setParent(import_page);window.queue_toggle.hide()

    # Compact 2x2 Diagnostics layout: inline device identity + 2x2 cards + visible footer without clipping.
    diagnostics,diagnostics_layout,diagnostic_header,_=page('Diagnóstico')
    window.diagnostic_refresh=button('Actualizar','refresh',window.refresh_device_details);diagnostic_header.addWidget(window.diagnostic_refresh)
    window.diagnostic_run=button('Comprobar lectura de audios','pulse',window.run_diagnostics);window.diagnostic_run.setObjectName('secondaryAccent');diagnostic_header.addWidget(window.diagnostic_run)
    diag_meta=QHBoxLayout();diag_meta.setSpacing(10)
    window.diagnostic_symbol=QLabel(diagnostics);window.diagnostic_symbol.hide()
    window.diagnostic_name=text_label('iPhone','deviceMetric');diag_meta.addWidget(window.diagnostic_name)
    diag_meta.addWidget(text_label('·','muted'))
    window.diagnostic_model=text_label('Información pendiente de lectura.','muted');diag_meta.addWidget(window.diagnostic_model)
    window.diagnostic_state=text_label('Sin conexión USB','statusPill');window.diagnostic_state.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed);diag_meta.addWidget(window.diagnostic_state)
    diag_meta.addStretch()
    diagnostics_layout.addLayout(diag_meta)
    grid=QGridLayout();grid.setSpacing(14);grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);window.diagnostic_fields={};window.health_fields={}
    storage,storage_layout=panel('Almacenamiento (datos)','Última lectura del volumen de datos del dispositivo.')
    window.diagnostic_fields['storage']=text_label('Pendiente','metric');storage_layout.addWidget(window.diagnostic_fields['storage'])
    window.storage_bar=QProgressBar();window.storage_bar.setRange(0,1000);window.storage_bar.setTextVisible(False);window.storage_bar.setFixedHeight(8);window.storage_bar.hide();storage_layout.addWidget(window.storage_bar)
    window.diagnostic_fields['library']=text_label('Pendiente','muted');storage_layout.addWidget(window.diagnostic_fields['library']);storage_layout.addStretch();grid.addWidget(storage,0,0)
    battery,battery_layout=panel('Batería','Salud real, ciclos, temperatura y voltaje reportados por iOS.')
    window.diagnostic_fields['battery_health']=text_label('Pendiente','metric');battery_layout.addWidget(window.diagnostic_fields['battery_health'])
    window.battery_bar=QProgressBar();window.battery_bar.setObjectName('batteryBar');window.battery_bar.setRange(0,1000);window.battery_bar.setTextVisible(False);window.battery_bar.setFixedHeight(8);window.battery_bar.hide();battery_layout.addWidget(window.battery_bar)
    window.diagnostic_fields['battery_detail']=text_label('Conecta el iPhone para consultar la telemetría de batería por USB.','muted',True);battery_layout.addWidget(window.diagnostic_fields['battery_detail']);battery_layout.addStretch();grid.addWidget(battery,0,1)
    checks,checks_layout=panel('Comprobaciones');checks_grid=QGridLayout();checks_grid.setVerticalSpacing(10)
    for row,(key,title) in enumerate([('connection','Conexión del dispositivo'),('database','Base de datos'),('permissions','Permisos del catálogo'),('integrity','Integridad con recibos')]):
        checks_grid.addWidget(text_label(title,'muted'),row,0);value=text_label('Pendiente','checkState');value.setAlignment(Qt.AlignmentFlag.AlignCenter);value.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed);checks_grid.addWidget(value,row,1,Qt.AlignmentFlag.AlignRight);window.health_fields[key]=value
    checks_grid.setColumnStretch(0,1);checks_layout.addLayout(checks_grid);checks_layout.addStretch();grid.addWidget(checks,1,0)
    usb,usb_layout=panel('Conexión USB','Detección y acceso al dispositivo.')
    window.diagnostic_fields['connection']=text_label('Sin conexión USB','metric');usb_layout.addWidget(window.diagnostic_fields['connection'])
    window.diagnostic_fields['connection_detail']=text_label('Conecta el iPhone y desbloquéalo para leer el catálogo.','muted',True);usb_layout.addWidget(window.diagnostic_fields['connection_detail'])
    window.diagnostic_fields['formats']=text_label('Formatos admitidos','small');usb_layout.addWidget(window.diagnostic_fields['formats'])
    usb_layout.addWidget(text_label('MP3 · WAV · M4A (AAC/ALAC) · AIFF','muted',True))
    window.diagnostic_fields['files']=text_label('Pendiente','small',True);usb_layout.addWidget(window.diagnostic_fields['files']);usb_layout.addStretch();grid.addWidget(usb,1,1)
    diagnostics_layout.addLayout(grid)
    diag_footer=QHBoxLayout();diag_footer.setSpacing(12)
    window.copy_diagnostic=button('Copiar diagnóstico','copy');window.last_diagnostic='';window.copy_diagnostic.setEnabled(False);window.copy_diagnostic.clicked.connect(lambda:QApplication.clipboard().setText(window.last_diagnostic));diag_footer.addWidget(window.copy_diagnostic)
    diag_footer.addStretch()
    window.advanced=QCheckBox(tr('Mostrar opciones avanzadas de recuperación'));diag_footer.addWidget(window.advanced)
    diagnostics_layout.addLayout(diag_footer)
    window.diagnostic_note=text_label('Comprobación opcional: lee los audios completos y puede tardar. No modifica el iPhone y no es necesaria para importar.','muted',True);diagnostics_layout.addWidget(window.diagnostic_note)
    maintenance=QFrame();maintenance.setObjectName('tableCard');maintenance_layout=QVBoxLayout(maintenance);maintenance_layout.setContentsMargins(18,16,18,16)
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

    apps_page,apps_layout,apps_header,_=page('Archivos de apps','Agrega, exporta o elimina archivos dentro de la carpeta Documentos de apps compatibles.')
    window.apps_refresh=button('Actualizar','refresh',window.load_apps)
    window.apps_refresh.setToolTip(tr('Leer las apps compatibles instaladas en el iPhone'))
    apps_header.addWidget(window.apps_refresh)
    apps_bar,apps_bar_layout=panel();apps_bar_layout.setContentsMargins(16,14,16,14);apps_bar_layout.setSpacing(12)
    selector_row=QHBoxLayout();selector_row.setSpacing(10)
    selector_row.addWidget(text_label('Aplicación','muted'))
    window.app_selector=QComboBox();window.app_selector.setMinimumWidth(220);window.app_selector.currentIndexChanged.connect(window.app_selected)
    selector_row.addWidget(window.app_selector,1)
    window.app_up=button('Subir nivel','up',window.app_go_up)
    window.app_up.setToolTip(tr('Volver a la carpeta anterior'))
    selector_row.addWidget(window.app_up)
    apps_bar_layout.addLayout(selector_row)
    actions_row=QHBoxLayout();actions_row.setSpacing(8)
    window.app_add_files=button('Añadir archivos','plus',window.choose_app_files);window.app_add_files.setObjectName('primary')
    window.app_add_files.setToolTip(tr('Copiar archivos del ordenador dentro de la carpeta abierta de la aplicación.'))
    window.app_add_folder=button('Añadir carpeta','upload',window.choose_app_upload_folder)
    window.app_add_folder.setToolTip(tr('Copiar una carpeta completa y su contenido dentro de la aplicación.'))
    window.app_new_folder=button('Nueva carpeta','folder',window.create_app_folder)
    window.app_new_folder.setToolTip(tr('Crear una subcarpeta vacía dentro de Documentos.'))
    window.app_rename=button('Renombrar','tag',window.rename_app_entry)
    window.app_rename.setToolTip(tr('Cambiar el nombre del archivo o carpeta seleccionado.'))
    window.app_export=button('Exportar','download',window.export_app_entries)
    window.app_export.setToolTip(tr('Guardar en el ordenador los archivos o carpetas seleccionados.'))
    window.app_delete=button('Eliminar','trash',window.delete_app_entries);window.app_delete.setObjectName('destructive')
    window.app_delete.setToolTip(tr('Eliminar los archivos o carpetas seleccionados dentro de Documentos; pide confirmación.'))
    for value in (window.app_add_files,window.app_add_folder,window.app_new_folder,window.app_rename,window.app_export):actions_row.addWidget(value)
    actions_row.addStretch();actions_row.addWidget(window.app_delete)
    apps_bar_layout.addLayout(actions_row)
    filter_row=QHBoxLayout();filter_row.setSpacing(10)
    window.app_search=QLineEdit();window.app_search.setPlaceholderText(tr('Buscar archivo o carpeta en esta ruta…'));window.app_search.setClearButtonEnabled(True);window.app_search.setMinimumHeight(34)
    filter_row.addWidget(window.app_search,1)
    window.app_conflict=QComboBox();window.app_conflict.addItems(['Si existe: Omitir','Si existe: Renombrar','Si existe: Reemplazar'])
    window.app_conflict.setToolTip(tr('Qué hacer al copiar o exportar si ya existe un archivo con el mismo nombre.'))
    filter_row.addWidget(window.app_conflict)
    apps_bar_layout.addLayout(filter_row)
    apps_layout.addWidget(apps_bar)
    path_bar=QFrame();path_bar.setObjectName('pathBar')
    path_row=QHBoxLayout(path_bar);path_row.setContentsMargins(10,6,12,6);path_row.setSpacing(6)
    window.app_breadcrumbs=QHBoxLayout();window.app_breadcrumbs.setContentsMargins(0,0,0,0);window.app_breadcrumbs.setSpacing(2)
    path_row.addLayout(window.app_breadcrumbs)
    path_row.addStretch()
    window.app_entries_count=text_label('','muted');path_row.addWidget(window.app_entries_count)
    window.app_path_label=QLabel('/Documents');window.app_path_label.setTextFormat(Qt.TextFormat.PlainText);window.app_path_label.setObjectName('section');window.app_path_label.hide();path_row.addWidget(window.app_path_label)
    apps_layout.addWidget(path_bar)
    window.app_table=QTableWidget(0,4);window.app_table.setHorizontalHeaderLabels(['Nombre','Tipo','Tamaño','Modificado'])
    for col,align in ((0,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter),(1,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter),(2,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter),(3,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)):
        item=window.app_table.horizontalHeaderItem(col)
        if item is not None:item.setTextAlignment(align)
    apps_layout.addWidget(window.app_table,1)
    window.app_status=text_label('Conecta tu iPhone y pulsa Actualizar para ver las apps con archivos compartidos.','muted',True)
    apps_layout.addWidget(window.app_status)
    apps_layout.addWidget(text_label('Solo aparecen apps instaladas con intercambio de archivos habilitado en iOS. También puedes arrastrar archivos o carpetas aquí.','muted',True))
    window.pages.addWidget(apps_page)

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
    window.preview_play_button=button('Escuchar vista previa','pulse',window.toggle_audio_preview);window.preview_play_button.setEnabled(False);hero_layout.addWidget(window.preview_play_button)
    window.preview_audio_status=QLabel('');window.preview_audio_status.setObjectName('muted');window.preview_audio_status.setWordWrap(True);window.preview_audio_status.hide();hero_layout.addWidget(window.preview_audio_status)
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
    window.inspector_details=[window.cover_metadata,window.view_cover,window.preview_play_button,window.lyrics_status,window.view_lyrics,properties_title,properties]
    for value in window.inspector_details:value.hide()
    description=QLabel(tr('Lleva tus canciones a Música y conserva tus originales en el ordenador.'));description.setObjectName('heroDescription');description.setWordWrap(True);hero_layout.addWidget(description);hero_layout.addStretch()
    window.inspector_scroll=QScrollArea();window.inspector_scroll.setObjectName('inspector');window.inspector_scroll.setWidgetResizable(True);window.inspector_scroll.setFrameShape(QFrame.Shape.NoFrame);window.inspector_scroll.setMinimumWidth(360);window.inspector_scroll.setWidget(window.inspector)
    dialog_layout.addWidget(window.inspector_scroll)
    close_details=button('Cerrar','close',window.inspector_dialog.close);dialog_layout.addWidget(close_details)
    window.inspector_toggle.setChecked(False);window.inspector_toggle.toggled.connect(window.inspector_dialog.setVisible)
    window.inspector_dialog.finished.connect(window.inspector_closed)
    activity=QFrame();activity.setObjectName('activityBar');activity_layout=QHBoxLayout(activity);activity_layout.setContentsMargins(18,8,18,8);activity_layout.setSpacing(12)
    window.status=text_label('Sin canciones para importar.','muted',True);activity_layout.addWidget(window.status,1)
    window.progress=QProgressBar();window.progress.setFixedWidth(180);window.progress.setFixedHeight(8);window.progress.setTextVisible(False);window.progress.hide();activity_layout.addWidget(window.progress)
    window.pause_transfer_button=button('Pausar','pause',window.pause_transfer);window.pause_transfer_button.hide();activity_layout.addWidget(window.pause_transfer_button)
    window.cancel_transfer_button=button('Cancelar','close',window.cancel_transfer);window.cancel_transfer_button.hide();activity_layout.addWidget(window.cancel_transfer_button);shell.addWidget(activity)
    window.errors=QListWidget();window.errors.setMaximumHeight(80);window.errors.hide();import_layout.addWidget(window.errors)
    for table in (window.table,window.library_table,window.app_table):
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.verticalHeader().hide();table.setShowGrid(False);table.setAlternatingRowColors(True)
        table.setIconSize(QSize(28,28));table.verticalHeader().setDefaultSectionSize(max(42,QFontMetrics(table.font()).height()+16));table.setWordWrap(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionsClickable(True);table.setSortingEnabled(True);table.horizontalHeader().setMinimumHeight(38)
    set_column_metrics(window)
    window.table.setColumnWidth(6,QFontMetrics(window.table.font()).horizontalAdvance('Ya en el iPhone')+28)
    window.library_table.sortByColumn(0,Qt.SortOrder.AscendingOrder);window.table.sortItems(0,Qt.SortOrder.AscendingOrder);window.app_table.sortByColumn(0,Qt.SortOrder.AscendingOrder)
    window.library_table.selectionModel().selectionChanged.connect(window.library_selection_changed);window.table.itemSelectionChanged.connect(window.local_selection_changed)
    window.app_table.itemSelectionChanged.connect(window.update_buttons);window.app_table.cellDoubleClicked.connect(window.app_entry_activated)
    window.app_search.textChanged.connect(window.populate_app_table)
    window.library_table.horizontalHeader().sortIndicatorChanged.connect(window.schedule_artwork);window.search.textChanged.connect(window.filter_library);window.format_filter.currentIndexChanged.connect(window.filter_library);window.content_filter.currentIndexChanged.connect(window.filter_library);window.playlist_filter.currentIndexChanged.connect(window.filter_library)
    window.view_mode_group.idClicked.connect(window.change_library_view_mode)
    window.collection_grid.groupCheckToggled.connect(window.toggle_collection_group)
    window.collection_grid.groupActivated.connect(window.open_collection_group)
    window.library_model.checkedChanged.connect(window.checks_changed);window.select_visible.clicked.connect(window.library_model.check_visible)
    window.navigation.idClicked.connect(window.navigate);window.nav_buttons[0].setChecked(True)
    for control in (window.metadata_choice,window.export_structure,window.convert_codec):control.currentIndexChanged.connect(window.save_transfer_preferences)
    for control in (window.import_artwork,window.import_lyrics,window.embed_artwork,window.auto_import,window.refresh_after_transfer,window.export_incremental,window.convert_audio,window.auto_check_updates):control.toggled.connect(window.save_transfer_preferences)
    window.ffmpeg_path.editingFinished.connect(window.save_transfer_preferences)
    from .presentation import DropVeil
    window.drop_veil=DropVeil(root);window.setWindowIcon(app_icon())


def set_column_metrics(window):
    """Reserve intrinsic text width, including sort arrows, padding and DPI scaling."""
    for table in (window.library_table,window.table):
        metrics=QFontMetrics(table.font())
        for column,sample in ((1,'Artista de la canción'),(2,'Nombre del álbum'),(3,'M4A · ALAC'),(4,'Duración'),(5,'999.9 MB')):
            table.setColumnWidth(column,metrics.horizontalAdvance(sample)+32)
    if hasattr(window,'app_table'):
        metrics=QFontMetrics(window.app_table.font())
        for column,sample in ((1,'Carpeta'),(2,'999.9 MB'),(3,'2026-12-31 23:59')):
            window.app_table.setColumnWidth(column,metrics.horizontalAdvance(sample)+32)


def layout_transfer_actions(window):
    window.action_columns=3
    for value in (window.choose,window.import_phone,window.export_phone):
        value.setMinimumHeight(42)
        if window.transfer_actions.indexOf(value)<0:
            window.transfer_actions.addWidget(value)


def apply_theme(window):
    selection=window.theme_choice.currentIndex()
    dark=selection==2 or selection==0 and QApplication.styleHints().colorScheme()==Qt.ColorScheme.Dark
    c=({'bg':'#0d191b','side':'#0a1d20','card':'#142d30','cardEnd':'#12292c','text':'#eef5f4','muted':'#99b5b4',
        'border':'#254043','rowLine':'rgba(255,255,255,0.06)','button':'#193438','hover':'#24464a','selected':'#224447','alternate':'#112629',
        'orange':'#f27620','primaryText':'#241309','primaryHover':'#ff973d','nav':'#1a4448','navBorder':'#2b6368','settingsActive':'#1a4448','settingsBorder':'#2b6368',
        'battery':'#3cc894'} if dark else
       {'bg':'#f9f8f5','side':'#f0eee9','card':'#ffffff','cardEnd':'#faf8f5','text':'#133133','muted':'#5b7274',
        'border':'#e2e2dc','rowLine':'rgba(19,49,51,0.08)','button':'#ffffff','hover':'#f2eee8','selected':'#e3efed','alternate':'#f7f9f7',
        'orange':'#c44f08','primaryText':'#ffffff','primaryHover':'#a94104','nav':'#1f5c60','navBorder':'#2a6e72','settingsActive':'#e3efed','settingsBorder':'#bfd8d5',
        'battery':'#1c8b68'})
    accent=window.use_accent.isChecked();reduced=window.reduce_transparency.isChecked()
    if not accent:c.update(orange='#58b9b5' if dark else '#246d70',primaryText='#10292b' if dark else '#ffffff',primaryHover='#7bcbc7' if dark else '#16575b',nav='#24575a' if dark else '#276a6d',navBorder='#367f80')
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
    material=lambda color:'rgba('+','.join(str(v) for v in QColor(color).getRgb()[:3])+',244)'
    panel_bg=c['card'] if reduced else f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {material(c['card'])},stop:1 {material(c['cardEnd'])})"
    check=(Path(__file__).with_name('assets')/('check-dark.svg' if dark else 'check-light.svg')).as_posix()
    chevron=(Path(__file__).with_name('assets')/('chevron-dark.svg' if dark else 'chevron-light.svg')).as_posix()
    window.setStyleSheet(f'''
        QWidget {{color:{c['text']};font-family:"{family}";font-size:{base}pt;}}
        QWidget#shell,QStackedWidget {{background:transparent;}}
        QFrame#sidebar {{background:{c['side']};border:0;border-right:1px solid {c['border']};}}
        QFrame#sidebarFooter {{background:transparent;border:0;}}
        QWidget#workspace {{background:transparent;}}
        QFrame#tableCard {{background:{panel_bg};border:1px solid {c['border']};border-radius:12px;}}
        QFrame#devicePill {{background:{c['button']};border:1px solid {c['border']};border-radius:15px;}}
        QFrame#settingsMenu {{background:{c['side']};border:1px solid {c['border']};border-radius:12px;}}
        QFrame#pathBar {{background:{c['button']};border:1px solid {c['border']};border-radius:9px;}}
        QFrame#updateBanner {{background:{'#1b3a3e' if dark else '#fdf1e6'};border:1px solid {c['orange']};border-radius:10px;}}
        QFrame#segmentBar {{background:{c['button']};border:1px solid {c['border']};border-radius:9px;}}
        QPushButton#segment {{background:transparent;border:0;border-radius:6px;padding:3px 11px;color:{c['muted']};font-weight:500;}}
        QPushButton#segment:hover {{color:{c['text']};background:{c['hover']};}}
        QPushButton#segment:checked {{background:{c['nav']};color:#ffffff;font-weight:600;}}
        QListWidget#collectionGrid {{background:{c['card']};border:1px solid {c['border']};border-radius:10px;padding:8px;outline:0;}}
        QListWidget#collectionGrid::item {{background:{c['button']};border:1px solid {c['border']};border-radius:10px;padding:8px;}}
        QListWidget#collectionGrid::item:selected {{background:{c['selected']};border-color:{c['orange']};}}
        QScrollArea#settingsScroll,QScrollArea#settingsScroll > QWidget {{background:transparent;border:0;}}
        QLabel#brand {{font-size:{base+1}pt;font-weight:700;}}
        QLabel#title {{font-size:{base+7}pt;font-weight:600;}}
        QLabel#cardTitle {{font-size:{base+1}pt;font-weight:600;}}
        QLabel#deviceName {{font-size:{base+2}pt;font-weight:600;}}
        QLabel#devicePillName {{font-weight:600;}}
        QLabel#deviceMetric {{font-weight:600;}}
        QLabel#metric {{font-size:{base+3}pt;font-weight:600;}}
        QLabel#muted,QLabel#metadata,QLabel#heroDescription {{color:{c['muted']};}}
        QLabel#checkState {{padding:2px 8px;border-radius:6px;font-size:{base-.5}pt;color:{c['muted']};}}
        QLabel#checkState[passed="true"] {{background:{'#143829' if dark else '#e6f5ec'};color:{'#63d489' if dark else '#1f6d36'};font-weight:600;}}
        QLabel#checkState[failed="true"] {{background:{'#3d2728' if dark else '#fae9ea'};color:{'#ffbc7f' if dark else '#a53e00'};font-weight:600;}}
        QLabel#small,QLabel#section {{font-size:{base-.5}pt;color:{c['muted']};}}
        QLabel#section {{font-weight:600;}}
        QLabel#connectionDot {{color:#969696;}}
        QLabel#connectionDot[connected="true"] {{color:{'#49d46b' if dark else '#2b9b4a'};}}
        QLabel#statusPill {{background:{c['button']};border:1px solid {c['border']};border-radius:12px;padding:4px 11px;font-size:{base-.5}pt;font-weight:600;}}
        QLabel#statusPill[connected="true"] {{background:{'#143829' if dark else '#e8f5ec'};border-color:{'#286649' if dark else '#b7dec2'};color:{'#68df8a' if dark else '#1f6d36'};}}
        QPushButton {{background:{c['button']};border:1px solid {c['border']};border-radius:8px;padding:5px 12px;font-weight:500;}}
        QPushButton:hover {{background:{c['hover']};}}
        QPushButton:pressed {{background:{c['selected']};}}
        QPushButton:focus {{border:2px solid {c['orange']};}}
        QPushButton#primary {{background:{c['orange']};color:{c['primaryText']};font-weight:600;border:1px solid {c['orange']};}}
        QPushButton#primary:hover {{background:{c['primaryHover']};}}
        QPushButton#secondaryAccent {{background:{'#245e61' if dark else '#276a6d'};color:#ffffff;border:1px solid {'#2f767a' if dark else '#246266'};}}
        QPushButton#destructive {{color:{'#ffb47d' if dark else '#b54200'};}}
        QPushButton:disabled,QPushButton#primary:disabled {{background:{c['bg']};color:{c['muted']};border:1px solid {c['border']};}}
        QPushButton#nav,QPushButton#settingsNav {{background:transparent;border:1px solid transparent;text-align:left;padding:7px 11px;}}
        QPushButton#nav:checked {{background:{c['nav']};border:1px solid {c['navBorder']};border-left:3px solid {c['orange']};color:#ffffff;font-weight:600;}}
        QPushButton#settingsNav:checked {{background:{c['settingsActive']};border:1px solid {c['settingsBorder']};border-left:3px solid {c['orange']};font-weight:600;}}
        QPushButton#nav:hover,QPushButton#settingsNav:hover {{border-color:{c['border']};}}
        QPushButton#crumb {{background:transparent;border:0;border-radius:6px;padding:3px 7px;color:{c['muted']};font-weight:500;}}
        QPushButton#crumb:hover {{background:{c['hover']};color:{c['text']};}}
        QPushButton#crumb[current="true"] {{color:{c['text']};font-weight:600;}}
        QPushButton[themeCard="true"] {{background:{c['bg']};border-radius:12px;padding:0;}}
        QPushButton[themeCard="true"]:checked {{border:2px solid {c['orange']};}}
        QLabel#formatChip {{background:{c['selected']};border:1px solid {c['border']};border-radius:7px;padding:4px 8px;min-width:48px;font-size:{base-1}pt;font-weight:600;}}
        QFrame#importDrop {{background:{c['card'] if reduced else ('#11292d' if dark else '#fff8f2')};border:1px dashed {c['border'] if dark else '#e6bda0'};border-radius:12px;}}
        QTableView,QTableWidget {{background:{c['card']};alternate-background-color:{c['alternate']};border:1px solid {c['border']};border-radius:10px;selection-background-color:{c['selected']};selection-color:{c['text']};outline:0;}}
        QTableView::item,QTableWidget::item {{padding:4px 10px;border-bottom:1px solid {c['rowLine']};}}
        QTableView::item:selected,QTableWidget::item:selected {{background:{c['selected']};}}
        QTableView::item:hover,QTableWidget::item:hover {{background:{c['hover']};}}
        QHeaderView,QTableCornerButton::section {{background:{c['card']};border:0;}}
        QHeaderView::section {{background:{c['card']};color:{c['muted']};padding:8px 10px;border:0;border-bottom:1px solid {c['border']};font-size:{base-.5}pt;font-weight:600;}}
        QLineEdit,QComboBox {{background:{c['button']};border:1px solid {c['border']};border-radius:8px;padding:6px 10px;selection-background-color:{c['selected']};}}
        QLineEdit:focus,QComboBox:focus {{border:1px solid {c['orange']};}}
        QComboBox {{padding-right:28px;min-height:22px;}}
        QComboBox::drop-down {{subcontrol-origin:padding;subcontrol-position:top right;width:26px;border:0;background:transparent;}}
        QComboBox::down-arrow {{image:url("{chevron}");width:15px;height:15px;}}
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
        QTableView::indicator,QTableWidget::indicator {{width:16px;height:16px;border:0;background:transparent;image:none;}}
        QCheckBox {{spacing:8px;padding:4px 0;}}
        QCheckBox::indicator,QListWidget::indicator {{width:16px;height:16px;border:1px solid {'#4e6f72' if dark else '#b4c3c2'};border-radius:5px;background:transparent;}}
        QCheckBox::indicator:hover,QListWidget::indicator:hover {{border-color:{'#789b9d' if dark else '#6d898b'};}}
        QCheckBox::indicator:checked,QListWidget::indicator:checked {{background:{c['orange']};border-color:{c['orange']};image:url("{check}");}}
        QCheckBox::indicator:indeterminate,QListWidget::indicator:indeterminate {{background:{c['selected']};border-color:{c['orange']};}}
        QFrame#activityBar {{background:{c['side']};border-top:1px solid {c['border']};}}
        QProgressBar {{background:{c['border']};border:0;border-radius:4px;}}
        QProgressBar::chunk {{background:{c['orange']};border-radius:4px;}}
        QProgressBar#batteryBar::chunk {{background:{c['battery']};border-radius:4px;}}
        QFrame#hero,QFrame#propertiesCard {{background:{c['card']};border:1px solid {c['border']};border-radius:12px;}}
        QLabel#inspectorTitle {{font-size:{base+5}pt;font-weight:600;}}
        QLabel#cover {{background:{c['selected']};border-radius:12px;font-size:32pt;}}
        QScrollArea#inspector,QScrollArea#inspector > QWidget > QWidget {{background:{c['bg']};border:0;}}
        QFrame#emptyState {{background:{c['card']};border:0;border-radius:12px;}}
        QLabel#emptyTitle {{font-size:{base+3}pt;font-weight:600;}}
        QLabel#emptySymbol {{font-size:26pt;color:{c['orange']};}}
        QFrame#dropVeil {{background:{c['bg']};border:2px dashed {c['orange']};border-radius:16px;}}
        QListWidget {{background:{c['card']};border:1px solid {c['border']};border-radius:8px;}}
        QScrollBar:vertical {{background:transparent;width:9px;margin:0;}}
        QScrollBar::handle:vertical {{background:{c['border']};min-height:28px;border-radius:4px;}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
        QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:transparent;}}
        QScrollBar:horizontal {{background:transparent;height:9px;margin:0;}}
        QScrollBar::handle:horizontal {{background:{c['border']};min-width:28px;border-radius:4px;}}
        QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal {{width:0;}}
        QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal {{background:transparent;}}
        QSplitter::handle {{background:{c['border']};height:1px;width:1px;}}
    ''')
    for value in window.findChildren(QPushButton):
        if isinstance(value,MotionButton):value.tone=QColor(c['orange'])
        kind=value.property('iconKind')
        if kind:
            color=c['primaryText'] if value.objectName()=='primary' else '#ffffff' if value.objectName()=='secondaryAccent' or value.objectName()=='nav' and value.isChecked() else c['text']
            value.setIcon(line_icon(kind,color,17))
    window.device_symbol.setPixmap(line_icon('phone','#a6d7d5' if dark else '#18565a',24).pixmap(24,24))
    window.diagnostic_symbol.setPixmap(line_icon('phone','#a6d7d5' if dark else '#18565a',42).pixmap(42,52))
    window.drop_symbol.setPixmap(line_icon('upload',c['orange'],32).pixmap(32,32))
    for table in (window.library_table,window.table,window.app_table):
        table.setProperty('checkAccent',c['orange']);table.setProperty('checkForeground',c['primaryText']);table.setProperty('darkTheme',dark)
        table.viewport().update()
    window.library_model.secondary_color=QColor(c['muted'])
    window.default_music_icon=music_placeholder_icon(c['selected'],c['border'],c['muted'],28);window.library_model.default_icon=window.default_music_icon
    window.default_folder_icon=line_icon('folder',c['orange'],22);window.default_file_icon=line_icon('file',c['muted'],22)
    if window.library_model.rowCount():window.library_model.dataChanged.emit(window.library_model.index(0,0),window.library_model.index(window.library_model.rowCount()-1,2),[Qt.ItemDataRole.DecorationRole,Qt.ItemDataRole.ForegroundRole])
    if getattr(window,'tracks',None):
        for row in range(window.table.rowCount()):
            item=window.table.item(row,0)
            if item is not None:
                track=window.tracks.get(item.data(Qt.ItemDataRole.UserRole))
                if track and not track.get('thumbnail'):item.setIcon(window.default_music_icon)
    if getattr(window,'app_entries',None):window.refresh_app_table_icons()
    window.theme_options[selection].setChecked(True);window.theme_dark=dark
    fit_controls(window);window.paint_transfer_stages()


def fit_controls(window):
    for control in window.findChildren(QPushButton):
        if not control.text() or control.objectName() in ('crumb','segment'):continue
        font=QFont(control.font())
        if control.objectName() in ('nav','settingsNav','primary'):
            font.setWeight(QFont.Weight.DemiBold)
        metrics=QFontMetrics(font)
        control.setMinimumWidth(metrics.horizontalAdvance(control.text())+(50 if control.property('iconKind') else 28))
    if hasattr(window,'view_mode_buttons'):
        for seg in window.view_mode_buttons:
            font=QFont(seg.font());font.setWeight(QFont.Weight.DemiBold)
            seg.setMinimumWidth(QFontMetrics(font).horizontalAdvance(seg.text())+24)
    window.sidebar.setFixedWidth(max(180,max(nav.minimumWidth() for nav in window.nav_buttons)+32))
    window.settings_menu.setFixedWidth(max(176,max(nav.minimumWidth() for nav in window.settings_buttons)+24))
    if hasattr(window,'formats_card') and hasattr(window,'queue_summary_card'):
        title_font=QFont(window.font());title_font.setPointSizeF(window.font().pointSizeF()+1);title_font.setWeight(QFont.Weight.DemiBold)
        title_metrics=QFontMetrics(title_font)
        chip_font=QFont(window.font());chip_font.setPointSizeF(max(8.0,window.font().pointSizeF()-1));chip_font.setWeight(QFont.Weight.DemiBold)
        chip_w=max(64,max(QFontMetrics(chip_font).horizontalAdvance(code)+22 for code in ('M4A','MP3','AAC','ALAC','WAV','AIFF')))
        needed=max(256,title_metrics.horizontalAdvance(str(tr('Formatos compatibles')))+48,title_metrics.horizontalAdvance(str(tr('Sincronización')))+48,chip_w*3+56,window.import_submit.minimumWidth()+44)
        window.formats_card.setFixedWidth(needed)
        window.queue_summary_card.setFixedWidth(needed)

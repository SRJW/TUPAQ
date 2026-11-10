"""Explicit UI messages; song/device metadata is never translated implicitly."""
import re
from string import Formatter
from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6 import QtWidgets
from .translations import EN

LANGUAGES = (('es', 'Español'), ('en', 'English'))
_language = 'es'
_patterns = []
for source, target in EN.items():
    if '{' not in source:
        continue
    parts = list(Formatter().parse(source))
    pattern = ''.join(re.escape(literal) + (f'(?P<{field}>[^\n]*?)' if field == 'filename' else f'(?P<{field}>.*?)' if field else '')
                      for literal, field, _, _ in parts)
    _patterns.append((re.compile(r'\A' + pattern + r'\Z', re.DOTALL), target))


def language():
    return _language


def render(source):
    if _language == 'es':
        return source
    if source in EN:
        return EN[source]
    for pattern, target in _patterns:
        match = pattern.fullmatch(source)
        if match:
            values = match.groupdict()
            # Only nested application messages, never titles/artists/paths.
            if 'message' in values:
                values['message'] = render(values['message'])
            if values.get('count') == '1':
                for unit in ('songs', 'files', 'complete files'):
                    target = target.replace('{count} ' + unit, '{count} ' + unit[:-1])
            return target.format_map(values)
    if '\n' in source:
        return '\n'.join(render(line) for line in source.split('\n'))
    return source


class Text(str):
    def __new__(cls, source):
        raw = source.source if isinstance(source, Text) else str(source)
        value = super().__new__(cls, render(raw))
        value.source = raw
        return value

    def upper(self):
        # Origins are app labels. Keep a source message for live switching.
        return Text(self.source.upper())


def tr(source):
    return Text(source)


class Localized:
    def __init__(self, *args, **kwargs):
        self._messages = {}
        super().__init__(*args, **kwargs)
        if args and isinstance(args[0], Text):
            self._messages['setText'] = args[0]

    def _set_message(self, method, value):
        if isinstance(value, Text):
            self._messages[method] = value
        else:
            self._messages.pop(method, None)
        getattr(super(), method)(str(value))

    def setText(self, value): self._set_message('setText', value)
    def setToolTip(self, value): self._set_message('setToolTip', value)
    def setPlaceholderText(self, value): self._set_message('setPlaceholderText', value)
    def setWindowTitle(self, value): self._set_message('setWindowTitle', value)
    def setInformativeText(self, value): self._set_message('setInformativeText', value)
    def setDetailedText(self, value): self._set_message('setDetailedText', value)

    def retranslate(self):
        for method, message in self._messages.items():
            getattr(super(), method)(render(message.source))


class QLabel(Localized, QtWidgets.QLabel): pass
class QPushButton(Localized, QtWidgets.QPushButton): pass
class QCheckBox(Localized, QtWidgets.QCheckBox): pass
class QLineEdit(Localized, QtWidgets.QLineEdit): pass
class QMessageBox(Localized, QtWidgets.QMessageBox): pass


class QComboBox(Localized, QtWidgets.QComboBox):
    def __init__(self, *args, **kwargs):
        self._item_messages = {}
        super().__init__(*args, **kwargs)
        view=QtWidgets.QListView(self)
        view.setUniformItemSizes(True)
        view.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        view.setSpacing(2)
        self.setView(view)
        self.setMaxVisibleItems(12)

    def showPopup(self):
        popup=self.view().window()
        popup.setObjectName('comboPopup')
        popup.setPalette(self.palette())
        super().showPopup()

    def addItems(self, values):
        for value in values:
            value = tr(value)
            row = self.count()
            super().addItem(str(value))
            if isinstance(value, Text): self._item_messages[row] = value

    def retranslate(self):
        super().retranslate()
        blocked = self.blockSignals(True)
        try:
            for row, message in self._item_messages.items():
                self.setItemText(row, render(message.source))
        finally:
            self.blockSignals(blocked)


class QTableWidget(Localized, QtWidgets.QTableWidget):
    def setHorizontalHeaderLabels(self, labels):
        self._headers = [tr(label) for label in labels]
        super().setHorizontalHeaderLabels([str(label) for label in self._headers])

    def retranslate(self):
        super().retranslate()
        for column, message in enumerate(getattr(self, '_headers', [])):
            if isinstance(message, Text):
                self.horizontalHeaderItem(column).setText(render(message.source))


class QListWidget(Localized, QtWidgets.QListWidget):
    def addItem(self, value):
        if isinstance(value, Text):
            item = QtWidgets.QListWidgetItem(str(value))
            item._message = value
            super().addItem(item)
        else: super().addItem(value)

    def retranslate(self):
        super().retranslate()
        for row in range(self.count()):
            item = self.item(row)
            message = getattr(item, '_message', None)
            if message is not None: item.setText(render(message.source))


def set_language(code, root=None):
    global _language
    _language = code if isinstance(code, str) and code in dict(LANGUAGES) else 'es'
    app = QtWidgets.QApplication.instance()
    previous = getattr(app, '_tupaq_qt_translator', None)
    if previous is not None:
        app.removeTranslator(previous)
        previous.deleteLater()
    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load('qtbase_' + _language, folder): app.installTranslator(translator)
    app._tupaq_qt_translator = translator
    if root is not None:
        for widget in root.findChildren(QtWidgets.QWidget):
            if isinstance(widget, Localized): widget.retranslate()

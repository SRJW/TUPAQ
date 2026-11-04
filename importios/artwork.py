"""Bounded embedded-image decoding into small PNG previews."""
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QImageReader


def thumbnail(data,limit=96):
    if not data or len(data) > 5*1024*1024:
        return None
    source = QBuffer()
    source.setData(QByteArray(data))
    source.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(source)
    size = reader.size()
    if not size.isValid() or size.width()*size.height() > 16_000_000:
        return None
    reader.setScaledSize(size.scaled(QSize(limit, limit), Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        return None
    result = QBuffer()
    result.open(QIODevice.OpenModeFlag.WriteOnly)
    return bytes(result.data()) if image.save(result, 'PNG') else None

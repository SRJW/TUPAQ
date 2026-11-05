"""Bounded embedded-image decoding into small PNG previews."""
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QImageReader

PREVIEW_BYTES=20*1024*1024
PREVIEW_PIXELS=36_000_000


def image_info(data):
    if not data or len(data)>PREVIEW_BYTES:return None
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer);size=reader.size()
    if not size.isValid() or size.width()*size.height()>PREVIEW_PIXELS:return None
    return {'cover_width':size.width(),'cover_height':size.height(),'cover_bytes':len(data),
            'cover_format':bytes(reader.format()).decode('ascii',errors='replace').upper()}


def preview_image(data,original=False):
    info=image_info(data)
    if not info:return None
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer);reader.setAllocationLimit(192);reader.setAutoTransform(True)
    size=reader.size()
    if not original and max(size.width(),size.height())>1024:
        reader.setScaledSize(size.scaled(QSize(1024,1024),Qt.AspectRatioMode.KeepAspectRatio))
    image=reader.read()
    return None if image.isNull() else image


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

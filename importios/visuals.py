"""Small painted native icons; no web view, animation or external icon font."""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QPen, QLinearGradient, QFont


def music_icon(size=64):
    image = QPixmap(size*2,size*2)
    image.setDevicePixelRatio(2)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0,0,size,size)
    for stop,color in [(0,'#ffb37c'),(.4,'#ff3d91'),(1,'#6238ff')]:
        gradient.setColorAt(stop,QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(1,1,size-2,size-2),size*.23,size*.23)
    painter.setPen(QColor('white'))
    font = QFont();font.setPixelSize(int(size*.8));font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(0,-size*.03,size,size),Qt.AlignmentFlag.AlignCenter,'♪')
    painter.end()
    return QIcon(image)


def line_icon(kind, color='#52576d', size=22):
    image = QPixmap(size*2,size*2);image.setDevicePixelRatio(2)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size/24,size/24)
    p.setPen(QPen(QColor(color),1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    if kind == 'home':
        p.drawPolyline([QPointF(3,11),QPointF(12,3),QPointF(21,11)])
        p.drawPolyline([QPointF(5,10),QPointF(5,21),QPointF(10,21),QPointF(10,14),QPointF(14,14),QPointF(14,21),QPointF(19,21),QPointF(19,10)])
    elif kind == 'library':
        for y in [6,11,16]:
            p.drawPolyline([QPointF(3,y),QPointF(12,y-4),QPointF(21,y),QPointF(12,y+4),QPointF(3,y)])
    elif kind in ('phone','usb'):
        p.drawRoundedRect(QRectF(7,2,10,20),2,2)
        p.drawLine(10,5,14,5);p.drawPoint(12,19)
        if kind == 'usb':p.drawLine(3,9,3,16);p.drawLine(3,16,6,16)
    elif kind in ('upload','download'):
        y1,y2 = (16,4) if kind == 'upload' else (4,16)
        p.drawLine(12,y1,12,y2)
        dy = 4 if kind == 'upload' else -4
        p.drawLine(12,y2,8,y2+dy);p.drawLine(12,y2,16,y2+dy)
        p.drawPolyline([QPointF(4,17),QPointF(4,21),QPointF(20,21),QPointF(20,17)])
    elif kind == 'settings':
        for y,x in [(6,8),(12,16),(18,10)]:
            p.drawLine(3,y,21,y);p.setBrush(QColor(color));p.drawEllipse(QPointF(x,y),2.3,2.3);p.setBrush(Qt.BrushStyle.NoBrush)
    elif kind == 'plus':
        p.drawEllipse(QRectF(3,3,18,18));p.drawLine(7,12,17,12);p.drawLine(12,7,12,17)
    elif kind == 'refresh':
        p.drawArc(QRectF(4,4,16,16),35*16,280*16);p.drawPolyline([QPointF(15,3),QPointF(20,4),QPointF(20,9)])
    elif kind == 'copy':
        p.drawRoundedRect(QRectF(8,7,12,14),2,2);p.drawPolyline([QPointF(5,16),QPointF(3,16),QPointF(3,3),QPointF(15,3)])
    elif kind == 'folder':
        p.drawPolyline([QPointF(3,7),QPointF(3,4),QPointF(10,4),QPointF(12,7),QPointF(21,7),QPointF(21,20),QPointF(3,20),QPointF(3,7),QPointF(21,7)])
    elif kind == 'trash':
        p.drawLine(4,6,20,6);p.drawRect(QRectF(7,6,10,15));p.drawLine(9,3,15,3);p.drawLine(10,10,10,17);p.drawLine(14,10,14,17)
    elif kind == 'close':
        p.drawLine(6,6,18,18);p.drawLine(6,18,18,6)
    else:
        font = QFont();font.setPixelSize(21);p.setFont(font)
        p.drawText(QRectF(0,0,24,24),Qt.AlignmentFlag.AlignCenter,'♪')
    p.end()
    return QIcon(image)

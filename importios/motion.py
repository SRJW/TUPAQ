"""Short, event-driven native motion. No idle timers or external UI runtime."""
from PySide6.QtCore import Qt,QVariantAnimation,QEasingCurve,QEvent,QRectF
from PySide6.QtGui import QColor,QPainter,QPixmap,QIcon,QPalette
from PySide6.QtWidgets import QWidget,QLabel,QStyleOptionButton,QStyle
from .i18n import QPushButton


def controller_for(widget):
    while widget is not None:
        controller=getattr(widget,'motion',None)
        if controller is not None:return controller
        widget=widget.parentWidget()
    return None


def animate(animation,start,end,enabled):
    animation.stop()
    animation.setStartValue(float(start));animation.setEndValue(float(end))
    if enabled:animation.start()
    else:animation.setCurrentTime(animation.duration())


def animation(parent,duration,callback):
    value=QVariantAnimation(parent);value.setDuration(duration);value.setEasingCurve(QEasingCurve.Type.OutCubic)
    value.setProperty('tupaqMotion',True);value.valueChanged.connect(callback)
    return value


class MotionController:
    def __init__(self,window,enabled=True):self.window=window;self.enabled=enabled;self.overlay=None
    def set_enabled(self,enabled):
        self.enabled=bool(enabled)
        if not enabled:
            for value in self.window.findChildren(QVariantAnimation):
                if value.property('tupaqMotion'):value.setCurrentTime(value.duration());value.stop()
            if self.overlay:self.overlay.finish()
    def navigate(self,stack,index):
        if stack.currentIndex()==index:return
        if self.overlay:self.overlay.finish()
        ratio=stack.devicePixelRatioF()
        if not self.enabled or not stack.isVisible() or stack.width()*stack.height()*ratio*ratio>8_000_000:
            stack.setCurrentIndex(index);return
        image=stack.currentWidget().grab()
        stack.setCurrentIndex(index)
        if self.overlay is None:self.overlay=PageVeil(stack)
        self.overlay.reveal(image)


class MotionButton(QPushButton):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.hover=0.;self.selection=0.;self.tone=QColor('#b8430a')
        self.hover_animation=animation(self,120,self.set_hover)
        self.selection_animation=animation(self,180,self.set_selection)
        self.toggled.connect(self.change_selection)
    def motion_enabled(self):
        controller=controller_for(self)
        return controller.enabled if controller else False
    def set_hover(self,value):self.hover=float(value);self.update()
    def set_selection(self,value):self.selection=float(value);self.update()
    def change_selection(self,checked):animate(self.selection_animation,self.selection,int(checked),self.motion_enabled())
    def enterEvent(self,event):
        if self.isEnabled():animate(self.hover_animation,self.hover,1,self.motion_enabled())
        super().enterEvent(event)
    def leaveEvent(self,event):
        animate(self.hover_animation,self.hover,0,self.motion_enabled());super().leaveEvent(event)
    def paintEvent(self,event):
        if self.objectName()=='nav' and not self.property('rail') and self.selection:
            painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color=QColor(self.tone);color.setAlpha(round(36*self.selection));painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(color);painter.drawRoundedRect(QRectF(self.rect()),12,12);painter.end()
        if self.property('rail') or self.property('tileAction'):
            painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            option=QStyleOptionButton();self.initStyleOption(option);option.text='';option.icon=QIcon()
            self.style().drawControl(QStyle.ControlElement.CE_PushButton,option,painter,self)
            if self.selection and self.property('rail'):
                color=QColor(self.tone);color.setAlpha(round(36*self.selection));painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(color);painter.drawRoundedRect(QRectF(self.rect()),20,20)
            size=28 if self.property('tileAction') else 26
            self.icon().paint(painter,(self.width()-size)//2,13,size,size,Qt.AlignmentFlag.AlignCenter,QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled)
            painter.setFont(self.font());painter.setPen(self.palette().color(QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled,QPalette.ColorRole.ButtonText))
            painter.drawText(self.rect().adjusted(4,43,-4,-8),Qt.AlignmentFlag.AlignCenter,self.text())
            if self.hover and self.isEnabled():
                color=QColor(self.tone);color.setAlpha(round(17*self.hover));painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(color);painter.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),20,20)
            return
        super().paintEvent(event)
        if self.hover and self.isEnabled():
            painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color=QColor(self.tone);color.setAlpha(round(17*self.hover));painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(color);painter.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),11,11)


class CoverView(QLabel):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.previous=QPixmap();self.blend=1.
        self.transition=animation(self,180,self.set_blend);self.transition.finished.connect(self.clear_previous)
    def set_blend(self,value):self.blend=float(value);self.update()
    def clear_previous(self):self.previous=QPixmap();self.update()
    def setPixmap(self,pixmap):
        current=self.pixmap();controller=controller_for(self)
        if controller and controller.enabled and self.isVisible() and current and not current.isNull() and not pixmap.isNull() and current.cacheKey()!=pixmap.cacheKey():
            self.previous=QPixmap(current);super().setPixmap(pixmap);animate(self.transition,0,1,True)
        else:
            self.transition.stop();self.previous=QPixmap();super().setPixmap(pixmap)
    def setText(self,text):
        if hasattr(self,'transition'):self.transition.stop();self.previous=QPixmap()
        super().setText(text)
    def paintEvent(self,event):
        super().paintEvent(event)
        if not self.previous.isNull() and self.blend<1:
            painter=QPainter(self);painter.setOpacity(1-self.blend)
            size=self.previous.deviceIndependentSize();painter.drawPixmap(round((self.width()-size.width())/2),round((self.height()-size.height())/2),self.previous)


class PageVeil(QWidget):
    def __init__(self,parent):
        super().__init__(parent);self.image=QPixmap();self.blend=1.
        # Briefly absorb clicks while the previous page is still visible.
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.transition=animation(self,180,self.set_blend);self.transition.finished.connect(self.finish)
        parent.installEventFilter(self);self.hide()
    def reveal(self,image):
        self.image=image;self.setGeometry(self.parentWidget().rect());self.show();self.raise_();animate(self.transition,0,1,True)
    def set_blend(self,value):self.blend=float(value);self.update()
    def finish(self):self.transition.stop();self.hide();self.image=QPixmap()
    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.Resize:self.finish()
        return False
    def paintEvent(self,event):
        painter=QPainter(self);painter.setOpacity(1-self.blend);painter.drawPixmap(0,round(-6*self.blend),self.image)

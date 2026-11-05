"""Cached atmospheric backdrop for translucent native panels."""
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QColor,QPainter,QPixmap,QLinearGradient,QRadialGradient
from PySide6.QtWidgets import QWidget

class Atmosphere(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.dark=True;self.mood=3;self.cache=None;self.setObjectName('shell')
    def set_scene(self,dark,mood):
        if (self.dark,self.mood)!=(dark,mood):self.dark,self.mood=dark,mood;self.cache=None;self.update()
    def paintEvent(self,event):
        size=self.size()
        if self.cache is None or self.cache.size()!=size:
            self.cache=QPixmap(size);p=QPainter(self.cache)
            if self.dark:
                sets=[('#172c40','#091420','#18394d','#28526a','#132838'),
                      ('#123b64','#17132c','#245bd5','#116964','#5c2789'),
                      ('#7d260f','#281321','#e45e11','#9a2325','#5c183e'),
                      ('#17181a','#101113','#1d1f22','#17191c','#16171a')]
            else:sets=[('#edf5fb','#e9ecf5','#97bedc','#b0c6e2','#c9d2e8'),
                       ('#e3f1ff','#f0eafb','#93c7ff','#8fd7d0','#c7a6ec'),
                       ('#fff0de','#f9e2ec','#ffbc77','#efa0a1','#e8b2d0'),
                       ('#f5f5f7','#ededf0','#e9e9ed','#f2f2f4','#e5e5e9')]
            top,bottom,a,b,c=sets[self.mood%4]
            gradient=QLinearGradient(0,0,size.width(),size.height());gradient.setColorAt(0,QColor(top));gradient.setColorAt(1,QColor(bottom));p.fillRect(self.rect(),gradient)
            for x,y,r,color in [(.02,.1,.85,a),(.94,.2,.72,b),(.25,1,.8,c)]:
                glow=QRadialGradient(QPointF(size.width()*x,size.height()*y),size.width()*r)
                center=QColor(color);center.setAlpha(130 if self.dark else 100);edge=QColor(color);edge.setAlpha(0)
                glow.setColorAt(0,center);glow.setColorAt(1,edge);p.fillRect(self.rect(),glow)
            sheen=QLinearGradient(0,0,0,size.height());sheen.setColorAt(0,QColor(255,255,255,20));sheen.setColorAt(.4,QColor(255,255,255,0));p.fillRect(self.rect(),sheen);p.end()
        painter=QPainter(self);painter.drawPixmap(0,0,self.cache)

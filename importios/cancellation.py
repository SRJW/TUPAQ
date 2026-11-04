"""Cooperative cancellation, with an atomic boundary before native metadata."""
from contextvars import ContextVar
import threading

CURRENT=ContextVar('tupaq_transfer_control',default=None)

class TransferCancelled(Exception):pass

class TransferControl:
    def __init__(self):
        self.event=threading.Event();self.lock=threading.Lock();self.committed=False;self.files=[]
    def request(self):
        with self.lock:
            self.event.set();return not self.committed
    def checkpoint(self):
        if self.event.is_set() and not self.committed:raise TransferCancelled()
    def begin_commit(self):
        with self.lock:
            self.checkpoint();self.committed=True

def checkpoint():
    control=CURRENT.get()
    if control is not None:control.checkpoint()

def begin_commit():
    control=CURRENT.get()
    if control is not None:control.begin_commit()

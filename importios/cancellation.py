"""Cooperative cancellation, with an atomic boundary before native metadata."""
from contextvars import ContextVar
import threading
import asyncio

CURRENT=ContextVar('tupaq_transfer_control',default=None)

class TransferCancelled(Exception):pass

class TransferControl:
    def __init__(self):
        self.event=threading.Event();self.lock=threading.Lock();self.committed=False;self.files=[];self.pause_requested=threading.Event()
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


async def wait_if_paused(progress=lambda *args:None):
    control=CURRENT.get()
    if control is None:return
    notified=False
    while control.pause_requested.is_set():
        checkpoint()
        if not notified:progress(0,0,'Pausado entre lotes.');notified=True
        await asyncio.sleep(.1)
    checkpoint()

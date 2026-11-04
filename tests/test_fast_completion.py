"""A legitimate fast terminal reply can predate local fsync, not the last ack."""
import tempfile
import time
import unittest
import test_transfers as support

class Phone(support.Phone):
    async def start_lockdown_service(self,name):return Peer(self)

class Peer(support.Peer):
    async def send(self,msg):
        await super().send(msg)
        if msg['Command']=='FileComplete' and not self.remaining:self.terminal_at=time.perf_counter_ns()
        if msg['Command']=='FileError' and not self.remaining:
            self.terminal_at=time.perf_counter_ns()
    async def receive(self):
        # Real phones wait for ancillary refusal before emitting SyncFinished.
        if self.queue and self.queue[0]['Command']=='SyncFinished' and not hasattr(self,'terminal_at'):raise AssertionError('missing timestamp')
        result=await super().receive()
        self.last_received_at=self.terminal_at if result['Command']=='SyncFinished' else time.perf_counter_ns()
        return result

class FastCompletionTests(unittest.TestCase):
    selected=support.TransferTests.selected
    call=support.TransferTests.call
    def test_fast_completion_during_final_send_is_not_misclassified_as_premature(self):
        with tempfile.TemporaryDirectory() as root:
            p=Phone();self.assertEqual(self.call(p,'import',[self.selected()],root)['imported'],1)

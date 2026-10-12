import pytest

from serialterminal.file_transfer import FileTransferManager, DataMessage
from serialterminal.file_transfer.transport import BinarySendReceipt, BinaryUserError
from serialterminal.profiles.chatter.machine_client import ChatterMachineClient
from serialterminal.profiles.chatter.machine_codec import Frame, Kind, decode, encode
from serialterminal.profiles.chatter.radio_timing import RadioTiming
from serialterminal.profiles.chatter.sweep import _lora_toa_s


@pytest.mark.parametrize('sf,bw,size,expected', [(7,500000,255,0.100), (12,500000,255,1.928), (12,500000,14,0.289)])
def test_toa_matches_radiolib_millisecond_rounding(sf,bw,size,expected):
    assert RadioTiming(sf,bw).toa_s(size) == expected
    assert _lora_toa_s(sf,bw,size) == expected


def test_budget_follows_phy_retry_and_header_settings():
    fast = RadioTiming(7,500000)
    slow = RadioTiming(12,500000)
    narrow = RadioTiming(12,7800)
    assert fast.budget_s('binary') < slow.budget_s('binary') < narrow.budget_s('binary')
    assert narrow.budget_s('binary') > 3600  # допустимый PHY не обрезается часом
    assert slow.budget_s('control') > slow.budget_s('binary') > 39.199
    assert RadioTiming(12,500000,attempts=1).transaction_s() < slow.transaction_s()
    assert RadioTiming(12,125000,ldro=True).toa_s(255) > RadioTiming(12,125000,ldro=False).toa_s(255)
    assert RadioTiming(9,125000,coding_rate=8,preamble=12).toa_s(255) > RadioTiming(9,125000).toa_s(255)


class TimingNode:
    def __init__(self):
        self.client = None
        self.commands = []
        self.submissions = []
        self.sf = 12
        self.generation = 1
        self.bad_bank = False
        self.change_generation_during_read = False

    def send(self, text):
        self.commands.append(text)
        def human(line):
            self.client.feed_line('chat', line)
        if text == '/config':
            human(f'[SYS] CFG RADIO power=2 dBm freq=470 MHz sf={self.sf} bw=500 kHz')
            human('[SYS] CFG LINK heartbeat=OFF retry=ON attempts=5 diag=OFF')
        elif text == '/radio read config':
            human('[SYS] RADIO_CONFIG_REGS phase=read preamble=8 sync=12')
            bank = 'FSK' if self.bad_bank else 'LoRa'
            human(f'[SYS] RADIO_CONFIG_DECODE phase=read bank={bank} mode=5 frequency_Hz=470000000 power_dBm=2')
            human(f'[SYS] RADIO_CONFIG_DECODE phase=read sf={self.sf} bw_Hz=500000 cr=4/5 header=explicit crc=1 ldro=0 agc=1')
            if self.change_generation_during_read:
                self.generation += 1
            human('[SYS] RADIO_CONFIG phase=read result=READ')
        else:
            frame = decode(text.lstrip('\n'))
            if frame.kind == Kind.HELLO:
                self.client.feed_line('chat',encode(Frame(Kind.WELCOME,41,frame.request,frame.payload+b'\x02\xf3\x00')).decode())
            elif frame.kind == Kind.SUBMIT:
                self.submissions.append(frame)
                self.client.feed_line('chat',encode(Frame(Kind.ACCEPTED,41,frame.request)).decode())
            elif frame.kind == Kind.CLOSE:
                self.client.feed_line('chat',encode(Frame(Kind.CLOSED,41,frame.request)).decode())
        return {'tx_id':len(self.commands)}


def timing_client():
    node = TimingNode()
    client = ChatterMachineClient(node.send,radio_timing=True,connection_generation=lambda:node.generation)
    node.client = client
    return client,node


def test_late_sf12_link_ok_keeps_original_identity_and_succeeds(monkeypatch):
    client,node = timing_client()
    clock = [1000.0]
    monkeypatch.setattr('serialterminal.profiles.chatter.machine_client.time.monotonic',lambda:clock[0])
    ticket = client.submit_binary(bytes(243))
    clock[0] += 39.199
    def arrival(_timeout):
        client.feed_line('chat',encode(Frame(Kind.LINK_OK,41,ticket.request)).decode())
    monkeypatch.setattr(client.condition,'wait',arrival)
    assert client.settle_binary(ticket).tx_id is not None
    assert len(node.submissions) == 1
    assert not client.pending
    client.close()


def test_fresh_phy_is_read_once_then_invalidated_by_generation_and_config():
    client,node = timing_client()
    slow = client.timing_budget_s('control')
    assert client.timing_budget_s('control') == slow
    assert node.commands == ['/config','/radio read config']
    node.sf = 7
    client.feed_line('chat','[SYS] SF 7 SAVED')
    assert client.legacy._radio_timing.last_snapshot is None
    assert client.timing_budget_s('control') < slow
    assert len(node.commands) == 4
    node.generation += 1
    client.timing_budget_s('control')
    assert len(node.commands) == 6
    assert not node.submissions
    client.close()


@pytest.mark.parametrize('bad_bank,changed',[(True,False),(False,True)])
def test_bad_or_old_readback_does_not_release_rf(bad_bank,changed):
    client,node = timing_client()
    node.bad_bank = bad_bank
    node.change_generation_during_read = changed
    with pytest.raises(BinaryUserError):
        client.send_binary(b'no RF')
    assert not node.submissions
    client.close()


class BudgetTransport:
    payload_capacity = 243
    def __init__(self):
        self.drained = []
    def set_receiver(self,receiver):
        self.receiver = receiver
    def timing_budget_s(self,purpose):
        return {'control':47,'resume':13,'drain':21}[purpose]
    def send_binary(self,data,*,cancel_event=None):
        return BinarySendReceipt(None)
    def drain_binary(self,timeout_s):
        self.drained.append(timeout_s)
        return {}


def test_ft1_uses_opaque_budgets_and_no_implicit_hour(tmp_path):
    transport = BudgetTransport()
    manager = FileTransferManager(transport,receive_dir=tmp_path)
    try:
        assert manager.result_timeout_s is None
        assert manager._timing_budget_s('control',manager.control_replay_interval_s) == 47
        assert manager._timing_budget_s('resume',manager.resume_handshake_timeout_s) == 13
        assert manager._incoming_idle_budget_s() == 4*47+21
        record = manager._reserve_record(191,direction='TX',filename='fixture')
        manager._terminal_record(record,'completed')
        assert transport.drained == [21]
    finally:
        manager.close()


def test_cleanup_failure_preserves_original_failure_and_lease(tmp_path):
    from serialterminal.file_transfer.core import FileTransferError
    transport = BudgetTransport()
    def unresolved(_timeout):
        raise BinaryUserError('local_tx_unsettled','still waiting for proof')
    transport.drain_binary = unresolved
    manager = FileTransferManager(transport,receive_dir=tmp_path)
    try:
        record = manager._reserve_record(192,direction='TX',filename='fixture')
        failure = FileTransferError('binary_send_failed','original cause',phase='sending')
        manager._terminal_record(record,'failed',failure=failure)
        assert record.snapshot()['failure']['code'] == 'binary_send_failed'
        assert manager._active_id == 192
    finally:
        manager.close()


def test_explicit_ft1_policy_is_preserved(tmp_path):
    manager = FileTransferManager(BudgetTransport(),receive_dir=tmp_path,result_timeout_s=4,
                                  control_replay_interval_s=2,resume_handshake_timeout_s=3,incoming_idle_timeout_s=5)
    try:
        assert manager.result_timeout_s == 4
        assert manager._timing_budget_s('control',manager.control_replay_interval_s) == 2
        assert manager._timing_budget_s('resume',manager.resume_handshake_timeout_s) == 3
        assert manager._incoming_idle_budget_s() == 5
    finally:
        manager.close()


def test_receiver_idle_estimate_survives_local_boot_without_authorizing_rf(tmp_path):
    from test_file_transfer_failure_retention import fixture
    client, node = timing_client()
    transport = BudgetTransport()
    base_budget = transport.timing_budget_s
    transport.timing_budget_s = lambda purpose: client.timing_budget_s(purpose) if purpose == 'control' else base_budget(purpose)
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    try:
        meta, chunks, _ = fixture(manager, count=3)
        manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
        before = manager._incoming_idle_budget_s()
        client.feed_line('chat', 'ESP-ROM:esp32s3-20210327')
        # Idle sweep оценивает срок уже принятого файла, а не выдаёт RF admission.
        manager._expire_stale_incoming()
        assert manager._incoming_idle_budget_s() == before
        assert manager._records[meta.transfer_id].state == 'receiving'
        assert manager._resume_store.incoming_part(meta.transfer_id).is_file()
        assert manager._rx_thread.is_alive()
        with pytest.raises(BinaryUserError) as caught:
            client.submit_binary(b'RF forbidden before READY')
        assert caught.value.code == 'local_controller_reset'
        assert not node.submissions
        node.sf = 7
        client.feed_line('chat', '[SYS] CHATTER READY')
        assert manager._incoming_idle_budget_s() < before
    finally:
        manager.close()
        client.close()

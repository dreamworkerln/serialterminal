import struct
import time
import pytest

from serialterminal.file_transfer.transport import BinaryUserError
from serialterminal.profiles.chatter.machine_client import ChatterMachineClient
from serialterminal.profiles.chatter.machine_codec import Frame,Kind,decode,encode


class Node:
    def __init__(self):
        self.client=None; self.frames=[]; self.epoch=41; self.drop_link=False
        self.legacy=False; self.unknown=False; self.outcomes={}; self.write_unknown=False
    def send(self,text):
        frame=decode(text.lstrip("\n")); self.frames.append(frame)
        def emit(kind,payload=b"",epoch=None):
            self.client.feed_line("chat",encode(Frame(kind,self.epoch if epoch is None else epoch,frame.request,payload)).decode())
        if frame.kind == Kind.HELLO:
            if self.legacy: self.client.feed_line("chat","[SYS] COMMAND INVALID: use /help")
            else: emit(Kind.WELCOME,frame.payload+b"\x02"+struct.pack("<H",243))
        elif frame.kind == Kind.CLOSE:
            emit(Kind.CLOSED)
        elif frame.kind == Kind.SUBMIT:
            self.outcomes[frame.request]=Kind.LINK_OK
            emit(Kind.ACCEPTED)
            emit(Kind.TX_DONE)
            if not self.drop_link: emit(Kind.LINK_OK)
        elif frame.kind == Kind.QUERY:
            emit(Kind.UNKNOWN if self.unknown else self.outcomes.get(frame.request,Kind.UNKNOWN))
        if self.write_unknown and frame.kind == Kind.SUBMIT: raise BinaryUserError("local_tx_unknown","lost host outcome after real delivery")
        return {"tx_id":len(self.frames)}


def setup_node(timeout=0.2):
    node=Node();client=ChatterMachineClient(node.send,presentation_timeout_s=timeout);node.client=client
    return client,node


def test_acceptance_and_physical_tx_do_not_settle_link():
    client,node=setup_node();node.drop_link=True
    ticket=client.submit_binary(b"opaque")
    assert ticket.outcome == Kind.TX_DONE
    assert len(client.pending)==1
    assert client.settle_binary(ticket).tx_id is not None
    assert [f.kind for f in node.frames].count(Kind.SUBMIT)==1
    assert [f.kind for f in node.frames].count(Kind.QUERY)==1
    client.close()


def test_unknown_blocks_replay_and_keeps_old_identity():
    client,node=setup_node();node.drop_link=True;node.unknown=True
    ticket=client.submit_binary(b"FT1 bytes")
    with pytest.raises(BinaryUserError,match="no retained") as caught: client.settle_binary(ticket)
    assert caught.value.code=="local_tx_unsettled"
    assert client.pending[ticket.request] is ticket
    # Даже API другой submission не должен обходить unresolved UNKNOWN.
    with pytest.raises(BinaryUserError): client.send_binary(b"more")
    assert [f.kind for f in node.frames].count(Kind.SUBMIT)==1
    client.close()


def test_ambiguous_host_write_queries_without_second_rf():
    client,node=setup_node();node.write_unknown=True;node.drop_link=True
    result=client.send_binary(b"FT1 bytes")
    assert result.tx_id is None
    assert [f.kind for f in node.frames].count(Kind.SUBMIT)==1
    assert [f.kind for f in node.frames].count(Kind.QUERY)==1
    assert not client.pending
    client.close()


def test_two_slot_bound_and_old_epoch_cannot_settle():
    client,node=setup_node();node.drop_link=True
    first=client.submit_binary(b"one");second=client.submit_binary(b"two")
    with pytest.raises(BinaryUserError) as caught: client.submit_binary(b"three")
    assert caught.value.code=="binary_pipeline_full"
    client.feed_line("chat",encode(Frame(Kind.LINK_OK,first.epoch-1,first.request)).decode())
    assert first.outcome==Kind.TX_DONE
    client.feed_line("chat",encode(Frame(Kind.LINK_OK,first.epoch,first.request)).decode())
    client.settle_binary(first)
    client.feed_line("chat",encode(Frame(Kind.LINK_OK,second.epoch,second.request)).decode())
    client.settle_binary(second);client.close()


def test_machine_rx_deduplicates_human_presentation_and_checks_crc():
    client,node=setup_node();client._ready(time.monotonic()+1)
    received=[];client.set_receiver(received.append)
    rx=encode(Frame(Kind.RX,node.epoch,0,b"opaque"))
    client.feed_line("chat",rx.decode())
    client.feed_line("chat","< [0/0 Q0] [BINARY] b3BhcXVl")
    client.feed_line("chat",rx.decode().replace("/m1 ","/m1 !"))
    assert received==[b"opaque"]
    assert client.parse_errors==1;client.close()


def test_legacy_requires_explicit_rejection():
    client,node=setup_node();node.legacy=True;client._ready(time.monotonic()+1)
    assert client.mode=="legacy";client.close()


def test_negotiation_silence_is_not_legacy_fallback():
    client=ChatterMachineClient(lambda text:None,presentation_timeout_s=0.1)
    with pytest.raises(BinaryUserError) as caught: client._ready(time.monotonic()+0.02)
    assert caught.value.code=="machine_negotiation_timeout"
    assert client.mode!="legacy";client.close()


def test_close_waits_for_addressed_closed_and_never_cancels_outstanding():
    client,node=setup_node();client._ready(time.monotonic()+1)
    client.close()
    assert client.close_acknowledged
    assert node.frames[-1].kind==Kind.CLOSE
    client,node=setup_node();node.drop_link=True
    client.submit_binary(b"pending")
    client.close()
    assert all(frame.kind!=Kind.CLOSE for frame in node.frames)
    assert len(client.pending)==1


def test_new_epoch_after_reconnect_invalidates_tickets_without_false_success():
    generation=[1];node=Node()
    client=ChatterMachineClient(node.send,presentation_timeout_s=0.3,connection_generation=lambda:generation[0])
    node.client=client;node.drop_link=True
    old=client.submit_binary(b"same FT1 message")
    generation[0]=2;node.epoch=42
    with pytest.raises(BinaryUserError) as caught: client.settle_binary(old)
    assert caught.value.code=="local_disconnect"
    client.discard_binary_pipeline()
    assert not client.pending and client.epoch==42
    node.drop_link=False
    assert client.send_binary(b"same FT1 message").tx_id is not None
    assert [f.kind for f in node.frames].count(Kind.SUBMIT)==2
    client.close()


def test_same_epoch_reconnect_keeps_unresolved_guard():
    generation=[1];node=Node()
    client=ChatterMachineClient(node.send,presentation_timeout_s=0.3,connection_generation=lambda:generation[0])
    node.client=client;node.drop_link=True
    ticket=client.submit_binary(b"old")
    generation[0]=2
    with pytest.raises(BinaryUserError) as caught: client.discard_binary_pipeline()
    assert caught.value.code=="local_tx_unsettled"
    assert client.pending[ticket.request] is ticket
    assert [f.kind for f in node.frames].count(Kind.SUBMIT)==1
    client.close()


def test_observed_reset_allows_pipeline_discard_before_ready():
    client,node=setup_node();node.drop_link=True
    client.submit_binary(b"old")
    client.feed_line("chat","ESP-ROM:esp32s3")
    client.discard_binary_pipeline()
    assert not client.pending and client.mode=="failed"
    assert client.error.code=="local_controller_reset"
    assert [f.kind for f in node.frames].count(Kind.SUBMIT)==1
    client.close()


def test_hello_busy_retries_only_local_control_before_deadline():
    node=Node();calls=[0]
    def send(text):
        frame=decode(text.lstrip("\n"))
        if frame.kind==Kind.HELLO and calls[0]==0:
            calls[0]+=1;node.frames.append(frame)
            client.feed_line("chat",encode(Frame(Kind.REJECTED,0,frame.request,b"\x01")).decode())
            return {"tx_id":1}
        return node.send(text)
    client=ChatterMachineClient(send,presentation_timeout_s=0.4);node.client=client
    client._ready(time.monotonic()+0.4)
    assert client.mode=="machine" and len(node.frames)==2
    assert all(frame.kind==Kind.HELLO for frame in node.frames)
    client.close()


def test_cancel_interrupts_negotiation_without_rf_submission():
    import threading
    from serialterminal.file_transfer.transport import BinaryUserCancelled
    cancel=threading.Event();lines=[]
    client=ChatterMachineClient(lambda line:lines.append(line))
    timer=threading.Timer(0.01,cancel.set);timer.start()
    started=time.monotonic()
    try:
        with pytest.raises(BinaryUserCancelled):
            client.send_binary_until(b"never RF",deadline=started+1,cancel_event=cancel)
        assert time.monotonic()-started<0.3
        assert all(decode(line.lstrip("\n")).kind==Kind.HELLO for line in lines)
    finally: timer.join();client.close()


def test_idle_receiver_reconnect_restores_machine_rx_without_file_send():
    generation=[1];node=Node()
    client=ChatterMachineClient(node.send,connection_generation=lambda:generation[0])
    node.client=client;received=[];client.set_receiver(received.append);client.start()
    deadline=time.monotonic()+1
    while client.mode!="machine" and time.monotonic()<deadline: time.sleep(0.01)
    assert client.mode=="machine"
    generation[0]=2;node.epoch=42
    deadline=time.monotonic()+1
    while client.epoch!=42 and time.monotonic()<deadline: time.sleep(0.01)
    assert client.epoch==42
    client.feed_line("chat",encode(Frame(Kind.RX,42,0,b"after reconnect")).decode())
    assert received==[b"after reconnect"]
    assert all(frame.kind==Kind.HELLO for frame in node.frames)
    client.close();assert not client.start_thread.is_alive()


def test_lifecycle_monitor_does_not_rotate_epoch_with_pending_ticket():
    generation=[1];node=Node()
    client=ChatterMachineClient(node.send,connection_generation=lambda:generation[0])
    node.client=client;client.start()
    deadline=time.monotonic()+1
    while client.mode!="machine" and time.monotonic()<deadline: time.sleep(0.01)
    node.drop_link=True;ticket=client.submit_binary(b"pending")
    generation[0]=2;node.epoch=42
    time.sleep(0.25)
    assert client.epoch==41 and client.pending[ticket.request] is ticket
    assert sum(frame.kind==Kind.HELLO for frame in node.frames)==1
    client.close();assert not client.start_thread.is_alive()


def test_drain_queries_lost_terminal_outcomes_without_rf_replay():
    client,node=setup_node();node.drop_link=True
    client.submit_binary(b"one");client.submit_binary(b"two")
    client.drain_binary(0.3)
    assert not client.pending
    assert [frame.kind for frame in node.frames].count(Kind.SUBMIT)==2
    assert [frame.kind for frame in node.frames].count(Kind.QUERY)==2
    client.close()


def test_lost_outcome_with_addressed_returned_credit_queries_without_30_second_stall():
    client,node=setup_node(timeout=30);node.drop_link=True
    ticket=client.submit_binary(b"delivered")
    client.feed_line("chat",encode(Frame(Kind.STATUS,ticket.epoch,ticket.request,b"\x02"+struct.pack("<IIB",1,0,1))).decode())
    started=time.monotonic()
    assert client.settle_binary(ticket).tx_id is not None
    assert time.monotonic()-started < 1.0
    assert [f.kind for f in node.frames].count(Kind.SUBMIT)==1
    assert [f.kind for f in node.frames].count(Kind.QUERY)==1
    client.close()


def test_credit_status_never_completes_ticket_or_queries_unrelated_request():
    client,node=setup_node(timeout=30);node.drop_link=True
    ticket=client.submit_binary(b"pending")
    for request,credit in [(ticket.request-1,2),(ticket.request,1)]:
        client.feed_line("chat",encode(Frame(Kind.STATUS,ticket.epoch,request,bytes([credit])+struct.pack("<IIB",0,0,1))).decode())
    assert ticket.credit_returned_at is None
    assert ticket.outcome==Kind.TX_DONE
    assert client.pending[ticket.request] is ticket
    assert all(frame.kind!=Kind.QUERY for frame in node.frames)
    client.feed_line("chat",encode(Frame(Kind.LINK_OK,ticket.epoch,ticket.request)).decode())
    client.settle_binary(ticket)
    assert all(frame.kind!=Kind.QUERY for frame in node.frames)
    client.close()


def test_later_ticket_full_credit_status_recovers_earlier_lost_outcome():
    client,node=setup_node(timeout=30);node.drop_link=True
    first=client.submit_binary(b"earlier")
    node.drop_link=False
    second=client.submit_binary(b"later")
    client.feed_line("chat",encode(Frame(Kind.STATUS,second.epoch,second.request,b"\x02"+struct.pack("<IIB",1,0,2))).decode())
    started=time.monotonic()
    client.settle_binary(first);client.settle_binary(second)
    assert time.monotonic()-started < 1.0
    assert [frame.request for frame in node.frames if frame.kind==Kind.QUERY]==[first.request]
    assert [f.kind for f in node.frames].count(Kind.SUBMIT)==2
    client.close()


def test_idle_same_epoch_reconnect_keeps_monotonic_request_counter():
    generation=[1];node=Node()
    client=ChatterMachineClient(node.send,presentation_timeout_s=0.3,connection_generation=lambda:generation[0])
    node.client=client
    client.send_binary(b"first")
    generation[0]=2
    client.send_binary(b"different new payload")
    submits=[frame for frame in node.frames if frame.kind==Kind.SUBMIT]
    assert [(frame.epoch,frame.request) for frame in submits]==[(41,1),(41,2)]
    assert submits[0].payload!=submits[1].payload
    assert len([frame for frame in node.frames if frame.kind==Kind.HELLO])==2
    client.close()

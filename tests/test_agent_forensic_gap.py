import threading

from serialterminal.agent import SessionManager
from serialterminal.runlog import RunLog
from serialterminal.session import ManagedSession
from serialterminal.transports.base import Transport


class _Transport(Transport):
    @property
    def is_connected(self):
        return False

    @property
    def description(self):
        return "gap-test"

    def connect(self):
        return False

    def disconnect(self):
        pass

    def read(self, size=512):
        return b""

    def write(self, data):
        pass


def test_forensic_log_marks_event_ring_overrun_before_retained_events(tmp_path):
    session = ManagedSession(_Transport(), event_limit=2)
    for index in range(1, 5):
        session._record_event("state", state=f"test-{index}")

    raw_path = tmp_path / "agent.log"
    stop_event = threading.Event()
    stop_event.set()
    with RunLog(raw_path) as run_log:
        manager = SessionManager(run_log=run_log)
        manager._event_logger_loop("s1", session, stop_event)

    forensic = raw_path.read_text()
    gap = forensic.index('"event":"forensic_gap"')
    seq3 = forensic.index('"seq":3')
    seq4 = forensic.index('"seq":4')
    assert gap < seq3 < seq4
    assert '"session":"s1"' in forensic
    assert '"last_logged_seq":0' in forensic
    assert '"next_logged_seq":3' in forensic
    assert '"lost_seq_first":1' in forensic
    assert '"lost_seq_last":2' in forensic


def test_contiguous_forensic_events_do_not_emit_gap_marker(tmp_path):
    raw_path = tmp_path / "agent.log"
    with RunLog(raw_path) as run_log:
        run_log.record("STATE", {"session": "s1", "seq": 1, "state": "one"})
        run_log.record("RX main", {"session": "s1", "seq": 2, "text": "two"})
        run_log.record("TX", {"session": "s1", "seq": 3, "tx_id": 1})

    assert '"event":"forensic_gap"' not in raw_path.read_text()

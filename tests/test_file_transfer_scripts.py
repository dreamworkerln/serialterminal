import base64
import hashlib
import json
from pathlib import Path
import runpy
import struct

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


def test_runner_without_execute_has_no_side_effects(tmp_path, capsys):
    runner = load('run_file_transfer.py')
    assert runner['main'](['--transport', 'usb', '--sender-key', 'serial:a',
                           '--receiver-key', 'serial:b', '--journal-root', str(tmp_path / 'journal')]) == 0
    assert not list(tmp_path.iterdir())
    assert json.loads(capsys.readouterr().out)['execute'] is False


def test_analyzer_reads_all_four_logs_from_run_root(tmp_path):
    analyzer = load('analyze_file_transfer.py')
    (tmp_path / 'serialterminal.log').write_text('')
    (tmp_path / 'serialterminal.console.log').write_text('2026-10-17T00:00:00+00:00 [s1] [O] READY\n')
    (tmp_path / 'serialterminal.fttiming.jsonl').write_text(json.dumps({
        'segment_id': 'first', 'seq': 1, 'event': 'run_stop',
    }) + '\n')
    (tmp_path / 'serialterminal.application.log').write_text(
        '[INFO] START pid=1\n[ERROR] simulated application failure\n[INFO] STOP\n'
    )
    report = analyzer['analyze'](tmp_path, decode=False)
    assert report['application'] == {'errors': 1, 'started': True, 'stopped': True}
    assert report['console_records'] == {'s1/O': 1}
    assert not any('missing serialterminal' in gap for gap in report['evidence_gaps'])
    assert any('application errors' in gap for gap in report['evidence_gaps'])
    assert all(Path(name).parent == Path('.') for name in report['st_logs'].values())
    assert report['outcome'] != 'PASS'


def test_analyzer_reports_missing_four_logs(tmp_path):
    report = load('analyze_file_transfer.py')['analyze'](tmp_path, decode=False)
    for name in ('serialterminal.log', 'serialterminal.console.log',
                 'serialterminal.fttiming.jsonl', 'serialterminal.application.log'):
        assert f'missing {name}' in report['evidence_gaps']


def test_ble_fragment_reassembly_and_exact_payload_correlation(tmp_path):
    analyzer = load('analyze_file_transfer.py')
    payload = b'notification from node\n'
    att = b'\x1b\x12\x00' + payload
    l2cap = struct.pack('<HH', len(att), 4) + att
    fragments = [struct.pack('<HH', 0x2040, 8) + l2cap[:8],
                 struct.pack('<HH', 0x1040, len(l2cap) - 8) + l2cap[8:]]
    capture = tmp_path / 'ble.btsnoop'
    raw = b'btsnoop\0' + struct.pack('>II', 1, 2001)
    for fragment in fragments:
        raw += struct.pack('>IIIIQ', len(fragment), len(fragment), 5, 0, 0) + fragment
    capture.write_bytes(raw)
    gaps = []
    stats = analyzer['btsnoop_stats'](capture, gaps)
    assert gaps == []
    key = 'hci0/conn0x0040/att0x0012'
    assert stats['att_notifications'][key]['count'] == 1
    forensic = tmp_path / 'serialterminal.log'
    forensic.write_text('[stamp] [RX telemetry] ' + json.dumps({
        'session': 's1', 'stream': 'telemetry', 'seq': 1,
        'data_b64': base64.b64encode(payload).decode(),
    }) + '\n')
    rx = analyzer['forensic_stats'](forensic, gaps)
    candidates = analyzer['correlate_notifications'](stats, rx)
    assert candidates[key] == [{'stream': 's1/telemetry', 'identical_payloads': 1,
                                'capture_payloads_absent_from_stream': 0,
                                'stream_payloads_absent_from_capture': 0}]
    assert list(stats['att_notifications'][key]['payload_sha256_counts']) == [hashlib.sha256(payload).hexdigest()]


def test_usb_parser_and_truncation_are_explicit(tmp_path):
    analyzer = load('analyze_file_transfer.py')
    packet = bytearray(64)
    packet[8:12] = bytes([ord('C'), 3, 0x81, 7])
    struct.pack_into('<H', packet, 12, 2)
    struct.pack_into('<iII', packet, 28, 0, 10, 10)
    packet += b'0123456789'
    header = b'\xd4\xc3\xb2\xa1' + struct.pack('<HHiiii', 2, 4, 0, 0, 65535, 220)
    capture = tmp_path / 'usb.pcap'
    capture.write_bytes(header + struct.pack('<IIII', 0, 0, len(packet), len(packet)) + packet)
    gaps = []
    stats = analyzer['usb_stats'](capture, gaps)
    assert gaps == []
    assert stats['endpoints']['bus2/dev7/ep0x81/type3']['completed_urb_bytes'] == 10
    capture.write_bytes(capture.read_bytes()[:-1])
    analyzer['usb_stats'](capture, gaps)
    assert 'truncated pcap packet' in gaps


def test_runner_agent_writes_four_logs_for_offline_analyzer(tmp_path):
    runner = load('run_file_transfer.py')
    analyzer = load('analyze_file_transfer.py')
    agent = runner['Agent'](tmp_path)
    result = agent.close()
    assert result == {'returncode': 0, 'forced': False}
    report = analyzer['analyze'](tmp_path, decode=False)
    for filename in report['st_logs'].values():
        assert (tmp_path / filename).is_file()
    assert not (tmp_path / 'logs').exists()
    assert not any(gap.startswith('missing serialterminal') for gap in report['evidence_gaps'])
    assert report['application'] == {'errors': 0, 'started': True, 'stopped': True}


@pytest.mark.parametrize('fault', [None, 'receiver', 'sha256', 'settling'])
def test_transfer_loop_reports_progress_and_verifies_final_file(tmp_path, capsys, monkeypatch, fault):
    runner = load('run_file_transfer.py')
    preflight_calls = []
    monkeypatch.setattr(runner['time'], 'sleep', lambda _: None)
    monkeypatch.setitem(runner['transfer'].__globals__, 'prepare_radios', lambda *args: preflight_calls.append(True))
    (tmp_path / 'sent').mkdir()
    (tmp_path / 'received').mkdir()
    source = tmp_path / 'sent' / 'test.bin'
    destination = tmp_path / 'received' / 'test.bin'
    source.write_bytes(b'exact file content')
    destination.write_bytes(source.read_bytes() if fault != 'sha256' else b'corrupted file')
    args = runner['parser']().parse_args([
        '--transport', 'usb', '--sender-key', 'serial:a', '--receiver-key', 'serial:b',
    ])
    class FakeAgent:
        def __init__(self):
            self.steps = iter([12, 18, 25, 10, 100])
            self.progress = {}
            self.close_attempts = 0
        def request(self, op, **fields):
            if op == 'discover':
                return {'devices': [{'key': key, 'kind': 'serial'} for key in ('serial:a', 'serial:b')]}
            if op == 'open':
                return {'session': fields['device_key'], 'state': 'connected'}
            if op == 'file_send_start':
                return {'transfer_id': 't1', 'state': 'compressing', 'percentage': 99.9, 'wire_bytes': 0}
            if op == 'file_transfer_observe':
                if fields['session'] == 'serial:b':
                    incoming = {**self.progress, 'final_path': str(destination)}
                    if fault == 'receiver':
                        incoming.update(state='failed', failure={'code': 'storage_failed'})
                    return {'cursor': fields['cursor'] + 1, 'progress': incoming}
                value = next(self.steps)
                self.progress = {'transfer_id': 't1', 'percentage': value, 'wire_bytes': 1000, 'bytes_completed': value * 10,
                                 'state': 'completed' if value == 100 else 'sending'}
                return {'cursor': fields['cursor'] + 1, 'progress': self.progress}
            if op == 'status':
                return {'file_transfer': {**self.progress, 'final_path': str(destination)}}
            if op == 'file_transfer_close':
                self.close_attempts += 1
                if fault == 'settling' and self.close_attempts == 1:
                    raise runner['AgentRequestError'](op, {'code': 'file_transfer_active'})
            assert op in ('file_transfer_close', 'close')
            return {}
    summary = {'source': runner['fingerprint'](source)}
    if fault in ('receiver', 'sha256'):
        with pytest.raises(RuntimeError, match='receiver transfer failed' if fault == 'receiver' else 'SHA-256 mismatch'):
            runner['transfer'](FakeAgent(), args, source, summary, [])
        assert 'итог=PASS' not in capsys.readouterr().out
        rows = [json.loads(line) for line in (tmp_path / 'progress.jsonl').read_text().splitlines()]
        assert not any(row['verified'] for row in rows)
        return
    runner['transfer'](FakeAgent(), args, source, summary, [])
    assert summary['outcome'] == 'PASS'
    assert preflight_calls == [True]
    lines = capsys.readouterr().out.splitlines()
    assert 'TX 0.0% [сжатие] | RX --% [ожидание META]' in lines[1]
    assert any('TX 25.0%' in line and 'RX 25.0%' in line for line in lines)
    assert 'итог=PASS SHA256=OK' in lines[-1]
    rows = [json.loads(line) for line in (tmp_path / 'progress.jsonl').read_text().splitlines()]
    assert rows[-1]['verified'] is True
    assert rows[-1]['TX']['state'] == rows[-1]['RX']['state'] == 'completed'



def test_capture_preflight_uses_configured_usbmon_without_sudo(tmp_path, monkeypatch):
    runner = load('run_file_transfer.py')
    args = runner['parser']().parse_args([
        '--transport', 'usb', '--sender-key', 'serial:a', '--receiver-key', 'serial:b',
    ])
    assert args.usbmon_interface == 'usbmon0'
    monkeypatch.setattr(runner['shutil'], 'which', lambda name: '/usr/bin/' + name)
    with pytest.raises(RuntimeError, match='device missing'):
        runner['capture_preflight'](args, tmp_path, device_root=tmp_path)
    (tmp_path / 'usbmon0').touch()
    runner['capture_preflight'](args, tmp_path, device_root=tmp_path)
    commands = runner['capture_commands'](args, tmp_path)
    assert commands[0][1][:3] == ['tcpdump', '-i', 'usbmon0']
    monkeypatch.setattr(runner['os'], 'access', lambda path, mode: False)
    with pytest.raises(RuntimeError, match='not readable'):
        runner['capture_preflight'](args, tmp_path, device_root=tmp_path)


def test_capture_preflight_reports_missing_tools_but_no_capture_needs_none(tmp_path, monkeypatch):
    runner = load('run_file_transfer.py')
    args = runner['parser']().parse_args([
        '--transport', 'ble', '--sender-key', 'ble:a', '--receiver-key', 'ble:b',
    ])
    monkeypatch.setattr(runner['shutil'], 'which', lambda name: None)
    with pytest.raises(RuntimeError, match='btmon'):
        runner['capture_preflight'](args, tmp_path)
    args.capture = 'none'
    runner['capture_preflight'](args, tmp_path)

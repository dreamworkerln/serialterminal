"""Парные статусы ROOT без аппаратуры и без чтения сырых логов."""
import json
from pathlib import Path
import runpy

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load():
    return runpy.run_path(str(ROOT / 'scripts' / 'run_file_transfer.py'))


def snapshot(done=0, *, state='sending', transfer_id='root', total=1000, **extra):
    return dict(transfer_id=transfer_id, state=state, wire_bytes=total, bytes_completed=done,
                chunks_total=100, chunks_completed=done // 10, **extra)


def test_independent_tx_rx_thresholds_and_silent_repeated_samples(tmp_path, capsys):
    now = [0.0]
    monitor = load()['TransferMonitor']('root', tmp_path / 'progress.jsonl', clock=lambda: now[0])
    monitor.update(snapshot(), snapshot(state='receiving'))
    capsys.readouterr()
    for step in range(1, 10):
        monitor.update(snapshot(step), snapshot(step, state='receiving'))
    assert capsys.readouterr().out == ''
    monitor.update(snapshot(400), snapshot(270, state='receiving'))
    text = capsys.readouterr().out
    assert 'TX 40.0% [передача]' in text
    assert 'RX 27.0% [приём]' in text
    assert 'Δ=+13.0п.п.' in text
    monitor.update(snapshot(450), snapshot(300, state='receiving'))
    assert 'RX 30.0%' in capsys.readouterr().out
    monitor.update(snapshot(450), snapshot(300, state='receiving'))
    assert capsys.readouterr().out == ''
    for step in (50, 60, 70, 80, 90):
        monitor.update(snapshot(step * 10), snapshot(300, state='receiving'))
        assert f'TX {step}.0%' in capsys.readouterr().out
    rows = [json.loads(line) for line in (tmp_path / 'progress.jsonl').read_text().splitlines()]
    assert rows[1]['delta']['bytes'] == 130
    assert not rows[-1]['verified']


def test_compression_and_unrelated_receive_are_not_data_progress(tmp_path, capsys):
    monitor = load()['TransferMonitor']('root', tmp_path / 'progress.jsonl')
    monitor.update(snapshot(1000, state='compressing'), snapshot(1000, state='completed', transfer_id='old'))
    text = capsys.readouterr().out
    assert 'TX 0.0% [сжатие]' in text
    assert 'RX --% [ожидание META]' in text
    assert 'Δ' not in text
    row = json.loads((tmp_path / 'progress.jsonl').read_text())
    assert row['RX'] is None


def test_phase_repair_and_transient_events_visible_without_new_percent(tmp_path, capsys):
    monitor = load()['TransferMonitor']('root', tmp_path / 'progress.jsonl')
    monitor.update(snapshot(1000, state='waiting_result'), snapshot(800, state='receiving'))
    capsys.readouterr()
    rx = snapshot(800, state='repair_requested', repair={'missing_total': 20, 'depth': 0, 'no_progress': 1})
    tx = snapshot(1000, state='waiting_result')
    events = {'TX': [{'kind': 'state', 'state': 'repairing'}, {'kind': 'repair_round_sent'},
                     {'kind': 'state', 'state': 'waiting_result'}]}
    monitor.update(tx, rx, events=events)
    text = capsys.readouterr().out
    assert 'TX 99.9% [ожидание RESULT]' in text
    assert 'RX 80.0% [запрос repair]' in text
    assert 'запрошено=20,depth=0,без_улучшения=1' in text
    assert 'repair/доставка→доставка отправлена→ожидание RESULT' in text
    monitor.update(tx, rx)
    assert capsys.readouterr().out == ''
    monitor.update(tx, {**rx, 'repair': {**rx['repair'], 'no_progress': 2}})
    assert 'без_улучшения=2' in capsys.readouterr().out


def test_elapsed_time_alone_never_emits_but_phase_and_verification_do(tmp_path, capsys):
    now = [0.0]
    monitor = load()['TransferMonitor']('root', tmp_path / 'progress.jsonl', clock=lambda: now[0])
    tx, rx = snapshot(1000, state='waiting_result'), snapshot(900, state='repair_requested')
    monitor.update(tx, rx)
    capsys.readouterr()
    now[0] = 9.0
    monitor.update(tx, rx)
    assert capsys.readouterr().out == ''
    now[0] = 10.0
    monitor.update(tx, rx)
    assert capsys.readouterr().out == ''
    now[0] = 3600.0
    monitor.update(tx, rx)
    assert capsys.readouterr().out == ''
    monitor.update(snapshot(1000, state='repairing'), rx)
    text = capsys.readouterr().out
    assert 'repair/доставка' in text
    assert 'прогресс DATA не менялся 3600с' in text
    done = snapshot(1000, state='completed')
    monitor.update(done, done)
    assert 'PASS' not in capsys.readouterr().out
    monitor.update(done, done, verified=True)
    assert 'итог=PASS SHA256=OK' in capsys.readouterr().out
    monitor.update(done, done, verified=True)
    assert capsys.readouterr().out == ''


def test_percent_regression_is_immediately_visible_not_hidden_by_highwater(tmp_path, capsys):
    now = [0.0]
    monitor = load()['TransferMonitor']('root', tmp_path / 'progress.jsonl', clock=lambda: now[0])
    monitor.update(snapshot(800), snapshot(700, state='receiving'))
    capsys.readouterr()
    monitor.update(snapshot(200), snapshot(100, state='receiving'))
    assert 'RX 10.0%' in capsys.readouterr().out
    now[0] = 10.0
    monitor.update(snapshot(200), snapshot(100, state='receiving'))
    assert capsys.readouterr().out == ''


def test_different_totals_do_not_produce_a_loss_estimate(tmp_path, capsys):
    monitor = load()['TransferMonitor']('root', tmp_path / 'progress.jsonl')
    monitor.update(snapshot(500), snapshot(300, total=900, state='receiving'))
    assert 'Δ недоступна: различаются wire_bytes' in capsys.readouterr().out


def test_both_observe_event_backlogs_are_drained_and_keep_current_snapshot():
    runner = load()
    calls = []
    class Agent:
        def request(self, op, **fields):
            calls.append(fields)
            cursor = fields['cursor'] + 100
            return {'cursor': cursor, 'head_cursor': 300,
                    'progress': snapshot(cursor), 'events': [{'kind': 'state', 'state': 'repairing'}]}
    result, events, warnings = runner['observe_transfer'](Agent(), 'rx', 'root', 0, {}, 'RX')
    assert [call['cursor'] for call in calls] == [0, 100, 200]
    assert all(call['session'] == 'rx' and call['transfer_id'] == 'root' for call in calls)
    assert result['progress']['bytes_completed'] == 300
    assert len(events) == 3 and not warnings


def test_expired_event_history_is_reported_and_current_progress_continues():
    runner = load()
    cursors = []
    class Agent:
        def request(self, op, **fields):
            cursors.append(fields['cursor'])
            if len(cursors) == 1:
                raise runner['AgentRequestError'](op, {
                    'code': 'file_cursor_expired', 'details': {'oldest_valid_cursor': 100, 'head_cursor': 105},
                })
            return {'cursor': 105, 'head_cursor': 105, 'progress': snapshot(800), 'events': []}
    summary = {}
    result, _, warnings = runner['observe_transfer'](Agent(), 'rx', 'root', 0, summary, 'RX')
    assert cursors == [0, 100]
    assert summary['monitor_event_gaps'][0]['role'] == 'RX'
    assert warnings and result['progress']['bytes_completed'] == 800


def test_unrelated_api_failure_is_not_masked():
    runner = load()
    class Agent:
        def request(self, op, **fields):
            raise runner['AgentRequestError'](op, {'code': 'unknown_session'})
    with pytest.raises(RuntimeError, match='unknown_session'):
        runner['observe_transfer'](Agent(), 'rx', 'root', 0, {}, 'RX')


@pytest.mark.parametrize('fail_transfer', [False, True])
def test_run_stdout_is_mirrored_in_run_folder_including_analyzer(tmp_path, capsys, monkeypatch, fail_transfer):
    runner = load()
    scope = runner['main'].__globals__
    monkeypatch.setitem(scope, 'checkpoint', lambda: {})
    class Agent:
        def __init__(self, run):
            pass
        def close(self):
            return {'returncode': 0, 'forced': False}
    monkeypatch.setitem(scope, 'Agent', Agent)
    def transfer(agent, args, source, summary, captures):
        print('TX 40% | RX 30%', flush=True)
        if fail_transfer:
            raise RuntimeError('simulated transfer failure')
        summary['outcome'] = 'PASS'
    monkeypatch.setitem(scope, 'transfer', transfer)
    def analyze(command, **options):
        assert command[1].endswith('analyze_file_transfer.py')
        assert options == {'text': True, 'capture_output': True}
        return runner['subprocess'].CompletedProcess(command, 0, stdout='{"outcome":"test"}\n', stderr='diagnostic')
    monkeypatch.setattr(runner['subprocess'], 'run', analyze)
    result = runner['main'](['--transport', 'usb', '--sender-key', 'a', '--receiver-key', 'b',
                             '--capture', 'none', '--size', '1024', '--journal-root', str(tmp_path), '--execute'])
    run, = tmp_path.iterdir()
    output = capsys.readouterr().out
    assert (run / 'runner.stdout.log').read_text() == output
    assert output == f'{run}\nTX 40% | RX 30%\n{{"outcome":"test"}}\n'
    assert (run / 'analyzer.stderr.log').read_text() == 'diagnostic'
    assert result == (1 if fail_transfer else 0)
    if fail_transfer:
        assert 'simulated transfer failure' in (run / 'runner.application.log').read_text()


def test_repeated_phase_cycles_keep_chronology_but_stdout_is_bounded(tmp_path, capsys):
    monitor = load()['TransferMonitor']('root', tmp_path / 'progress.jsonl')
    events = {'TX': [{'kind': 'state', 'state': state}
                     for _ in range(10) for state in ('waiting_result', 'repairing')]}
    monitor.update(snapshot(1000, state='repairing'), events=events)
    text = capsys.readouterr().out
    assert 'фазы=…→' in text
    assert text.count('→') == 8
    row = json.loads((tmp_path / 'progress.jsonl').read_text())
    assert row['activities']['TX'] == ['ожидание RESULT', 'repair/доставка'] * 10


def test_runner_with_real_ft1_managers_reports_loss_and_recursive_repair(tmp_path, capsys, monkeypatch):
    """Настоящие FT1 workers; виртуальная линия теряет каждый пятый ROOT DATA."""
    import time
    from types import SimpleNamespace
    from serialterminal.file_transfer import (
        BinarySendReceipt, DataMessage, FileTransferManager, MetaMessage, decode_message,
    )

    runner = load()
    scope = runner['transfer'].__globals__
    monkeypatch.setitem(scope, 'prepare_radios', lambda *args: None)
    monkeypatch.setitem(scope, 'time', SimpleNamespace(
        monotonic=time.monotonic, sleep=lambda seconds: time.sleep(min(seconds, .02)),
    ))

    class Link:
        payload_capacity = 243
        def __init__(self, *, loss=False):
            self.loss = loss
            self.receiver = None
            self.peer = None
            self.root_id = None
            self.dropped = set()
            self.sent = 0
        def set_receiver(self, receiver):
            self.receiver = receiver
        def send_binary(self, payload, *, cancel_event=None):
            message = decode_message(payload)
            self.sent += 1
            if isinstance(message, MetaMessage) and message.depth == 0:
                self.root_id = message.transfer_id
            if isinstance(message, DataMessage) and message.transfer_id == self.root_id:
                time.sleep(.005)
                if self.loss and message.chunk_index % 5 == 0 and message.chunk_index not in self.dropped:
                    self.dropped.add(message.chunk_index)
                    return BinarySendReceipt(tx_id=self.sent)
            self.peer.receiver(bytes(payload))
            return BinarySendReceipt(tx_id=self.sent)

    left, right = Link(loss=True), Link()
    left.peer, right.peer = right, left
    tx = FileTransferManager(left, receive_dir=tmp_path / 'sender', result_timeout_s=2)
    rx = FileTransferManager(right, receive_dir=tmp_path / 'received', result_timeout_s=2)
    (tmp_path / 'sent').mkdir()
    source = tmp_path / 'sent' / 'payload.bin'
    runner['make_payload'](source, 65536)
    args = runner['parser']().parse_args([
        '--transport', 'usb', '--sender-key', 'serial:a', '--receiver-key', 'serial:b', '--timeout', '15',
    ])
    class Agent:
        def request(self, op, **fields):
            if op == 'discover':
                return {'devices': [{'key': key, 'kind': 'serial'} for key in ('serial:a', 'serial:b')]}
            if op == 'open':
                return {'session': fields['device_key'], 'state': 'connected'}
            manager = tx if fields.get('session') == 'serial:a' else rx
            if op == 'file_send_start':
                return manager.start_send(fields['path'])
            if op == 'file_transfer_observe':
                return manager.observe(fields['transfer_id'], cursor=fields['cursor'],
                                       window=fields['window'], timeout_ms=fields['timeout_ms'])
            if op == 'status':
                return {'state': 'connected', 'file_transfer': manager.display_snapshot()}
            if op == 'file_transfer_close':
                return manager.close_transfer(fields['transfer_id'])
            assert op == 'close'
            manager.close()
            return {}
    summary = {'source': runner['fingerprint'](source), 'validation': 'software FT1 pair; not USB/BLE hardware'}
    try:
        with (tmp_path / 'runner.stdout.log').open('w') as output:
            with runner['redirect_stdout'](runner['RunStdout'](__import__('sys').stdout, output)):
                runner['transfer'](Agent(), args, source, summary, [])
        rows = [json.loads(line) for line in (tmp_path / 'progress.jsonl').read_text().splitlines()]
        paired = [row for row in rows if row['TX'] and row['RX'] and row['delta']]
        initial = [row for row in paired if row['TX']['state'] == 'sending']
        assert len(initial) >= 8
        assert max(row['delta']['percentage_points'] for row in initial) > 15
        assert all(row['RX']['direction'] == 'RX' and row['TX']['direction'] == 'TX' for row in paired)
        assert any(0 < row['TX']['bytes_completed'] < row['TX']['wire_bytes'] for row in paired)
        assert any(0 < row['RX']['bytes_completed'] < row['RX']['wire_bytes'] for row in paired)
        repair_seen = any('repair' in str(row['activities']) or row['RX'].get('repair') for row in paired)
        assert repair_seen
        assert rows[-1]['verified'] and rows[-1]['delta']['bytes'] == 0
        assert summary['outcome'] == 'PASS'
        assert summary['source']['sha256'] == summary['received']['sha256']
        text = capsys.readouterr().out
        assert text == (tmp_path / 'runner.stdout.log').read_text()
        assert len(text.splitlines()) < 240
        report = {
            'outcome': 'PASS', 'kind': 'software FT1 pair with real workers and intentional loss',
            'file_bytes': 65536, 'dropped_once_root_chunks': len(left.dropped),
            'paired_observations': len(paired), 'stdout_lines': len(text.splitlines()),
            'max_observed_difference_pp': max(row['delta']['percentage_points'] for row in paired),
            'repair_visible': bool(repair_seen), 'final_verified': rows[-1]['verified'],
            'file_sha256': summary['received']['sha256'],
        }
        (tmp_path / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    finally:
        tx.close()
        rx.close()


@pytest.mark.parametrize('flag', ['--timeout', '--scan-seconds'])
@pytest.mark.parametrize('value', ['nan', 'inf'])
def test_nonfinite_run_deadlines_rejected_before_any_side_effect(flag, value, tmp_path):
    runner = load()
    with pytest.raises(SystemExit) as exc:
        runner['main'](['--transport', 'usb', '--sender-key', 'a', '--receiver-key', 'b',
                        '--journal-root', str(tmp_path), flag, value])
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())


def test_settling_wait_is_bounded_and_only_retries_active(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    runner = load()
    now = [0.0]
    monkeypatch.setitem(runner['close_settled_transfer'].__globals__, 'time', SimpleNamespace(
        monotonic=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds)))
    calls = []
    class Agent:
        def request(self, op, **fields):
            calls.append((op, fields))
            raise runner['AgentRequestError'](op, {'code': 'file_transfer_active'})
    with pytest.raises(TimeoutError, match='deadline'):
        runner['close_settled_transfer'](Agent(), 's1', 'root', timeout=.25)
    assert .25 <= now[0] < .4
    assert len(calls) == 3
    assert capsys.readouterr().out.count('фаза=') == 1
    assert all(op == 'file_transfer_close' for op, _ in calls)


def test_observe_long_poll_and_api_timeout_respect_remaining_deadline(monkeypatch):
    from types import SimpleNamespace
    runner = load()
    monkeypatch.setitem(runner['request_budget'].__globals__, 'time', SimpleNamespace(monotonic=lambda: 10))
    calls = []
    class Agent:
        def request(self, op, **fields):
            calls.append(fields)
            return {'cursor': 0, 'head_cursor': 0, 'events': [], 'progress': snapshot()}
    runner['observe_transfer'](Agent(), 's1', 'root', 0, {}, 'TX', timeout_ms=1000, deadline=10.25)
    assert calls[0]['timeout'] == .25
    assert calls[0]['timeout_ms'] == 250
    with pytest.raises(TimeoutError):
        runner['observe_transfer'](Agent(), 's1', 'root', 0, {}, 'TX', timeout_ms=1000, deadline=10)
    assert len(calls) == 1


@pytest.mark.parametrize('fault, message', [
    ('sender_failed', 'sender transfer failed'), ('receiver_failed', 'receiver transfer failed'),
    ('disconnect', 'receiver disconnected'), ('stalled_rx', 'deadline exceeded'),
    ('missing_rx', 'deadline exceeded'),
])
def test_transfer_faults_never_print_pass_or_resend(tmp_path, monkeypatch, capsys, fault, message):
    from types import SimpleNamespace
    runner = load()
    scope = runner['transfer'].__globals__
    now = [0.0]
    monkeypatch.setitem(scope, 'time', SimpleNamespace(
        monotonic=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds)))
    monkeypatch.setitem(scope, 'prepare_radios', lambda *args: None)
    real_monitor = runner['TransferMonitor']
    monkeypatch.setitem(scope, 'TransferMonitor', lambda *args, **kwargs: real_monitor(*args, **kwargs, clock=lambda: now[0]))
    (tmp_path / 'sent').mkdir()
    source = tmp_path / 'sent' / 'input.bin'
    source.write_bytes(b'input')
    args = runner['parser']().parse_args([
        '--transport', 'usb', '--sender-key', 'serial:a', '--receiver-key', 'serial:b', '--timeout', '25'])
    calls = []
    class Agent:
        def request(self, op, **fields):
            calls.append(op)
            now[0] += .001
            if op == 'discover':
                return {'devices': [{'key': key, 'kind': 'serial'} for key in ('serial:a', 'serial:b')]}
            if op == 'open':
                return {'session': fields['device_key'], 'state': 'connected'}
            if op == 'file_send_start':
                return snapshot(state='preparing')
            incoming = snapshot(500, state='failed' if fault == 'receiver_failed' else 'receiving')
            if op == 'status':
                return {'state': 'disconnected' if fault == 'disconnect' else 'connected',
                        'file_transfer': None if fault == 'missing_rx' else incoming}
            assert op == 'file_transfer_observe'
            value = (snapshot(1000, state='failed' if fault == 'sender_failed' else 'waiting_result')
                     if fields['session'] == 'serial:a' else incoming)
            return {'cursor': 0, 'head_cursor': 0, 'events': [], 'progress': value}
    summary = {'source': runner['fingerprint'](source)}
    with pytest.raises((RuntimeError, TimeoutError), match=message):
        runner['transfer'](Agent(), args, source, summary, [])
    text = capsys.readouterr().out
    assert 'PASS' not in text
    assert calls.count('file_send_start') == 1
    assert 'file_transfer_close' not in calls
    assert source.read_bytes() == b'input'
    if fault in ('stalled_rx', 'missing_rx'):
        assert now[0] <= 25.02
        assert text.count('прогресс DATA не менялся') == 0
        assert calls.count('status') >= 20
        assert len(text.splitlines()) <= 3


@pytest.mark.parametrize('step', [1, 10])
def test_percent_step_independent_roles_jumps_and_resume(tmp_path, capsys, step):
    runner = load()
    monitor = runner['TransferMonitor']('root', tmp_path / 'progress.jsonl', step=step)
    tx, rx = snapshot(), snapshot(state='receiving')
    monitor.update(tx, rx)
    capsys.readouterr()
    monitor.update(snapshot(9), snapshot(9, state='receiving'))
    assert capsys.readouterr().out == ''
    value = 10 * step
    monitor.update(snapshot(value), snapshot(9, state='receiving'))
    assert f'TX {step}.0%' in capsys.readouterr().out
    monitor.update(snapshot(value), snapshot(value, state='receiving'))
    assert f'RX {step}.0%' in capsys.readouterr().out
    monitor.update(snapshot(value), snapshot(value, state='receiving'))
    assert capsys.readouterr().out == ''
    monitor.update(snapshot(value * 3), snapshot(value * 3, state='receiving'))
    jumped = capsys.readouterr().out.splitlines()
    assert len(jumped) == 1
    assert f'TX {step * 3}.0%' in jumped[0]
    monitor.update(snapshot(), snapshot(state='receiving'))
    capsys.readouterr()
    monitor.update(snapshot(value), snapshot(value, state='receiving'))
    assert f'TX {step}.0%' in capsys.readouterr().out
    rows = [json.loads(line) for line in (tmp_path / 'progress.jsonl').read_text().splitlines()]
    assert rows[-1]['TX']['bytes_completed'] == value
    assert rows[-1]['RX']['bytes_completed'] == value


def test_progress_step_default_and_override():
    runner = load()
    fields = ['--transport', 'usb', '--sender-key', 'a', '--receiver-key', 'b']
    assert runner['parser']().parse_args(fields).progress_step == 1
    assert runner['parser']().parse_args(fields + ['--progress-step', '10']).progress_step == 10


@pytest.mark.parametrize('step', ['0', '101'])
def test_invalid_progress_step_rejected_before_run(step, tmp_path):
    runner = load()
    with pytest.raises(SystemExit) as exc:
        runner['main'](['--transport', 'usb', '--sender-key', 'a', '--receiver-key', 'b',
                        '--progress-step', step, '--journal-root', str(tmp_path)])
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("outcome", ["PASS", "FAIL", "INCONCLUSIVE"])
def test_skip_analysis_never_runs_parser_and_preserves_runner_verdict(tmp_path, monkeypatch, outcome):
    runner = load()
    scope = runner["main"].__globals__
    monkeypatch.setitem(scope, "checkpoint", lambda: {})
    class Agent:
        def __init__(self, run):
            pass
        def close(self):
            return {"returncode": 0, "forced": False}
    monkeypatch.setitem(scope, "Agent", Agent)
    monkeypatch.setitem(scope, "transfer", lambda agent, args, source, summary, captures: summary.update(outcome=outcome))
    def forbidden(*args, **kwargs):
        pytest.fail("--skip-analysis must never invoke an analyzer subprocess")
    monkeypatch.setattr(runner["subprocess"], "run", forbidden)
    code = runner["main"](["--transport", "usb", "--sender-key", "a", "--receiver-key", "b",
                           "--capture", "none", "--size", "10", "--journal-root", str(tmp_path),
                           "--skip-analysis", "--execute"])
    run, = tmp_path.iterdir()
    assert code == (0 if outcome == "PASS" else 1)
    result = json.loads((run / "result.json").read_text())
    assert result["outcome"] == outcome and result["analysis_skipped"]
    assert not (run / "analysis.json").exists()
    assert not (run / "analyzer.stderr.log").exists()

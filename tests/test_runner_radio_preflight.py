import json
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def runner():
    return runpy.run_path(str(ROOT / 'scripts' / 'run_file_transfer.py'))


def arguments(module, *extra):
    return module['parser']().parse_args([
        '--transport', 'usb', '--sender-key', 'serial:a', '--receiver-key', 'serial:b',
        *extra,
    ])


class FakeNodeAgent:
    def __init__(self, *, config=None, hardware=None, reject=None, validation='OK', tx_state='written'):
        self.config = {'sf': 7, 'bandwidth_hz': 500000, 'power_dbm': 2, 'frequency_hz': 470000000}
        self.config.update(config or {})
        self.hardware = dict(self.config)
        self.hardware.update(hardware or {})
        self.reject, self.validation, self.tx_state = reject, validation, tx_state
        self.commands = []
        self.seq, self.tx_id = 0, 0
        self.command = ''
        self.file_started = False

    def request(self, op, **fields):
        if op == 'discover':
            return {'devices': [{'key': key, 'kind': 'serial'} for key in ('serial:a', 'serial:b')]}
        if op == 'open':
            return {'session': fields['device_key'], 'state': 'connected'}
        if op == 'status':
            return {'latest_seq': self.seq}
        if op == 'send_line':
            self.command = fields['text']
            self.commands.append((fields['session'], self.command))
            self.tx_id += 1
            return {'tx_id': self.tx_id, 'state': 'queued'}
        if op == 'observe':
            session = next(iter(fields['cursors']))
            self.seq += 1
            return {'cursors': {session: self.seq},
                    'events': [{'session': session, 'kind': 'tx', 'tx_id': self.tx_id, 'tx_state': self.tx_state}],
                    'lines': [{'session': session, 'text': value} for value in self.lines()]}
        if op == 'file_send_start':
            self.file_started = True
            raise AssertionError('file send must not start after preflight failure')
        raise AssertionError(op)

    def lines(self):
        if self.command == self.reject:
            return ['[SYS] CFG BUSY: radio/protocol transaction active; setting not changed']
        if self.command.startswith('/sf '):
            return ['[SYS] SF ' + self.command.split()[1] + ' SAVED']
        if self.command.startswith('/bw '):
            return ['[SYS] BW ' + self.command.split()[1] + ' kHz SAVED']
        if self.command.startswith('/power '):
            return ['[SYS] POWER ' + self.command.split()[1] + ' dBm SAVED']
        if self.command.startswith('/freq '):
            return ['[SYS] FREQ ' + self.command.split()[1] + ' MHz SAVED']
        if self.command == '/config':
            c = self.config
            return ['[SYS] CFG schema=2 storage=NVS freq_oob=OFF',
                    f"[SYS] CFG RADIO power={c['power_dbm']} dBm freq={c['frequency_hz'] / 1000000:g} MHz sf={c['sf']} bw={c['bandwidth_hz'] / 1000:g} kHz",
                    '[SYS] CFG LINK heartbeat=OFF retry=ON attempts=5 diag=OFF']
        if self.command == '/radio read config':
            c = self.hardware
            return ['[SYS] RADIO_CONFIG_REGS phase=read readable=1 ver=12',
                    f"[SYS] RADIO_CONFIG_DECODE phase=read bank=LoRa mode=5 frequency_Hz={c['frequency_hz']} power_dBm={c['power_dbm']}",
                    f"[SYS] RADIO_CONFIG_DECODE phase=read sf={c['sf']} bw_Hz={c['bandwidth_hz']} cr=4/5",
                    '[SYS] RADIO_CONFIG phase=read result=READ mismatches=0 state=0']
        if self.command == '/radio validate config':
            differences = [] if self.validation == 'OK' else ['[SYS] RADIO_CONFIG_DIFF phase=validate field=FRF expected=7700480 actual=7600000']
            return [*differences, f'[SYS] RADIO_CONFIG phase=validate result={self.validation} mismatches={len(differences)} state=0']
        raise AssertionError(self.command)

    def close(self):
        return {'returncode': 0, 'forced': False}


def test_applies_four_settings_to_both_nodes_and_verifies_registers(tmp_path):
    module = runner()
    agent, summary = FakeNodeAgent(), {}
    module['prepare_radios'](agent, arguments(module), [('receiver', 's1'), ('sender', 's2')], summary, tmp_path)
    report = json.loads((tmp_path / 'radio_preflight.json').read_text())
    assert report['outcome'] == 'PASS'
    assert report['node_status']['outcome'] == 'SKIPPED'
    assert report['node_status']['todo'] == 'TODO_057_NODE_RUNTIME_STATUS'
    expected = ['/sf 7', '/bw 500', '/power 2', '/freq 470', '/config', '/radio read config', '/radio validate config']
    assert agent.commands == [(session, command) for session in ('s1', 's2') for command in expected]
    assert all(node['outcome'] == 'PASS' and node['mismatches'] == {} for node in report['nodes'].values())


@pytest.mark.parametrize('field,actual', [('sf', 8), ('bandwidth_hz', 125000), ('power_dbm', 3), ('frequency_hz', 471000000)])
def test_saved_response_does_not_hide_wrong_config_value(tmp_path, field, actual):
    module = runner()
    agent, summary = FakeNodeAgent(config={field: actual}), {}
    with pytest.raises(module['ControlError']):
        module['prepare_radios'](agent, arguments(module), [('receiver', 's1'), ('sender', 's2')], summary, tmp_path)
    report = json.loads((tmp_path / 'radio_preflight.json').read_text())
    assert report['outcome'] == 'FAIL'
    mismatch = report['nodes']['receiver']['mismatches'][field]
    assert mismatch['config'] == actual
    assert mismatch['set_result'] == 'saved'
    assert not any(session == 's2' for session, _ in agent.commands)


def test_readback_and_firmware_validation_are_separate_required_gates(tmp_path):
    module = runner()
    report = {}
    assert not module['prepare_node'](FakeNodeAgent(hardware={'power_dbm': 3}), 's1', module['requested_radio'](arguments(module)), 1, report)
    assert report['mismatches']['power_dbm']['hardware'] == 3
    report = {}
    assert not module['prepare_node'](FakeNodeAgent(validation='MISMATCH'), 's1', module['requested_radio'](arguments(module)), 1, report)
    assert report['hardware_differences'][0]['field'] == 'FRF'
    assert 'frequency_hz' in report['mismatches']


def test_busy_stops_setters_and_still_reads_actual_values(tmp_path):
    module = runner()
    agent = FakeNodeAgent(reject='/bw 500')
    report = {}
    assert not module['prepare_node'](agent, 's1', module['requested_radio'](arguments(module)), 1, report)
    commands = [command for _, command in agent.commands]
    assert commands[:2] == ['/sf 7', '/bw 500']
    assert '/power 2' not in commands and '/freq 470' not in commands
    assert '/config' in commands
    assert report['set_results']['bandwidth_hz'] == 'failed'
    assert report['set_results']['power_dbm'] == 'not_attempted'
    assert report['errors'][0]['code'] == 'node_rejected_or_busy'


def test_unknown_tx_stops_without_more_commands_or_file_send(tmp_path):
    module = runner()
    agent = FakeNodeAgent(tx_state='unknown')
    report = {}
    assert not module['prepare_node'](agent, 's1', module['requested_radio'](arguments(module)), 1, report)
    assert agent.commands == [('s1', '/sf 7')]
    assert report['errors'][0]['code'] == 'tx_unknown'
    assert not agent.file_started


def test_runner_failure_returns_report_and_preserves_source_without_starting_file(tmp_path, monkeypatch, capsys):
    module = runner()
    source = tmp_path / 'original.jpg'
    source.write_bytes(b'original image bytes')
    agent = FakeNodeAgent(hardware={'power_dbm': 3})
    globals_ = module['main'].__globals__
    monkeypatch.setitem(globals_, 'Agent', lambda run: agent)
    monkeypatch.setitem(globals_, 'checkpoint', lambda: {'test': 'software only'})
    monkeypatch.setitem(globals_, 'subprocess', SimpleNamespace(run=lambda command, **kwargs: SimpleNamespace(returncode=1, stdout='', stderr='')))
    exit_code = module['main']([
        '--transport', 'usb', '--sender-key', 'serial:a', '--receiver-key', 'serial:b',
        '--file', str(source), '--journal-root', str(tmp_path / 'journal'),
        '--capture', 'none', '--execute',
    ])
    assert exit_code == 1
    assert not agent.file_started
    run = next((tmp_path / 'journal').iterdir())
    report = json.loads((run / 'radio_preflight.json').read_text())
    result = json.loads((run / 'result.json').read_text())
    assert result['outcome'] == report['outcome'] == 'FAIL'
    assert report['requested']['frequency_hz'] == 470000000
    assert report['nodes']['receiver']['mismatches']['power_dbm']['hardware'] == 3
    assert (run / 'sent' / source.name).read_bytes() == source.read_bytes() == b'original image bytes'
    assert '%' not in capsys.readouterr().out


def test_default_frequency_is_470_mhz_in_plan_and_settings(tmp_path, capsys):
    module = runner()
    assert module['main'](['--transport', 'usb', '--sender-key', 'a', '--receiver-key', 'b',
                           '--journal-root', str(tmp_path)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['freq_mhz'] == '470'
    assert plan['preflight_timeout'] == 5
    assert plan['timeout'] == 3600
    assert plan['radio']['frequency_hz'] == 470000000
    assert module['requested_radio'](arguments(module))['frequency_hz'] == 470000000
    assert module['requested_radio'](arguments(module, '--freq-mhz', '471.125'))['frequency_hz'] == 471125000
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('extra', [['--bw-khz', '499'], ['--freq-mhz', '470.0005'], ['--freq-mhz', 'nan']])
def test_invalid_radio_settings_rejected_locally(extra):
    module = runner()
    with pytest.raises(ValueError):
        module['requested_radio'](arguments(module, *extra))



def test_reply_before_tx_written_waits_for_the_matching_tx_event():
    module = runner()
    class ReorderedAgent(FakeNodeAgent):
        def __init__(self):
            super().__init__()
            self.observations = 0
        def request(self, op, **fields):
            if op != 'observe':
                return super().request(op, **fields)
            self.observations += 1
            result = super().request(op, **fields)
            if self.observations == 1:
                result['events'][0]['tx_id'] += 100
            else:
                result['lines'] = []
            return result
    agent = ReorderedAgent()
    control = module['NodeControl'](agent, 's1', 1)
    assert control.command('/sf 7', lambda lines: '[SYS] SF 7 SAVED' in lines) == ['[SYS] SF 7 SAVED']
    assert agent.observations == 2


def test_api_timeout_marks_control_broken_and_does_not_retry_settings():
    module = runner()
    class TimeoutAgent(FakeNodeAgent):
        def request(self, op, **fields):
            if op == 'observe':
                raise TimeoutError('agent response missing')
            return super().request(op, **fields)
    agent, report = TimeoutAgent(), {}
    assert not module['prepare_node'](agent, 's1', module['requested_radio'](arguments(module)), 1, report)
    assert agent.commands == [('s1', '/sf 7')]
    assert report['errors'][0]['code'] == 'TimeoutError'


@pytest.mark.parametrize('value', ['nan', 'inf', '-1'])
def test_preflight_deadline_must_be_finite_and_positive(tmp_path, value):
    with pytest.raises(SystemExit):
        runner()['main'](['--transport', 'usb', '--sender-key', 'a', '--receiver-key', 'b',
                          '--preflight-timeout', value, '--journal-root', str(tmp_path)])
    assert not list(tmp_path.iterdir())



def test_runner_deadlines_can_be_overridden():
    module = runner()
    args = arguments(module, '--preflight-timeout', '8', '--timeout', '7200')
    assert args.preflight_timeout == 8
    assert args.timeout == 7200

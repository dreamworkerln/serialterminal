import json
from pathlib import Path
import runpy
import struct
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


def fake_topology(root):
    identities = []
    for index, (bus, device) in enumerate(((1, 4), (3, 7))):
        usb = root / 'devices' / f'usb{bus}' / f'{bus}-2'
        interface = usb / 'interface'
        interface.mkdir(parents=True)
        (usb / 'busnum').write_text(str(bus))
        (usb / 'devnum').write_text(str(device))
        tty = f'ttyACM{index}'
        (root / 'class' / tty).mkdir(parents=True)
        (root / 'class' / tty / 'device').symlink_to(interface)
        identities.append(SimpleNamespace(key=f'serial:{index}', path='/dev/' + tty))
    return identities


def test_usbmon0_covers_nodes_on_different_buses_without_opening_ports(tmp_path):
    runner = load('run_file_transfer.py')
    args = runner['parser']().parse_args([
        '--transport', 'usb', '--sender-key', 'serial:0', '--receiver-key', 'serial:1',
    ])
    assert args.usbmon_interface == 'usbmon0'
    targets = runner['usb_capture_targets'](args, identities=fake_topology(tmp_path), sys_class_tty=tmp_path / 'class')
    assert [(row['role'], row['bus'], row['device']) for row in targets] == [('sender', 1, 4), ('receiver', 3, 7)]


def test_explicit_single_bus_cannot_silently_miss_receiver(tmp_path):
    runner = load('run_file_transfer.py')
    args = runner['parser']().parse_args([
        '--transport', 'usb', '--sender-key', 'serial:0', '--receiver-key', 'serial:1', '--usbmon-interface', 'usbmon1',
    ])
    with pytest.raises(RuntimeError, match='does not cover receiver'):
        runner['usb_capture_targets'](args, identities=fake_topology(tmp_path), sys_class_tty=tmp_path / 'class')


def test_missing_target_or_sysfs_identity_stops_before_capture(tmp_path):
    runner = load('run_file_transfer.py')
    args = runner['parser']().parse_args([
        '--transport', 'usb', '--sender-key', 'serial:0', '--receiver-key', 'serial:1',
    ])
    with pytest.raises(RuntimeError, match='not discovered'):
        runner['usb_capture_targets'](args, identities=[], sys_class_tty=tmp_path / 'class')
    identities = [SimpleNamespace(key='serial:0', path='/dev/ttyACM0')]
    with pytest.raises(RuntimeError, match='sysfs location missing'):
        runner['usb_capture_targets'](args, identities=identities, sys_class_tty=tmp_path / 'class')


def test_non_usb_or_disabled_capture_does_not_resolve_usb_targets(tmp_path):
    runner = load('run_file_transfer.py')
    args = runner['parser']().parse_args([
        '--transport', 'ble', '--sender-key', 'ble:0', '--receiver-key', 'ble:1', '--capture', 'both',
    ])
    assert runner['usb_capture_targets'](args, identities=[]) == []
    args.transport, args.capture = 'usb', 'none'
    assert runner['usb_capture_targets'](args, identities=[]) == []


def pcap(path, targets):
    data = b'\xd4\xc3\xb2\xa1' + struct.pack('<HHiiii', 2, 4, 0, 0, 65535, 220)
    for bus, device in targets:
        packet = bytearray(64)
        packet[8:12] = bytes([ord('C'), 3, 0x81, device])
        struct.pack_into('<H', packet, 12, bus)
        struct.pack_into('<iII', packet, 28, 0, 3, 3)
        packet += b'abc'
        data += struct.pack('<IIII', 0, 0, len(packet), len(packet)) + packet
    path.write_bytes(data)


def test_analyzer_filters_unrelated_devices_but_preserves_original_capture(tmp_path):
    analyzer = load('analyze_file_transfer.py')
    source = tmp_path / 'usb.pcap'
    pcap(source, [(1, 4), (3, 7), (1, 99)])
    original = source.read_bytes()
    gaps = []
    result = analyzer['usb_stats'](source, gaps, targets=[{'bus': 1, 'device': 4}, {'bus': 3, 'device': 7}])
    assert gaps == []
    assert result['records'] == 3
    assert result['target_records'] == {'bus1/dev4': 1, 'bus3/dev7': 1}
    assert result['filtered_to_selected_nodes'] is True
    assert not any('dev99' in key for key in result['endpoints'])
    assert source.read_bytes() == original


def test_analyzer_reports_missing_node_traffic_even_with_unrelated_packets(tmp_path):
    analyzer = load('analyze_file_transfer.py')
    source = tmp_path / 'usb.pcap'
    pcap(source, [(1, 4), (1, 99)])
    gaps = []
    analyzer['usb_stats'](source, gaps, targets=[{'bus': 1, 'device': 4}, {'bus': 3, 'device': 7}])
    assert 'no USB records for selected node bus3/dev7' in gaps



def test_completed_transfer_does_not_hide_missing_receiver_capture(tmp_path):
    analyzer = load('analyze_file_transfer.py')
    for directory in ('sent', 'received'):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / 'file.bin').write_bytes(b'verified file')
    state = {'state': 'completed', 'transfer_id': 't1'}
    (tmp_path / 'result.json').write_text(json.dumps({
        'transport': 'usb', 'outcome': 'PASS', 'sender_transfer': state,
        'receiver_status': {'file_transfer': state},
        'usb_capture_targets': [{'bus': 1, 'device': 4}, {'bus': 3, 'device': 7}],
    }))
    (tmp_path / 'serialterminal.log').write_text('')
    (tmp_path / 'serialterminal.console.log').write_text('')
    (tmp_path / 'serialterminal.fttiming.jsonl').write_text(json.dumps({
        'segment_id': 'test', 'seq': 1, 'event': 'run_stop',
    }) + '\n')
    (tmp_path / 'serialterminal.application.log').write_text('[INFO] START pid=1\n[INFO] STOP\n')
    (tmp_path / 'usbmon.stderr.log').write_text('0 packets dropped by kernel\n')
    pcap(tmp_path / 'usb.pcap', [(1, 4), (1, 99)])
    report = analyzer['analyze'](tmp_path, decode=False)
    assert report['file_integrity'] == 'PASS'
    assert report['outcome'] == 'INCONCLUSIVE'
    assert 'no USB records for selected node bus3/dev7' in report['evidence_gaps']
    assert report['captures']['usb.pcap']['target_records'] == {'bus1/dev4': 1}



def test_snapshot_truncation_is_scoped_to_selected_usb_nodes(tmp_path):
    analyzer = load('analyze_file_transfer.py')
    source = tmp_path / 'usb.pcap'
    pcap(source, [(1, 4), (1, 99)])
    data = bytearray(source.read_bytes())
    second_header = 24 + 16 + 67
    struct.pack_into('<I', data, second_header + 12, 500)
    source.write_bytes(data)
    gaps = []
    report = analyzer['usb_stats'](source, gaps, targets=[{'bus': 1, 'device': 4}])
    assert gaps == []
    assert report['capture_length_counts'] == {'other_device_snapshot_truncations': 1}
    assert report['capture_length_samples'][0]['device'] == 99
    gaps = []
    analyzer['usb_stats'](source, gaps, targets=[{'bus': 1, 'device': 99}])
    assert 'truncated pcap payload for node bus1/dev99' in gaps


def test_incomplete_pcap_file_blocks_evidence_even_for_unrelated_device(tmp_path):
    analyzer = load('analyze_file_transfer.py')
    source = tmp_path / 'usb.pcap'
    pcap(source, [(1, 99)])
    source.write_bytes(source.read_bytes()[:-1])
    gaps = []
    report = analyzer['usb_stats'](source, gaps, targets=[{'bus': 1, 'device': 4}])
    assert 'truncated pcap packet' in gaps
    assert report['capture_length_counts']['incomplete_file_records'] == 1

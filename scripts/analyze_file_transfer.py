#!/usr/bin/env python3
"""Офлайн-анализ FT1-прогона, ST timing/forensic, btmon и usbmon."""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def json_rows(path, gaps):
    if not path.exists():
        gaps.append(f"missing {path.name}")
        return
    with path.open(encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("not an object")
                yield value
            except (ValueError, TypeError):
                gaps.append(f"{path.name}:{number}: malformed JSON")


def timing_stats(path, gaps):
    counts, sizes, ft1 = Counter(), Counter(), Counter()
    last, segments, stopped = {}, set(), False
    for row in json_rows(path, gaps):
        segment, seq = row.get("segment_id"), row.get("seq")
        if not segment or not isinstance(seq, int):
            gaps.append(f"{path.name}: missing segment_id/seq")
        else:
            previous = last.get(segment, 0)
            if seq != previous + 1:
                gaps.append(f"timing segment {segment}: expected {previous + 1}, got {seq}")
            last[segment] = seq
            segments.add(segment)
        stopped |= row.get("event") == "run_stop"
        key = f"{row.get('session', '-')}/{row.get('stream', '-')}/{row.get('event', '?')}"
        counts[key] += 1
        if isinstance(row.get("bytes"), int):
            sizes[key] += row["bytes"]
        if row.get("event") == "ft1_event":
            event = row.get("ft1") or {}
            ft1[f"{row.get('session')}/{event.get('transfer_id')}/{event.get('kind')}"] += 1
    if not stopped:
        gaps.append("timing run_stop missing; tail completeness unconfirmed")
    return {"events": dict(counts), "bytes": dict(sizes), "ft1_events": dict(ft1), "segments": len(segments)}


def forensic_stats(path, gaps):
    counts, sizes, ft1 = Counter(), Counter(), Counter()
    states, last, payloads = Counter(), {}, defaultdict(Counter)
    if not path.exists():
        gaps.append(f"missing {path.name}")
        return {}
    with path.open(encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            match = re.search(r" \[(RX [^]]+|FT1|STATE|ERROR|AGENT)\] (.*)$", line)
            if not match:
                continue
            tag, raw = match.groups()
            try:
                row = json.loads(raw)
            except ValueError:
                gaps.append(f"{path.name}:{number}: malformed forensic record")
                continue
            if not isinstance(row, dict):
                continue
            session = row.get("session", "-")
            if row.get("kind") == "forensic_gap" or row.get("event") == "forensic_gap":
                gaps.append(f"{path.name}:{number}: forensic_gap")
            if tag.startswith("RX "):
                key = f"{session}/{row.get('stream', tag[3:])}"
                counts[key] += 1
                seq = row.get("seq")
                # RX seq включает STATE/TX; разность RX seq не является потерей пакетов.
                last[key] = seq
                try:
                    payload = base64.b64decode(row["data_b64"], validate=True)
                    sizes[key] += len(payload)
                    payloads[key][hashlib.sha256(payload).hexdigest()] += 1
                except (KeyError, ValueError):
                    gaps.append(f"{path.name}:{number}: unavailable RX bytes")
            elif tag == "FT1":
                ft1[f"{session}/{row.get('transfer_id')}/{row.get('kind')}"] += 1
            elif tag in {"STATE", "ERROR"}:
                states[f"{session}/{tag}/{row.get('state', row.get('kind'))}"] += 1
    return {"rx_chunks": dict(counts), "rx_bytes": dict(sizes), "ft1_events": dict(ft1),
            "state_errors": dict(states), "last_rx_seq": last, "payload_sha256_counts": {k: dict(v) for k, v in payloads.items()}}


SNAPSHOT_FIELDS = ("transfer_id", "direction", "state", "wire_bytes", "bytes_completed",
                   "chunks_total", "chunks_completed", "repair", "elapsed", "final_path")


def snapshot_key(snapshot):
    value = {key: snapshot[key] for key in SNAPSHOT_FIELDS if key in snapshot}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def runner_progress_stats(run, result, gaps):
    path = run / "progress.jsonl"
    if not path.exists():
        if result.get("transfer_id"):
            gaps.append("missing progress.jsonl for started transfer")
        return {"available": False}
    before = len(gaps)
    sessions = {result.get(key, {}).get("session"): role
                for key, role in (("sender_open", "TX"), ("receiver_open", "RX"))}
    sessions.pop(None, None)
    pending, origins = {}, {}
    # Сверяем отпечатки snapshots с исходными ответами ST, не выводя сами записи.
    for row in json_rows(run / "agent.jsonl", gaps):
        message = row.get("message") or {}
        if row.get("direction") == "request":
            pending[message.get("id")] = (message.get("op"), sessions.get(message.get("session")))
        elif row.get("direction") == "response":
            operation, role = pending.pop(message.get("id"), (None, None))
            if role is None or not message.get("ok"):
                continue
            body = message.get("result") or {}
            snapshot = (body if operation == "file_send_start" else body.get("progress")
                        if operation == "file_transfer_observe" else body.get("file_transfer")
                        if operation == "status" else None)
            if snapshot:
                key = (role, snapshot_key(snapshot))
                origins[key] = min(origins.get(key, float("inf")), row.get("timestamp", float("inf")))
    counts, intermediate, states = Counter(), Counter(), defaultdict(set)
    matched, rows, verified, maximum_delta, previous_elapsed = 0, 0, False, 0.0, -1.0
    errors = Counter()
    for row in json_rows(path, gaps):
        rows += 1
        try:
            stamp = datetime.fromisoformat(row["timestamp"]).timestamp()
            elapsed = float(row["elapsed"])
            if not math.isfinite(elapsed) or elapsed < previous_elapsed:
                errors["elapsed is not monotonic"] += 1
            previous_elapsed = elapsed
            if row.get("transfer_id") != result.get("transfer_id"):
                errors["wrong ROOT transfer_id"] += 1
            values = {}
            for role in ("TX", "RX"):
                snapshot = row.get(role)
                if snapshot is None:
                    continue
                counts[role] += 1
                states[role].add(snapshot["state"])
                if snapshot.get("direction") != role or snapshot.get("transfer_id") != row.get("transfer_id"):
                    errors["wrong snapshot role/ROOT"] += 1
                if origins.get((role, snapshot_key(snapshot)), float("inf")) > stamp + .001:
                    errors["snapshot absent from preceding ST API responses"] += 1
                else:
                    matched += 1
                done, total = snapshot.get("bytes_completed", 0), snapshot.get("wire_bytes", 0)
                if snapshot["state"] not in {"preparing", "compressing"} and total > 0:
                    if not 0 <= done <= total:
                        errors["DATA counters out of bounds"] += 1
                    values[role] = (done, total)
                    intermediate[role] += 0 < done < total
            tx, rx = values.get("TX"), values.get("RX")
            delta = row.get("delta")
            if tx and rx and tx[1] == rx[1]:
                difference = tx[0] - rx[0]
                expected = 100 * difference / tx[1]
                maximum_delta = max(maximum_delta, abs(expected))
                if not delta or delta.get("bytes") != difference or not math.isclose(delta.get("percentage_points", float("inf")), expected, abs_tol=.001):
                    errors["incorrect TX-RX difference"] += 1
            elif delta is not None:
                errors["unavailable counters have numeric difference"] += 1
            if row.get("verified"):
                verified = True
                if any((row.get(role) or {}).get("state") != "completed" for role in ("TX", "RX")):
                    errors["verified before both completed"] += 1
        except (KeyError, TypeError, ValueError, OverflowError):
            errors["malformed progress row"] += 1
    for error, count in errors.items():
        gaps.append(f"runner progress: {error} ({count})")
    if result.get("outcome") == "PASS" and (not rows or not verified):
        gaps.append("runner progress: successful run has no verified observation")
    return {"available": True, "rows": rows, "snapshots": dict(counts), "api_matched_snapshots": matched,
            "intermediate_snapshots": dict(intermediate), "states": {key: sorted(value) for key, value in states.items()},
            "max_absolute_difference_pp": round(maximum_delta, 3), "verified": verified,
            "event_history_gaps": len(result.get("monitor_event_gaps", [])),
            "consistency": "PASS" if len(gaps) == before else "INCONCLUSIVE"}


def btsnoop_stats(path, gaps):
    counts, drops, records = Counter(), 0, 0
    pending, notifications = {}, defaultdict(Counter)
    with path.open("rb") as handle:
        header = handle.read(16)
        if len(header) != 16 or header[:8] != b"btsnoop\0":
            gaps.append("invalid btsnoop header")
            return {}
        version, linktype = struct.unpack(">II", header[8:])
        if version != 1:
            gaps.append(f"unsupported btsnoop version {version}")
            return {}
        while raw := handle.read(24):
            if len(raw) != 24:
                gaps.append("truncated btsnoop record header")
                break
            original, included, flags, dropped, _ = struct.unpack(">IIIIQ", raw)
            if included > 16 * 1024 * 1024:
                gaps.append("invalid btsnoop record length")
                break
            payload = handle.read(included)
            if len(payload) != included or included < original:
                gaps.append("truncated btsnoop packet")
            drops = max(drops, dropped)
            records += 1
            # Для Linux monitor linktype 2001 flags кодируют adapter index и opcode.
            counts[f"hci{flags >> 16}/opcode{flags & 0xffff}" if linktype == 2001 else f"flags{flags}"] += 1
            if linktype == 2001 and flags & 0xffff == 5:
                consume_acl(payload, flags >> 16, pending, notifications, gaps)
    if drops:
        gaps.append(f"btsnoop reports {drops} cumulative drops")
    return {"linktype": linktype, "records": records, "cumulative_drops": drops, "records_by_channel": dict(counts),
            "att_notifications": {k: {"count": sum(v.values()), "payload_sha256_counts": dict(v)}
                                  for k, v in notifications.items()}}



def consume_acl(payload, adapter, pending, notifications, gaps):
    if len(payload) < 4:
        gaps.append("short HCI ACL packet")
        return
    flags, length = struct.unpack("<HH", payload[:4])
    connection, boundary = flags & 0xfff, (flags >> 12) & 3
    key = (adapter, connection)
    data = payload[4:]
    if len(data) != length:
        gaps.append("HCI ACL length mismatch")
        pending.pop(key, None)
        return
    if boundary in (0, 2):
        if key in pending:
            gaps.append(f"unfinished L2CAP packet: {key}")
        pending[key] = bytearray(data)
    elif boundary == 1 and key in pending:
        pending[key].extend(data)
    else:
        gaps.append(f"orphan/unsupported ACL fragment: {key}")
        return
    buffer = pending[key]
    if len(buffer) < 4:
        return
    length, cid = struct.unpack("<HH", buffer[:4])
    if len(buffer) < length + 4:
        return
    pending.pop(key)
    if len(buffer) != length + 4:
        gaps.append(f"L2CAP length mismatch: {key}")
        return
    # Fixed ATT CID: EATT и multi-handle notification требуют отдельного декодера.
    if cid == 4 and length >= 3 and buffer[4] in (0x1b, 0x1d):
        handle = struct.unpack("<H", buffer[5:7])[0]
        group = f"hci{adapter}/conn0x{connection:04x}/att0x{handle:04x}"
        notifications[group][hashlib.sha256(buffer[7:]).hexdigest()] += 1


def correlate_notifications(capture, forensic):
    streams = forensic.get("payload_sha256_counts", {})
    result = {}
    for group, values in capture.get("att_notifications", {}).items():
        observed = Counter(values["payload_sha256_counts"])
        candidates = []
        for stream, hashes in streams.items():
            local = Counter(hashes)
            matched = sum((observed & local).values())
            if matched:
                candidates.append({"stream": stream, "identical_payloads": matched,
                                   "capture_payloads_absent_from_stream": sum((observed - local).values()),
                                   "stream_payloads_absent_from_capture": sum((local - observed).values())})
        result[group] = sorted(candidates, key=lambda row: row["identical_payloads"], reverse=True)
    return result

def usb_stats(path, gaps, targets=None):
    endpoints = defaultdict(Counter)
    records = 0
    selected = None if targets is None else {(row["bus"], row["device"]) for row in targets}
    target_counts = Counter()
    length_counts, length_samples = Counter(), []
    with path.open("rb") as handle:
        header = handle.read(24)
        endian = {b"\xd4\xc3\xb2\xa1": "<", b"\xa1\xb2\xc3\xd4": ">",
                  b"\x4d\x3c\xb2\xa1": "<", b"\xa1\xb2\x3c\x4d": ">"}.get(header[:4])
        if len(header) != 24 or endian is None:
            gaps.append("unsupported/truncated USB pcap header (classic pcap required)")
            return {}
        linktype = struct.unpack(endian + "I", header[20:24])[0]
        if linktype not in (189, 220):
            gaps.append(f"unexpected USB linktype {linktype}")
            return {}
        while raw := handle.read(16):
            if len(raw) != 16:
                gaps.append("truncated pcap record header")
                break
            _, _, included, original = struct.unpack(endian + "IIII", raw)
            if included > 16 * 1024 * 1024:
                gaps.append("invalid pcap record length")
                break
            payload = handle.read(included)
            file_short = len(payload) != included
            snapshot_short = included < original
            if file_short:
                gaps.append("truncated pcap packet")
                length_counts["incomplete_file_records"] += 1
            records += 1
            if len(payload) < (64 if linktype == 220 else 48):
                gaps.append("short usbmon packet")
                continue
            event, transfer, endpoint, device = payload[8:12]
            bus = struct.unpack(endian + "H", payload[12:14])[0]
            is_target = selected is None or (bus, device) in selected
            status, urb_bytes, data_bytes = struct.unpack(endian + "iII", payload[28:40])
            if snapshot_short:
                length_counts["selected_snapshot_truncations" if is_target else "other_device_snapshot_truncations"] += 1
                if is_target and not file_short:
                    gaps.append(f"truncated pcap payload for node bus{bus}/dev{device}")
                if len(length_samples) < 8:
                    length_samples.append({"record": records, "bus": bus, "device": device,
                                           "selected_node": is_target, "included": included, "original": original,
                                           "file_bytes": len(payload), "event": chr(event), "transfer_type": transfer,
                                           "endpoint": endpoint, "urb_bytes": urb_bytes, "data_bytes": data_bytes,
                                           "data_flag": payload[15]})
            if not is_target:
                continue
            target_counts[f"bus{bus}/dev{device}"] += 1
            key = f"bus{bus}/dev{device}/ep0x{endpoint:02x}/type{transfer}"
            row = endpoints[key]
            row[chr(event)] += 1
            row["captured_data_bytes"] += data_bytes
            if event == ord("C"):
                row["completed_urb_bytes"] += urb_bytes
            if status and event in (ord("C"), ord("E")):
                row[f"status_{status}"] += 1
    if selected is not None:
        for bus, device in sorted(selected):
            if not target_counts[f"bus{bus}/dev{device}"]:
                gaps.append(f"no USB records for selected node bus{bus}/dev{device}")
    return {"linktype": linktype, "records": records, "target_records": dict(target_counts),
            "filtered_to_selected_nodes": selected is not None,
            "capture_length_counts": dict(length_counts), "capture_length_samples": length_samples,
            "endpoints": {k: dict(v) for k, v in endpoints.items()}}


def decode_capture(run, source, tool, arguments, gaps):
    destination = run / (source.stem + ".decoded.log")
    if not shutil.which(tool):
        gaps.append(f"{tool} unavailable for offline decoding {source.name}")
        return {}
    command = [tool, *arguments, str(source)]
    try:
        with destination.open("wb") as out, (run / (source.stem + ".decode.stderr.log")).open("wb") as err:
            result = subprocess.run(command, stdout=out, stderr=err, timeout=60)
        if result.returncode:
            gaps.append(f"offline decoder failed: {source.name}, exit {result.returncode}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        gaps.append(f"offline decoder failed: {exc}")
    counts = Counter()
    with destination.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            for token in ("Handle Value Notification", "Handle Value Indication", "Disconnect Complete",
                          "Connection Timeout", "Error Response"):
                if token in line:
                    counts[token] += 1
    return {"command": command, "text": destination.name, "diagnostic_counts": dict(counts)}


def analyze(run, decode=True):
    gaps = []
    result_path = run / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    report = {"run": str(run), "recorded_outcome": result.get("outcome", "INCONCLUSIVE"),
              "transport": result.get("transport"), "evidence_gaps": gaps}
    source = list((run / "sent").glob("*"))
    received = list((run / "received").glob("*"))
    report["files"] = {"sent": {p.name: fingerprint(p) for p in source if p.is_file()},
                       "received": {p.name: fingerprint(p) for p in received if p.is_file()}}
    tx = result.get("sender_transfer") or {}
    rx = (result.get("receiver_status") or {}).get("file_transfer") or {}
    original = report["files"]["sent"]
    incoming = report["files"]["received"]
    verified = bool(len(original) == 1 and any(value == next(iter(original.values())) for value in incoming.values()))
    completed = (tx.get("state") == rx.get("state") == "completed"
                 and tx.get("transfer_id") == rx.get("transfer_id")
                 and (not result.get("transfer_id") or tx.get("transfer_id") == result["transfer_id"]))
    report["file_integrity"] = "PASS" if verified and completed else "FAIL" if original else "INCONCLUSIVE"
    report["sender_transfer"], report["receiver_transfer"] = tx, rx
    report["st_logs"] = {
        "primary": "serialterminal.log", "console": "serialterminal.console.log",
        "timing": "serialterminal.fttiming.jsonl", "application": "serialterminal.application.log",
    }
    report["timing"] = timing_stats(run / report["st_logs"]["timing"], gaps)
    report["forensic"] = forensic_stats(run / report["st_logs"]["primary"], gaps)
    if report["timing"].get("ft1_events") != report["forensic"].get("ft1_events", {}):
        gaps.append("FT1 event counts differ between primary and timing logs")
    report["runner_progress"] = runner_progress_stats(run, result, gaps)
    console = Counter()
    console_path = run / report["st_logs"]["console"]
    if not console_path.exists():
        gaps.append(f"missing {console_path.name}")
    else:
        with console_path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = re.search(r" \[(s\d+)\] \[([IO])\] ", line)
                if match:
                    console[f"{match[1]}/{match[2]}"] += 1
    report["console_records"] = dict(console)
    application = {"errors": 0, "started": False, "stopped": False}
    app_path = run / report["st_logs"]["application"]
    if not app_path.exists():
        gaps.append(f"missing {app_path.name}")
    else:
        with app_path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                application["errors"] += "[ERROR]" in line
                application["started"] |= "[INFO] START pid=" in line
                application["stopped"] |= "[INFO] STOP" in line
        if application["errors"]:
            gaps.append(f"{app_path.name}: {application['errors']} application errors; inspect trace completeness")
        if not application["started"] or not application["stopped"]:
            gaps.append(f"{app_path.name}: incomplete process lifecycle")
    report["application"] = application
    captures = {}
    for capture in result.get("captures", []):
        name = capture["output"]
        if not (run / name).exists():
            gaps.append(f"missing capture {name}")
        if capture.get("early_exit") or capture.get("forced") or capture.get("returncode") not in (0, -2):
            gaps.append(f"capture did not finish cleanly: {name}")
    if result.get("capture_incomplete"):
        gaps.append("runner reports incomplete capture")
    for name, parse, tool, arguments in (
        ("ble.btsnoop", btsnoop_stats, "btmon", ["-P", "-T", "-c", "never", "-r"]),
        ("usb.pcap", usb_stats, "tcpdump", ["-nn", "-tt", "-r"]),
    ):
        path = run / name
        if path.exists():
            if name == "usb.pcap" and result.get("transport") == "usb":
                targets = result.get("usb_capture_targets")
                if not targets:
                    gaps.append("USB node bus/device mapping unavailable; capture attribution unconfirmed")
                captures[name] = usb_stats(path, gaps, targets=targets or None)
            else:
                captures[name] = parse(path, gaps)
            if not captures[name].get("records"):
                gaps.append(f"empty capture {name}")
            if decode:
                captures[name]["decode"] = decode_capture(run, path, tool, arguments, gaps)
    usb_stderr = run / "usbmon.stderr.log"
    if usb_stderr.exists():
        text = usb_stderr.read_text(encoding="utf-8", errors="replace")
        dropped = re.findall(r"(\d+) packets dropped by kernel", text)
        if not dropped:
            gaps.append("usbmon capture drop count unavailable")
        elif any(int(value) for value in dropped):
            gaps.append(f"usbmon kernel drops: {dropped}")
    if "ble.btsnoop" in captures:
        report["ble_payload_candidates"] = correlate_notifications(captures["ble.btsnoop"], report["forensic"])
    report["usb_capture_targets"] = result.get("usb_capture_targets", [])
    report["captures"] = captures
    other_truncations = captures.get("usb.pcap", {}).get("capture_length_counts", {}).get("other_device_snapshot_truncations", 0)
    report["capture_warnings"] = ([f"{other_truncations} snapshot-truncated USB records belong to devices outside the selected nodes"]
                                  if other_truncations else [])
    report["packet_loss_percent"] = None
    report["limits"] = [
        "HCI capture observes host/controller traffic, not BLE packets over the air.",
        "USB URBs, HCI ACL packets, ATT notifications, ST RX chunks and FT1 DATA are different units.",
        "USB node mapping is a pre-capture sysfs snapshot; re-enumeration/address reuse needs separate identity verification.",
        "Capture counters include startup/shutdown and possibly unrelated devices; do not subtract global counters.",
        "FT1 repair/completion and matching hashes do not prove zero local transport loss.",
        "BLE payload candidates compare exact SHA-256 multisets, with multiplicity; candidate stream mapping and capture boundaries still require verification.",
        "Fixed ATT CID notifications/indications are reassembled from incoming HCI ACL; EATT is not decoded by the built-in parser.",
        "Physical firmware version must be established from captured node output, not source HEAD.",
    ]
    if not captures:
        gaps.append("no packet captures; transport loss cannot be localized")
    report["outcome"] = (
        "PASS" if report["file_integrity"] == "PASS" and result.get("outcome") == "PASS" and not gaps
        else "FAIL" if report["file_integrity"] == "FAIL" or result.get("outcome") == "FAIL"
        else "INCONCLUSIVE"
    )
    return report


EXCERPT_LOGS = {
    "primary": "serialterminal.log", "console": "serialterminal.console.log",
    "timing": "serialterminal.fttiming.jsonl", "application": "serialterminal.application.log",
}
MAX_EXCERPT_LINES = 200
MAX_EXCERPT_BYTES = 32768
MAX_SOURCE_LINE_BYTES = 65536


def excerpt_time(value):
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("timezone required")
        return moment.timestamp()
    except (ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError("нужно ISO-время с timezone, например 2026-10-17T10:00:00+03:00") from exc


def bounded_source_lines(path):
    # Одна BINARY/API запись бывает огромной: не держим всю строку в памяти.
    with path.open("rb") as handle:
        number = 0
        while raw := handle.readline(MAX_SOURCE_LINE_BYTES + 1):
            number += 1
            oversized = len(raw) > MAX_SOURCE_LINE_BYTES
            prefix = raw[:MAX_SOURCE_LINE_BYTES]
            while not raw.endswith(b"\n") and len(raw) > MAX_SOURCE_LINE_BYTES:
                raw = handle.readline(MAX_SOURCE_LINE_BYTES + 1)
                if not raw:
                    break
            yield number, prefix.decode("utf-8", errors="replace").rstrip("\r\n"), oversized


def record_time(kind, text):
    try:
        if kind == "timing":
            value = json.loads(text).get("timestamp")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            return float(value) if math.isfinite(value) else None
        return excerpt_time(text.split(" ", 1)[0])
    except (ValueError, TypeError, AttributeError, OverflowError, argparse.ArgumentTypeError):
        return None


def encoded_excerpt_row(row):
    return json.dumps(row, ensure_ascii=False) + "\n"


def fit_excerpt_row(row, budget):
    rendered = encoded_excerpt_row(row)
    if len(rendered.encode("utf-8")) <= budget:
        return row
    row = {**row, "text_truncated": True}
    text = row["text"]
    row["text"] = ""
    if len(encoded_excerpt_row(row).encode("utf-8")) > budget:
        return None
    lo, hi = 0, len(text)
    while lo < hi:
        middle = (lo + hi + 1) // 2
        row["text"] = text[:middle]
        if len(encoded_excerpt_row(row).encode("utf-8")) <= budget:
            lo = middle
        else:
            hi = middle - 1
    row["text"] = text[:lo]
    return row


def extract_excerpt(run, *, at, before=2, after=2, kinds=None, max_lines=80, max_bytes=16384):
    if not math.isfinite(at) or not all(math.isfinite(v) and v >= 0 for v in (before, after)):
        raise ValueError("время и окрестности должны быть конечными, окрестности — неотрицательными")
    if before + after > 300:
        raise ValueError("окно фрагмента не может превышать 300 секунд")
    if not 1 <= max_lines <= MAX_EXCERPT_LINES or not 1 <= max_bytes <= MAX_EXCERPT_BYTES:
        raise ValueError("лимиты фрагмента: 1–200 строк и 1–32768 bytes")
    try:
        from_utc = datetime.fromtimestamp(at - before, timezone.utc).isoformat()
        to_utc = datetime.fromtimestamp(at + after, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError("временное окно выходит за допустимый диапазон дат") from exc
    kinds = list(dict.fromkeys(kinds or EXCERPT_LOGS))
    if any(kind not in EXCERPT_LOGS for kind in kinds):
        raise ValueError("неизвестный тип ST-лога")
    candidates, sources = [], {}
    for kind in kinds:
        filename = EXCERPT_LOGS[kind]
        path = run / filename
        stats = {"matched_lines": 0, "unparsed_timestamps": 0, "oversized_lines": 0, "missing": not path.exists()}
        sources[filename] = stats
        if stats["missing"]:
            continue
        current_time, kept_bytes, kept_lines = None, 0, 0
        for number, text, oversized in bounded_source_lines(path):
            stamp = record_time(kind, text)
            # Traceback application log продолжает timestamp предыдущей записи.
            if stamp is not None or kind != "application":
                current_time = stamp
            stats["oversized_lines"] += oversized
            if current_time is None:
                stats["unparsed_timestamps"] += 1
                continue
            if not at - before <= current_time <= at + after:
                continue
            stats["matched_lines"] += 1
            if kept_lines >= max_lines:
                continue
            row = {"source": filename, "line": number, "timestamp": current_time, "text": text}
            if oversized:
                row["text_truncated"] = True
            row = fit_excerpt_row(row, max_bytes - kept_bytes)
            if row is not None:
                candidates.append(row)
                kept_bytes += len(encoded_excerpt_row(row).encode("utf-8"))
                kept_lines += 1
    # Лимиты общие для всех четырёх файлов; исходные строки имеют provenance.
    rows, used_bytes = [], 0
    for row in sorted(candidates, key=lambda value: (value["timestamp"], value["source"], value["line"])):
        if len(rows) >= max_lines:
            break
        row = fit_excerpt_row(row, max_bytes - used_bytes)
        if row is None:
            break
        rows.append(row)
        used_bytes += len(encoded_excerpt_row(row).encode("utf-8"))
    matched = sum(stats["matched_lines"] for stats in sources.values())
    return {
        "run": str(run), "from_utc": from_utc, "to_utc": to_utc,
        "max_lines": max_lines, "max_bytes": max_bytes, "record_bytes": used_bytes,
        "matched_lines": matched, "returned_lines": len(rows),
        "truncated": matched > len(rows) or any(row.get("text_truncated") for row in rows),
        "sources": sources, "records": rows,
    }


def run_excerpt(args, parser):
    if len(args.runs) != 1:
        parser.error("для фрагмента укажи один каталог прогона")
    run = args.runs[0].resolve()
    if not run.is_dir():
        parser.error("каталог прогона не существует")
    try:
        report = extract_excerpt(run, at=args.excerpt_at, before=args.before, after=args.after,
                                 kinds=args.excerpt_log, max_lines=args.max_lines, max_bytes=args.max_bytes)
    except ValueError as exc:
        parser.error(str(exc))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = run / f"excerpt-{stamp}.json"
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    summary = {key: value for key, value in report.items() if key not in {"records", "run"}}
    summary["excerpt"] = str(output)
    if args.show_excerpt:
        for row in report["records"]:
            print(encoded_excerpt_row(row), end="")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if report["returned_lines"] else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("runs", type=Path, nargs="+", help="один прогон или USB и BLE для сравнения")
    p.add_argument("--no-decode", action="store_true", help="только встроенный binary parser, без btmon/tcpdump")
    p.add_argument("--excerpt-at", type=excerpt_time, help="время известного сбоя/аномалии, ISO с timezone")
    p.add_argument("--before", type=float, default=2, help="секунд до события, по умолчанию 2")
    p.add_argument("--after", type=float, default=2, help="секунд после события, по умолчанию 2")
    p.add_argument("--excerpt-log", action="append", choices=tuple(EXCERPT_LOGS), help="типы логов; по умолчанию все четыре")
    p.add_argument("--max-lines", type=int, default=80, help="общий лимит строк фрагмента, максимум 200")
    p.add_argument("--max-bytes", type=int, default=16384, help="общий лимит bytes записей, максимум 32768")
    p.add_argument("--show-excerpt", action="store_true", help="явно вывести ограниченный фрагмент для разбора известной аномалии")
    args = p.parse_args(argv)
    if args.excerpt_at is not None:
        return run_excerpt(args, p)
    if args.show_excerpt or args.excerpt_log or args.before != 2 or args.after != 2 or args.max_lines != 80 or args.max_bytes != 16384:
        p.error("параметры фрагмента требуют --excerpt-at")
    reports = []
    for directory in args.runs:
        run = directory.resolve()
        report = analyze(run, decode=not args.no_decode)
        reports.append(report)
        (run / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = [f"Outcome: {report['outcome']}", f"File integrity: {report['file_integrity']}",
                 f"Transport: {report['transport']}", "Packet loss: undetermined", "", "Evidence gaps:"]
        lines.extend(f"- {gap}" for gap in report["evidence_gaps"])
        lines.extend(["", "Capture warnings:", *[f"- {warning}" for warning in report["capture_warnings"]]])
        lines.extend(["", "Interpretation limits:", *[f"- {item}" for item in report["limits"]]])
        (run / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(json.dumps({"run": str(run), "outcome": report["outcome"], "file_integrity": report["file_integrity"],
                          "elapsed": report["sender_transfer"].get("elapsed"), "gaps": len(report["evidence_gaps"])}, ensure_ascii=False))
    return 0 if all(report["outcome"] == "PASS" for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())

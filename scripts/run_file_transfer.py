#!/usr/bin/env python3
"""Прогон файла через LoRa с USB/USB или BLE/BLE клиентами SerialTerminal."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT.parents[1] / "journal_of_experiments"
TERMINAL = {"completed", "failed", "cancelled"}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def make_payload(path, size):
    # SHA-256 counter stream воспроизводим между прогонами и почти не сжимается gzip.
    with path.open("xb") as handle:
        for index in range((size + 31) // 32):
            block = hashlib.sha256(b"ST transport comparison v1\0" + index.to_bytes(8, "big")).digest()
            handle.write(block[:min(32, size - index * 32)])


class RunStdout:
    def __init__(self, console, logfile):
        self.console = console
        self.logfile = logfile

    def write(self, text):
        self.logfile.write(text)
        self.console.write(text)
        return len(text)

    def flush(self):
        self.logfile.flush()
        self.console.flush()


class AgentRequestError(RuntimeError):
    def __init__(self, op, error):
        super().__init__(f"{op}: {error}")
        self.error = error


class Agent:
    def __init__(self, run):
        self.transcript = (run / "agent.jsonl").open("w", encoding="utf-8")
        self.lock = threading.Lock()
        self.stderr = (run / "agent.stderr.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / "serialterminal.py"), "agent", "--log",
             str(run / "serialterminal.log"), "--receive-dir", str(run / "received"), "--log-base64"],
            cwd=run, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
            text=True, bufsize=1,
        )
        self.responses = queue.Queue()
        self.next_id = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def record(self, direction, value):
        with self.lock:
            self.transcript.write(json.dumps({"timestamp": time.time(), "direction": direction,
                                              "message": value}, ensure_ascii=False) + "\n")
            self.transcript.flush()

    def _read(self):
        try:
            for raw in self.process.stdout:
                response = json.loads(raw)
                self.record("response", response)
                self.responses.put(response)
        except Exception as exc:
            self.responses.put(exc)
        finally:
            self.responses.put(EOFError("agent stdout closed"))

    def request(self, op, *, timeout=30, **fields):
        self.next_id += 1
        request = {"id": self.next_id, "op": op, **fields}
        self.record("request", request)
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                response = self.responses.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise TimeoutError(f"agent {op} timed out") from exc
            if isinstance(response, Exception):
                raise response
            # После timeout старый long-poll может ответить позже; его ответ уже сохранён.
            if response.get("id") != request["id"]:
                continue
            if not response.get("ok"):
                raise AgentRequestError(op, response.get("error") or {})
            return response["result"]

    def close(self):
        self.process.stdin.close()
        forced = False
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            forced = True
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.reader.join(timeout=5)
        if self.reader.is_alive():
            raise RuntimeError("agent reader did not stop")
        self.transcript.close()
        self.stderr.close()
        return {"returncode": self.process.returncode, "forced": forced}


class Capture:
    def __init__(self, name, command, output, run):
        self.name, self.output = name, output
        self.stdout = (run / f"{name}.stdout.log").open("wb")
        self.stderr = (run / f"{name}.stderr.log").open("wb")
        self.process = subprocess.Popen(command, stdout=self.stdout, stderr=self.stderr, start_new_session=True)
        self.info = {"name": name, "command": command, "output": output.name}

    def ready(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.check()
            if self.output.exists() and self.output.stat().st_size >= 16:
                return
            time.sleep(0.1)
        raise RuntimeError(f"{self.name} did not initialize capture; see stderr log")

    def check(self):
        if self.process.poll() is not None:
            raise RuntimeError(f"{self.name} exited early ({self.process.returncode}); see stderr log")

    def stop(self):
        early = self.process.poll() is not None
        forced = False
        if not early:
            os.killpg(self.process.pid, signal.SIGINT)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                forced = True
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=3)
        self.stdout.close()
        self.stderr.close()
        return {**self.info, "returncode": self.process.returncode, "early_exit": early, "forced": forced}


def capture_commands(args, run):
    modes = {args.transport} if args.capture == "auto" else {"usb", "ble"} if args.capture == "both" else set()
    prefix = ["sudo", "-n"] if args.capture_sudo else []
    result = []
    if "ble" in modes:
        output = run / "ble.btsnoop"
        result.append(("btmon", prefix + ["btmon", "-i", args.hci_index, "-w", str(output),
                                         "-P", "-T", "-c", "never"], output))
    if "usb" in modes:
        output = run / "usb.pcap"
        result.append(("usbmon", prefix + ["tcpdump", "-i", args.usbmon_interface,
                                          "-s", "0", "-U", "-w", str(output)], output))
    return result


def capture_preflight(args, run, *, device_root=Path("/dev")):
    for name, command, _output in capture_commands(args, run):
        executable = command[2] if args.capture_sudo else command[0]
        for tool in (["sudo", executable] if args.capture_sudo else [executable]):
            if shutil.which(tool) is None:
                raise RuntimeError(f"capture tool not installed: {tool}")
        if name == "usbmon":
            device = device_root / args.usbmon_interface
            if not device.exists():
                raise RuntimeError(f"USB capture device missing: {device}; load usbmon before the run")
            if not args.capture_sudo and not os.access(device, os.R_OK):
                raise RuntimeError(f"USB capture device is not readable: {device}; check udev permissions")


def usb_capture_targets(args, *, identities=None, sys_class_tty=Path("/sys/class/tty")):
    if args.transport != "usb" or args.capture not in {"auto", "both"}:
        return []
    if identities is None:
        # Только host metadata: discovery не открывает tty и не отправляет команды.
        sys.path.insert(0, str(ROOT / "src"))
        from serialterminal.transports.serial import discover_serial_devices
        identities = discover_serial_devices()
    devices = {identity.key: identity for identity in identities}
    targets = []
    for role, key in (("sender", args.sender_key), ("receiver", args.receiver_key)):
        if key not in devices:
            raise RuntimeError(f"USB capture target not discovered: {key}")
        tty = Path(os.path.realpath(devices[key].path)).name
        location = sys_class_tty / tty / "device"
        if not location.exists():
            raise RuntimeError(f"USB sysfs location missing for {key}")
        physical = location.resolve()
        for parent in (physical, *physical.parents):
            if (parent / "busnum").is_file() and (parent / "devnum").is_file():
                bus = int((parent / "busnum").read_text().strip())
                device = int((parent / "devnum").read_text().strip())
                break
        else:
            raise RuntimeError(f"USB bus/device identity unavailable for {key}")
        if not 1 <= bus <= 65535 or not 1 <= device <= 127:
            raise RuntimeError(f"invalid USB bus/device identity for {key}")
        if args.usbmon_interface != "usbmon0" and args.usbmon_interface != f"usbmon{bus}":
            raise RuntimeError(f"{args.usbmon_interface} does not cover {role} on USB bus {bus}; use usbmon0")
        targets.append({"role": role, "device_key": key, "tty": tty, "bus": bus, "device": device})
    return targets


def discover_pair(agent, args):
    result = agent.request("discover", scope="serial" if args.transport == "usb" else "ble",
                           scan_seconds=args.scan_seconds, timeout=args.scan_seconds + 30)
    devices = {item["key"]: item for item in result["devices"]}
    selected = []
    for key in (args.sender_key, args.receiver_key):
        if key not in devices:
            raise RuntimeError(f"device_key not discovered: {key}")
        device = devices[key]
        expected_kind = "serial" if args.transport == "usb" else "ble"
        if device.get("kind") != expected_kind:
            raise RuntimeError(f"unexpected transport for {key}: {device.get('kind')}")
        if device.get("busy"):
            raise RuntimeError(f"device is busy; release it before this run: {key}")
        selected.append(device)
    return selected


BW_VALUES_HZ = {7800, 10400, 15600, 20800, 31250, 41700, 62500, 125000, 250000, 500000}
CFG_RADIO_RE = re.compile(
    r"^\[SYS\] CFG RADIO power=(-?\d+) dBm freq=([\d.]+) MHz sf=(\d+) bw=([\d.]+) kHz$"
)


def scaled_value(text, scale):
    try:
        value = Decimal(str(text)) * scale
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError("value has unsupported precision")
        return int(value)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError(f"invalid radio value: {text}") from exc


def requested_radio(args):
    frequency = scaled_value(args.freq_mhz, 1000000)
    bandwidth = scaled_value(args.bw_khz, 1000)
    if frequency % 1000 or not (
        137000000 <= frequency <= 175000000 or 395000000 <= frequency <= 525000000
    ):
        raise ValueError("freq: шаг 1 кГц, диапазон 137–175 или 395–525 МГц; OOB policy ноды не меняется")
    if bandwidth not in BW_VALUES_HZ or not 7 <= args.sf <= 12 or args.power_dbm not in {*range(2, 18), 20}:
        raise ValueError("unsupported SF/BW/power")
    return {"sf": args.sf, "bandwidth_hz": bandwidth, "power_dbm": args.power_dbm, "frequency_hz": frequency}


class ControlError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class NodeControl:
    def __init__(self, agent, session, timeout):
        self.agent, self.session, self.timeout = agent, session, timeout
        self.broken = False

    def command(self, text, complete):
        deadline = time.monotonic() + self.timeout
        def request(op, **fields):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.broken = True
                raise ControlError("command_timeout")
            try:
                return self.agent.request(op, timeout=remaining, **fields)
            except Exception:
                self.broken = True
                raise
        # Курсор до отправки исключает старые SAVED/readback из предыдущего запроса.
        cursor = request("status", session=self.session)["latest_seq"]
        sent = request("send_line", session=self.session, text=text)
        tx_id = sent["tx_id"]
        lines, written = [], False
        while time.monotonic() < deadline:
            observed = request("observe", cursors={self.session: cursor},
                               timeout_ms=max(1, min(250, int((deadline - time.monotonic()) * 1000))), include_events=True)
            cursor = observed["cursors"][self.session]
            for event in observed.get("events", []):
                if event.get("session", self.session) != self.session:
                    continue
                if event.get("kind") == "state" and event.get("state") in {"disconnected", "reconnecting", "closed"}:
                    self.broken = True
                    raise ControlError("connection_changed")
                if event.get("kind") == "tx" and event.get("tx_id") == tx_id:
                    state = event.get("tx_state")
                    if state in {"failed", "unknown", "cancelled"}:
                        self.broken = True
                        raise ControlError(f"tx_{state}")
                    written |= state == "written"
            for row in observed.get("lines", []):
                if row.get("session", self.session) != self.session:
                    continue
                value = row.get("text", "")
                if value.startswith("[SYS]") and any(marker in value for marker in (" REJECTED", " NOT SAVED", " BUSY")):
                    raise ControlError("node_rejected_or_busy")
                # Preamble, telemetry и BINARY payload остаются только в ST/API logs.
                if value.startswith("[SYS] ") and any(marker in value for marker in (
                    " SAVED", " CFG ", " RADIO_CONFIG", " CFG LINK",
                )):
                    lines.append(value)
            if written and complete(lines):
                return lines
        if not written:
            self.broken = True
        raise ControlError("response_timeout" if written else "tx_not_confirmed")


def parse_config(lines):
    result = {}
    for line in lines:
        match = CFG_RADIO_RE.fullmatch(line)
        if match:
            result.update(power_dbm=int(match[1]), frequency_hz=scaled_value(match[2], 1000000),
                          sf=int(match[3]), bandwidth_hz=scaled_value(match[4], 1000))
        if line.startswith("[SYS] CFG schema="):
            result["storage"] = dict(re.findall(r"(\w+)=([^ ]+)", line)).get("storage")
    return result


def parse_hardware(lines):
    fields = {}
    for line in lines:
        if "RADIO_CONFIG_REGS phase=read " in line or "RADIO_CONFIG_DECODE phase=read " in line:
            fields.update(dict(re.findall(r"(\w+)=([^ ]+)", line)))
    result = {}
    for source, target in (("sf", "sf"), ("bw_Hz", "bandwidth_hz"), ("power_dBm", "power_dbm"),
                           ("frequency_Hz", "frequency_hz"), ("readable", "readable"), ("mode", "mode")):
        if source in fields:
            result[target] = int(fields[source])
    result["bank"] = fields.get("bank")
    return result


def prepare_node(agent, session, requested, timeout, report):
    control = NodeControl(agent, session, timeout)
    commands = (
        ("sf", f"/sf {requested['sf']}", f"[SYS] SF {requested['sf']} SAVED"),
        ("bandwidth_hz", f"/bw {Decimal(requested['bandwidth_hz']) / 1000:f}", None),
        ("power_dbm", f"/power {requested['power_dbm']}", f"[SYS] POWER {requested['power_dbm']} dBm SAVED"),
        ("frequency_hz", f"/freq {Decimal(requested['frequency_hz']) / 1000000:f}", None),
    )
    report["set_results"] = dict.fromkeys(requested, "not_attempted")
    report["errors"], report["mismatches"] = [], {}
    for field, command, exact in commands:
        try:
            if exact is None:
                unit = "kHz" if field == "bandwidth_hz" else "MHz"
                label = "BW" if field == "bandwidth_hz" else "FREQ"
                scale = 1000 if field == "bandwidth_hz" else 1000000
                pattern = re.compile(rf"^\[SYS\] {label} ([\d.]+) {unit} SAVED$")
                def complete(lines):
                    return any((match := pattern.fullmatch(line)) and scaled_value(match[1], scale) == requested[field] for line in lines)
            else:
                def complete(lines):
                    return exact in lines
            control.command(command, complete)
            report["set_results"][field] = "saved"
        except Exception as exc:
            report["set_results"][field] = "failed"
            report["errors"].append({"field": field, "stage": "set", "code": getattr(exc, "code", type(exc).__name__)})
            break
    if not control.broken:
        try:
            lines = control.command("/config", lambda values: any(value.startswith("[SYS] CFG LINK ") for value in values))
            report["config"] = parse_config(lines)
            lines = control.command("/radio read config", lambda values: any("RADIO_CONFIG phase=read " in value for value in values))
            report["hardware"] = parse_hardware(lines)
            lines = control.command("/radio validate config", lambda values: any("RADIO_CONFIG phase=validate " in value for value in values))
            report["validation"] = [dict(re.findall(r"(\w+)=([^ ]+)", value)) for value in lines if "RADIO_CONFIG phase=validate " in value]
            report["hardware_differences"] = [dict(re.findall(r"(\w+)=([^ ]+)", value)) for value in lines if "RADIO_CONFIG_DIFF phase=validate " in value]
        except Exception as exc:
            report["errors"].append({"stage": "readback", "code": getattr(exc, "code", type(exc).__name__)})
    config, hardware = report.get("config", {}), report.get("hardware", {})
    validated = any(row.get("result") == "OK" and row.get("state") == "0" and row.get("mismatches") == "0" for row in report.get("validation", []))
    for field, expected in requested.items():
        matches = config.get(field) == expected
        # Частоту RX сравнивает firmware validator: он учитывает FRF LSB и errata.
        hardware_matches = validated and hardware.get(field) is not None if field == "frequency_hz" else hardware.get(field) == expected
        if not matches or not hardware_matches or report["set_results"][field] != "saved":
            report["mismatches"][field] = {"expected": expected, "config": config.get(field), "hardware": hardware.get(field),
                                           "set_result": report["set_results"][field], "verified": False}
    if not validated or hardware.get("readable") != 1 or hardware.get("bank") != "LoRa" or hardware.get("mode") != 5:
        report["errors"].append({"stage": "hardware_validation", "code": "radio_not_verified_in_rx"})
    if config.get("storage") != "NVS":
        report["errors"].append({"stage": "persistence", "code": "nvs_not_confirmed"})
    report["outcome"] = "PASS" if not report["errors"] and not report["mismatches"] else "FAIL"
    return report["outcome"] == "PASS"


def prepare_radios(agent, args, sessions, summary, run):
    requested = requested_radio(args)
    report = {"requested": requested, "outcome": "FAIL",
              "nodes": {role: {"session": session, "outcome": "NOT_ATTEMPTED"} for role, session in sessions}, "node_status": {
        "outcome": "SKIPPED", "reason": "full node readiness/current-work query not available; M1 STATUS is interface credits/counters only",
        "todo": "TODO_057_NODE_RUNTIME_STATUS",
    }}
    summary["radio_preflight"] = report
    try:
        for role, session in sessions:
            node = report["nodes"][role]
            node["outcome"] = "FAIL"
            if not prepare_node(agent, session, requested, args.preflight_timeout, node):
                raise ControlError(f"radio_preflight_failed:{role}")
        report["outcome"] = "PASS"
    finally:
        write_json(run / "radio_preflight.json", report)


PHASES = {
    "preparing": "подготовка", "compressing": "сжатие",
    "sending": "передача", "receiving": "приём", "resuming": "возобновление",
    "waiting_result": "ожидание RESULT", "repair_requested": "запрос repair",
    "repairing": "repair/доставка", "verifying": "проверка",
    "decompressing": "распаковка", "recovering_local_node": "восстановление ноды",
    "suspended": "приостановлено", "completed": "завершено",
    "failed": "ошибка", "cancelled": "отменено",
}
ACTIVITIES = {
    "recursive_child_started": "приём списка repair",
    "recursive_list_sent": "отправка списка repair",
    "repair_requested": "запрос доставки", "repair_round_sent": "доставка отправлена",
    "control_replay": "повтор управления",
}


def data_progress(snapshot):
    # Во время сжатия bytes_completed относится к исходному файлу, не к DATA.
    if not snapshot or snapshot.get("state") in {"preparing", "compressing"}:
        return None
    total = int(snapshot.get("wire_bytes", 0))
    if total <= 0:
        return None
    done = max(0, min(total, int(snapshot.get("bytes_completed", 0))))
    percentage = min(99.9, 100 * done / total)
    if snapshot.get("state") == "completed":
        percentage = 100.0
    return done, total, percentage


class TransferMonitor:
    def __init__(self, transfer_id, path, *, step=1, clock=time.monotonic):
        if not 1 <= step <= 100:
            raise ValueError("progress step must be between 1 and 100")
        self.step = step
        self.transfer_id = transfer_id
        self.path = path
        self.clock = clock
        self.started = clock()
        self.buckets = {"TX": -1, "RX": -1}
        self.signatures = {}
        self.counters = {}
        self.changed_at = {"TX": self.started, "RX": self.started}
        self.verified = False

    def update(self, sender, receiver=None, *, events=None, verified=False, warnings=()):
        now = self.clock()
        # Чужой/предыдущий ROOT не должен выглядеть как приём текущего файла.
        nodes = {role: snapshot if snapshot and snapshot.get("transfer_id") == self.transfer_id else None
                 for role, snapshot in (("TX", sender), ("RX", receiver))}
        values = {role: data_progress(snapshot) for role, snapshot in nodes.items()}
        emit = not self.signatures or bool(warnings) or verified != self.verified
        details, activities = [], {}
        for role, snapshot in nodes.items():
            snapshot = snapshot or {}
            state = snapshot.get("state", "awaiting_meta")
            repair = snapshot.get("repair") or {}
            signature = (state, repair.get("missing_total"), repair.get("depth"), repair.get("no_progress"))
            emit |= self.signatures.get(role) != signature
            self.signatures[role] = signature
            value = values[role]
            counter = value[:2] if value else None
            previous_counter = self.counters.get(role)
            if previous_counter != counter:
                if previous_counter and counter and counter[0] < previous_counter[0]:
                    emit = True
                self.changed_at[role] = now
                self.counters[role] = counter
            bucket = int(value[2] // self.step) if value else 0
            emit |= bucket != self.buckets[role]
            self.buckets[role] = bucket
            percentage = f"{value[2]:.1f}%" if value else ("0.0%" if state in {"preparing", "compressing"} else "--%")
            phase = PHASES.get(state, "ожидание META" if state == "awaiting_meta" else state)
            detail = f"{role} {percentage} [{phase}]"
            if repair:
                detail += f" repair(запрошено={repair.get('missing_total', '?')},depth={repair.get('depth', '?')}"
                if "no_progress" in repair:
                    detail += f",без_улучшения={repair['no_progress']}"
                detail += ")"
            transitions = []
            for event in (events or {}).get(role, ()):
                label = PHASES.get(event.get("state")) if event.get("kind") == "state" else ACTIVITIES.get(event.get("kind"))
                if label and (not transitions or label != transitions[-1]):
                    transitions.append(label)
            if transitions:
                activities[role] = transitions
                detail += " фазы=" + ("…→" if len(transitions) > 8 else "") + "→".join(transitions[-8:])
                emit = True
            if now - self.changed_at[role] >= 10:
                detail += f" прогресс DATA не менялся {now - self.changed_at[role]:.0f}с"
            details.append(detail)
        delta = None
        tx, rx = values["TX"], values["RX"]
        if tx and rx and tx[1] == rx[1]:
            delta = {"bytes": tx[0] - rx[0], "percentage_points": 100 * (tx[0] - rx[0]) / tx[1]}
            details.append(f"Δ={delta['percentage_points']:+.1f}п.п.")
        elif tx and rx:
            details.append("Δ недоступна: различаются wire_bytes")
        if verified:
            details.append("итог=PASS SHA256=OK")
        details.extend(warnings)
        if not emit:
            return
        row = {"timestamp": datetime.now(timezone.utc).isoformat(), "elapsed": round(now - self.started, 3),
               "transfer_id": self.transfer_id, "TX": nodes["TX"], "RX": nodes["RX"],
               "delta": delta, "activities": activities, "warnings": list(warnings), "verified": verified}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"t={row['elapsed']:.1f}с " + " | ".join(details), flush=True)
        self.verified = verified


def request_budget(deadline, *, phase="file transfer observation"):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(f"{phase} deadline exceeded")
    return min(30, remaining)


def close_settled_transfer(agent, session, transfer_id, *, timeout=5):
    # completed публикуется раньше окончания drain/release. Повторяем только
    # механический close, не отправку файла и не освобождение чужой session.
    deadline = time.monotonic() + timeout
    attempts = 0
    while True:
        attempts += 1
        try:
            result = agent.request("file_transfer_close", session=session, transfer_id=transfer_id,
                                   timeout=request_budget(deadline, phase="file transfer settling"))
            return {"session": session, "attempts": attempts, "result": result}
        except AgentRequestError as exc:
            if exc.error.get("code") != "file_transfer_active":
                raise
            if attempts == 1:
                print(f"фаза=ожидание освобождения передачи session={session}", flush=True)
            remaining = request_budget(deadline, phase="file transfer settling")
            time.sleep(min(.1, remaining))


def observe_transfer(agent, session, transfer_id, cursor, summary, role, *, timeout_ms=0, deadline=None):
    warnings = []
    def page(next_cursor, wait_ms):
        options = {} if deadline is None else {"timeout": request_budget(deadline)}
        if deadline is not None:
            wait_ms = min(wait_ms, max(0, int(options["timeout"] * 1000)))
        try:
            return agent.request("file_transfer_observe", session=session, transfer_id=transfer_id,
                                 cursor=next_cursor, window=100, timeout_ms=wait_ms, **options)
        except AgentRequestError as exc:
            if exc.error.get("code") != "file_cursor_expired":
                raise
            details = exc.error["details"]
            gap = {"role": role, **details}
            summary.setdefault("monitor_event_gaps", []).append(gap)
            warnings.append(f"{role}: пропуск истории событий; см. monitor_event_gaps")
            options = {} if deadline is None else {"timeout": request_budget(deadline)}
            return agent.request("file_transfer_observe", session=session, transfer_id=transfer_id,
                                 cursor=details["oldest_valid_cursor"], window=100, timeout_ms=0, **options)

    result = page(cursor, timeout_ms)
    # Snapshot актуален даже при backlog событий. Окна дочитываем внутри Python,
    # не превращая каждый DATA event в вывод или отдельный model/tool turn.
    events = result.get("events", [])[:]
    head = result.get("head_cursor", result["cursor"])
    while result["cursor"] < head:
        following = page(result["cursor"], 0)
        if following["cursor"] <= result["cursor"]:
            raise RuntimeError("file_transfer_observe cursor did not advance")
        events.extend(following.get("events", []))
        result = following
    return result, events, warnings


def transfer(agent, args, source, summary, captures):
    summary["devices"] = discover_pair(agent, args)
    sessions = []
    for role, key in (("receiver", args.receiver_key), ("sender", args.sender_key)):
        opened = agent.request("open", device_key=key, profile="chatter", wait_connected_ms=20000)
        sessions.append(opened["session"])
        summary[role + "_open"] = opened
        if opened["state"] != "connected":
            raise RuntimeError(f"{role} did not connect")
    receiver, sender = sessions
    print("фаза=настройка и проверка радио TX/RX", flush=True)
    prepare_radios(agent, args, [("receiver", receiver), ("sender", sender)], summary, source.parent.parent)
    started = agent.request("file_send_start", session=sender, path=str(source))
    transfer_id = started["transfer_id"]
    monitor = TransferMonitor(transfer_id, source.parent.parent / "progress.jsonl", step=args.progress_step)
    monitor.update(started)
    summary["transfer_id"] = transfer_id
    cursor = receiver_cursor = 0
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        for capture in captures:
            capture.check()
        sampled_at = time.monotonic()
        observed, tx_events, warnings = observe_transfer(
            agent, sender, transfer_id, cursor, summary, "TX", timeout_ms=1000, deadline=deadline)
        cursor = observed["cursor"]
        summary["sender_transfer"] = observed["progress"]
        status = agent.request("status", session=receiver, timeout=request_budget(deadline))
        summary["receiver_status"] = status
        progress = observed["progress"]
        incoming = status.get("file_transfer") or {}
        rx_events = []
        if incoming.get("transfer_id") == transfer_id:
            rx_observed, rx_events, rx_warnings = observe_transfer(
                agent, receiver, transfer_id, receiver_cursor, summary, "RX", deadline=deadline)
            receiver_cursor = rx_observed["cursor"]
            incoming = rx_observed["progress"]
            summary["receiver_status"]["file_transfer"] = incoming
            warnings.extend(rx_warnings)
        monitor.update(progress, incoming, events={"TX": tx_events, "RX": rx_events}, warnings=warnings)
        if status.get("state") in {"disconnected", "failed", "closed"}:
            raise RuntimeError(f"receiver disconnected: {status.get('state')}")
        if incoming.get("transfer_id") == transfer_id and incoming.get("state") in {"failed", "cancelled"}:
            raise RuntimeError(f"receiver transfer failed: {incoming.get('failure')}")
        if progress["state"] in TERMINAL:
            if progress["state"] != "completed":
                raise RuntimeError(f"sender transfer failed: {progress}")
            if incoming.get("transfer_id") == transfer_id and incoming.get("state") == "completed":
                destination = Path(incoming["final_path"]).resolve()
                destination.relative_to(source.parent.parent / "received")
                summary["received"] = fingerprint(destination)
                expected = summary["source"]
                if any(summary["received"][field] != expected[field] for field in ("bytes", "sha256")):
                    raise RuntimeError("received size/SHA-256 mismatch")
                summary["transfer_close"] = []
                for session in (sender, receiver):
                    summary["transfer_close"].append(close_settled_transfer(agent, session, transfer_id))
                for session in (sender, receiver):
                    closed = agent.request("close", session=session)
                    summary.setdefault("session_close", []).append(closed)
                    release = closed.get("transport_release")
                    if args.transport == "ble" and (not release or release.get("result") != "disconnected"):
                        raise RuntimeError(f"BLE release not confirmed: {closed}")
                monitor.update(progress, incoming, verified=True)
                summary["outcome"] = "PASS"
                return
        # Ограничиваем частоту выборок; progress events будят long-poll сразу.
        time.sleep(max(0, min(1 - (time.monotonic() - sampled_at), deadline - time.monotonic())))
    raise TimeoutError(f"run deadline exceeded ({args.timeout}s); no automatic resend/cancel")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--transport", choices=("usb", "ble"), required=True)
    p.add_argument("--sender-key", required=True, help="точный device_key из JSONL discover")
    p.add_argument("--receiver-key", required=True)
    p.add_argument("--sf", type=int, default=7, choices=range(7, 13))
    p.add_argument("--bw-khz", default="500", help="bandwidth обеих нод, кГц")
    p.add_argument("--power-dbm", type=int, default=2, choices=[*range(2, 18), 20])
    p.add_argument("--freq-mhz", default="470", help="частота обеих нод, МГц; по умолчанию 470")
    p.add_argument("--preflight-timeout", type=float, default=5, help="предел ожидания каждого config/readback ответа, секунды; по умолчанию 5")
    p.add_argument("--file", type=Path, help="файл; по умолчанию воспроизводимые 1 МиБ")
    p.add_argument("--size", type=int, default=1048576, help="размер генерируемого файла в байтах")
    p.add_argument("--journal-root", type=Path, default=JOURNAL)
    p.add_argument("--timeout", type=float, default=3600, help="общий предел передачи, секунды; по умолчанию 3600 (1 час)")
    p.add_argument("--progress-step", type=int, default=1, choices=range(1, 101),
                   help="шаг stdout в процентах отдельно для TX/RX; по умолчанию 1, например 10 для редкого вывода")
    p.add_argument("--scan-seconds", type=float, default=5)
    p.add_argument("--capture", choices=("auto", "both", "none"), default="auto")
    p.add_argument("--capture-sudo", action="store_true", help="sudo -n только для packet capture")
    p.add_argument("--hci-index", default="0")
    p.add_argument("--usbmon-interface", default="usbmon0",
                   help="USB capture interface; default: usbmon0 (all USB buses)")
    p.add_argument("--skip-analysis", action="store_true",
                   help="только прогон: сохранить все логи без запуска анализатора; проверка completed/размера/SHA остаётся")
    p.add_argument("--execute", action="store_true", help="без флага только показать план, без аппаратных действий")
    return p


def checkpoint():
    info = {}
    for name, command in {
        "head": ["git", "rev-parse", "HEAD"], "branch": ["git", "branch", "--show-current"],
        "status": ["git", "status", "--porcelain"], "diff": ["git", "diff", "--binary", "HEAD"],
    }.items():
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=10)
        info[name] = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    # Dirty untracked runtime/tests тоже входят в checkpoint, но не копируются из чужих каталогов.
    info["runtime_sha256"] = {
        str(path.relative_to(ROOT)): fingerprint(path)["sha256"]
        for path in sorted((ROOT / "src").rglob("*.py"))
    }
    info["entrypoint"] = fingerprint(ROOT / "serialterminal.py")
    info["python"] = sys.version
    info["executable"] = sys.executable
    return info


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.sender_key == args.receiver_key:
        p.error("sender and receiver must be different devices")
    if args.size <= 0 or any(not math.isfinite(value) or value <= 0 for value in (args.timeout, args.scan_seconds)):
        p.error("size must be positive; timeout and scan-seconds must be finite and positive")
    if args.file and not args.file.is_file():
        p.error("--file must name an existing regular file")
    try:
        radio = requested_radio(args)
    except ValueError as exc:
        p.error(str(exc))
    if not math.isfinite(args.preflight_timeout) or args.preflight_timeout <= 0:
        p.error("preflight-timeout must be finite and positive")
    plan = vars(args).copy()
    plan["radio"] = radio
    plan.update(scenario="file through LoRa; both host links use selected transport",
                physical_firmware_version="must be confirmed from node evidence; not inferred from source")
    if not args.execute:
        print(json.dumps(plan, default=str, ensure_ascii=False, indent=2))
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run = args.journal_root.resolve() / f"{stamp}_ft1_{args.transport}"
    run.mkdir(parents=True, exist_ok=False)
    with (run / "runner.stdout.log").open("x", encoding="utf-8") as logfile:
        with redirect_stdout(RunStdout(sys.stdout, logfile)):
            print(run, flush=True)
            write_json(run / "plan.json", {k: str(v) if isinstance(v, Path) else v for k, v in plan.items()})
            summary = {
                "outcome": "BLOCKED", "transport": args.transport, "started_utc": stamp, "captures": [],
                "analysis_skipped": args.skip_analysis,
                "st_logs": {"primary": "serialterminal.log", "console": "serialterminal.console.log",
                            "timing": "serialterminal.fttiming.jsonl", "application": "serialterminal.application.log"},
            }
            captures, agent = [], None
            try:
                for script in (Path(__file__), ROOT / "scripts" / "analyze_file_transfer.py"):
                    shutil.copy2(script, run / script.name)
                write_json(run / "checkpoint.json", checkpoint())
                (run / "sent").mkdir()
                (run / "received").mkdir()
                source = run / "sent" / (args.file.name if args.file else "payload-1MiB.bin")
                if args.file:
                    shutil.copy2(args.file, source)
                else:
                    make_payload(source, args.size)
                summary["source"] = fingerprint(source)
                capture_preflight(args, run)
                summary["usb_capture_targets"] = usb_capture_targets(args)
                for name, command, output in capture_commands(args, run):
                    capture = Capture(name, command, output, run)
                    captures.append(capture)
                    capture.ready()
                agent = Agent(run)
                summary["outcome"] = "FAIL"
                transfer(agent, args, source, summary, captures)
            except KeyboardInterrupt:
                summary.update(outcome="INTERRUPTED", error="operator interrupt")
            except Exception as exc:
                if summary["outcome"] == "PASS":
                    summary["outcome"] = "FAIL"
                summary["error"] = f"{type(exc).__name__}: {exc}"
                (run / "runner.application.log").write_text(traceback.format_exc(), encoding="utf-8")
            finally:
                if agent is not None:
                    try:
                        summary["agent_exit"] = agent.close()
                        if summary["agent_exit"]["forced"] or summary["agent_exit"]["returncode"]:
                            summary["outcome"] = "FAIL"
                    except Exception as exc:
                        summary.update(outcome="FAIL", cleanup_error=str(exc))
                for capture in reversed(captures):
                    try:
                        info = capture.stop()
                        summary["captures"].append(info)
                        if info["early_exit"] or info["forced"] or info["returncode"] not in (0, -signal.SIGINT):
                            summary["capture_incomplete"] = True
                    except Exception as exc:
                        summary.setdefault("capture_errors", []).append(str(exc))
                        summary["capture_incomplete"] = True
                if summary.get("capture_incomplete") and summary["outcome"] == "PASS":
                    summary["outcome"] = "INCONCLUSIVE"
                summary["ended_utc"] = datetime.now(timezone.utc).isoformat()
                write_json(run / "result.json", summary)
            if args.skip_analysis:
                print(f"Итог раннера: {summary['outcome']}; анализ логов пропущен (--skip-analysis)", flush=True)
                return 0 if summary["outcome"] == "PASS" else 1
            result = subprocess.run([sys.executable, str(run / "analyze_file_transfer.py"), str(run)],
                                    text=True, capture_output=True)
            (run / "analyzer.stderr.log").write_text(result.stderr, encoding="utf-8")
            sys.stdout.write(result.stdout)
            sys.stdout.flush()
            return 0 if summary["outcome"] == "PASS" and result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

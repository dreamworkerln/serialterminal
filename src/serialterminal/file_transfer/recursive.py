from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
import os
from pathlib import Path
import struct
import threading
import time

from . import core, manager, resumable
from .protocol import (
    EndMessage, FileProtocolError, MetaMessage, MissingMessage, MissingRange,
    ResultMessage, canonical_missing_ranges, decode_message, parse_transfer_id,
    transfer_id_text, validate_missing_ranges,
)

FILE_MAX_MISSING_PERCENT = 30
FILE_MAX_RECURSION_DEPTH = 8
FILE_MAX_NO_PROGRESS_CYCLES = 3
_LIST_HEADER = struct.Struct('>4sQII')
_LIST_RANGE = struct.Struct('>II')
_LIST_MAGIC = b'MRF2'


@dataclass
class _Frame:
    record: core._TransferRecord
    parent_id: int = 0
    depth: int = 0
    meta: MetaMessage | None = None
    incoming: object | None = None
    child_id: int | None = None
    request_id: int = 0
    previous_missing: int | None = None
    no_progress: int = 0
    last_end: EndMessage | None = None
    deferred_end: EndMessage | None = None
    requests: deque = field(default_factory=deque)
    processed: dict = field(default_factory=dict)
    service_request: MissingMessage | None = None
    settled: bool = False
    cancel_queued: bool = False
    ending: bool = False


def write_missing_list(path, parent_id, ranges):
    validate_missing_ranges(ranges)
    total = sum(item.count for item in ranges)
    with path.open('wb') as handle:
        handle.write(_LIST_HEADER.pack(_LIST_MAGIC, parent_id, total, len(ranges)))
        for item in ranges:
            handle.write(_LIST_RANGE.pack(item.start_chunk, item.count))
        handle.flush()
        os.fsync(handle.fileno())
    return total


def read_missing_list(path, parent_id, chunk_count, request_id):
    with path.open('rb') as handle:
        header = handle.read(_LIST_HEADER.size)
        if len(header) != _LIST_HEADER.size:
            raise FileProtocolError('truncated missing-list header')
        magic, actual_parent, total, count = _LIST_HEADER.unpack(header)
        if magic != _LIST_MAGIC or actual_parent != parent_id:
            raise FileProtocolError('missing-list magic/parent mismatch')
        if not 0 < count <= total <= chunk_count:
            raise FileProtocolError('missing-list count/total exceeds parent')
        if path.stat().st_size != _LIST_HEADER.size + count * _LIST_RANGE.size:
            raise FileProtocolError('missing-list length mismatch')
        ranges = tuple(MissingRange(*_LIST_RANGE.unpack(handle.read(_LIST_RANGE.size))) for _ in range(count))
    validate_missing_ranges(ranges, chunk_count=chunk_count)
    if sum(item.count for item in ranges) != total:
        raise FileProtocolError('missing-list total mismatch')
    return MissingMessage(parent_id, ranges, request_id=request_id)


def initialize(self, *args, max_missing_percent=FILE_MAX_MISSING_PERCENT,
               max_recursion_depth=FILE_MAX_RECURSION_DEPTH,
               max_no_progress_cycles=FILE_MAX_NO_PROGRESS_CYCLES, **kwargs):
    if isinstance(max_missing_percent, bool) or not isinstance(max_missing_percent, int) or not 0 <= max_missing_percent <= 100:
        raise ValueError('max_missing_percent must be an integer in 0..100')
    if (type(max_recursion_depth) is not int or not 1 <= max_recursion_depth <= 8 or
            type(max_no_progress_cycles) is not int or max_no_progress_cycles < 1):
        raise ValueError('invalid recursive repair limits')
    self.max_missing_percent = max_missing_percent
    self.max_recursion_depth = max_recursion_depth
    self.max_no_progress_cycles = max_no_progress_cycles
    self._recursive_frames = {}
    self._recursive_root_id = None
    manager.initialize(self, *args, **kwargs)


def _claim(self, transfer_id, direction):
    frame = self._recursive_frames.get(transfer_id)
    if frame is None or not frame.parent_id:
        core.FileTransferManager._claim(self, transfer_id, direction)


def _release(self, transfer_id, direction):
    frame = self._recursive_frames.get(transfer_id)
    if frame is None or not frame.parent_id:
        core.FileTransferManager._release(self, transfer_id, direction)
    if frame is not None:
        frame.settled = True


def _incoming_for(self, transfer_id):
    with self._lock:
        frame = self._recursive_frames.get(transfer_id)
        if frame is not None:
            if frame.record is None or frame.ending or frame.record.state in core._TERMINAL_STATES:
                return None
            return frame.incoming
        return core.FileTransferManager._incoming_for(self, transfer_id)


def _send_worker(self, record, path):
    with self._lock:
        existing = self._recursive_frames.get(record.transfer_id)
        if existing is None or not existing.parent_id:
            self._recursive_frames[record.transfer_id] = _Frame(record)
            self._recursive_root_id = record.transfer_id
    resumable._send_worker(self, record, path)


def _send_message_direct(self, message, *, cancel_event, deadline=None):
    if isinstance(message, MetaMessage):
        with self._lock:
            frame = self._recursive_frames.get(message.transfer_id)
            if frame is not None:
                message = replace(message, parent_transfer_id=frame.parent_id, depth=frame.depth)
                frame.meta = message
    elif isinstance(message, EndMessage):
        with self._lock:
            frame = self._recursive_frames.get(message.transfer_id)
            if frame is not None:
                frame.last_end = message
    resumable._send_message_direct(self, message, cancel_event=cancel_event, deadline=deadline)


def _handle_meta(self, meta):
    with self._control_admission_scope():
        existing_frame = self._recursive_frames.get(meta.transfer_id)
        if (existing_frame is not None and existing_frame.meta == meta and
                existing_frame.record is not None and
                existing_frame.record.state not in {'failed', 'cancelled', 'suspended'}):
            if existing_frame.record.state == 'completed':
                self._send_result_async(existing_frame.record, ResultMessage(meta.transfer_id, True, 'ok', ''))
            elif existing_frame.incoming is not None and existing_frame.child_id is None:
                self._send_resume(existing_frame.incoming)
            return
        if meta.parent_transfer_id:
            parent = self._recursive_frames.get(meta.parent_transfer_id)
            if parent is not None and meta.transfer_id in parent.processed:
                if parent.processed[meta.transfer_id] == meta:
                    self._send_result_async(None, ResultMessage(meta.transfer_id, True, 'ok', ''))
                else:
                    self._reject_incoming(meta.transfer_id, 'protocol_error', 'conflicting completed list identity')
                return
            if (parent is None or parent.record.direction != 'TX' or
                    parent.record.state in core._TERMINAL_STATES or parent.last_end is None or
                    parent.child_id is not None or meta.depth != parent.depth + 1 or
                    meta.depth > self.max_recursion_depth or
                    meta.original_size > _LIST_HEADER.size + _LIST_RANGE.size * parent.record.chunks_total):
                self._reject_incoming(meta.transfer_id, 'protocol_error', 'unexpected missing-list parent/depth/size')
                return
            # Родитель сохраняет внешний lease. Дочерний admission временно
            # использует тот же manager, RX worker и единственный outbox.
            active, incoming = self._active_id, self._incoming
            frame = _Frame(None, parent_id=meta.parent_transfer_id, depth=meta.depth, meta=meta)
            self._recursive_frames[meta.transfer_id] = frame
            self._active_id = None
            self._incoming = None
            try:
                manager._handle_meta(self, meta)
                record = self._records.get(meta.transfer_id)
                if record is None or self._incoming is None or record.state in core._TERMINAL_STATES:
                    self._recursive_frames.pop(meta.transfer_id, None)
                    return
                frame.record = record
                frame.incoming = self._incoming
                parent.child_id = meta.transfer_id
                parent.record.event('recursive_child_started', child_id=transfer_id_text(meta.transfer_id), depth=meta.depth)
                with parent.record._condition:
                    parent.record._condition.notify_all()
            except Exception:
                frame.record = self._records.get(meta.transfer_id)
                frame.incoming = self._incoming
                if frame.record is None or frame.incoming is None:
                    self._recursive_frames.pop(meta.transfer_id, None)
                else:
                    parent.child_id = meta.transfer_id
                raise
            finally:
                self._active_id = active
                if meta.transfer_id not in self._recursive_frames:
                    self._incoming = incoming
            return
        manager._handle_meta(self, meta)
        record = self._records.get(meta.transfer_id)
        if record is not None and record.state not in core._TERMINAL_STATES:
            self._recursive_frames[meta.transfer_id] = _Frame(record, meta=meta, incoming=self._incoming)
            self._recursive_root_id = meta.transfer_id


def _start_list(self, parent, ranges):
    with self._lock:
        child_id = self._new_transfer_id_locked()
        path = self._resume_store.root / 'recursive' / f'{transfer_id_text(child_id)}.missing'
        path.parent.mkdir(parents=True, exist_ok=True)
        total = write_missing_list(path, parent.record.transfer_id, ranges)
        self._fsync_directory(path.parent)
        record = core._TransferRecord(child_id, direction='TX', filename=path.name,
                                      event_retention=self.event_retention, event_sink=self.event_sink)
        self._records[child_id] = record
        self._recursive_frames[child_id] = _Frame(record, parent_id=parent.record.transfer_id, depth=parent.depth + 1)
        parent.child_id = child_id
        parent.request_id = child_id
        parent.record.set_state('repair_requested')
        parent.record.event('recursive_list_sent', child_id=transfer_id_text(child_id), depth=parent.depth + 1,
                            missing_total=total, ranges=len(ranges))
        thread = threading.Thread(target=self._send_worker, args=(record, path),
                                  name=f'serialterminal-file-tx-{transfer_id_text(child_id)}', daemon=True)
        record._thread = thread
        try:
            thread.start()
        except Exception:
            parent.child_id = None
            self._recursive_frames.pop(child_id, None)
            self._records.pop(child_id, None)
            path.unlink(missing_ok=True)
            raise


def _handle_end(self, message):
    frame = self._recursive_frames.get(message.transfer_id)
    incoming = self._incoming_for(message.transfer_id)
    if frame is None or incoming is None:
        resumable._handle_end(self, message)
        return
    if message.chunk_count != frame.record.chunks_total:
        resumable._handle_end(self, message)
        return
    if message.repair_id != frame.request_id:
        frame.record.event('end_ignored', reason='stale_repair_id', repair_id=transfer_id_text(message.repair_id))
        return
    if frame.child_id is not None:
        # RESULT дочернего TX может разбудить peer раньше, чем локальный worker
        # освободит child context. Сохраняем только END этой ожидаемой досылки.
        child = self._recursive_frames.get(frame.child_id)
        if child and child.record.direction == 'TX' and child.record.remote_result and child.record.remote_result.ok:
            frame.deferred_end = message
        return
    missing = self._missing_indexes(incoming)
    if not missing:
        resumable._handle_end(self, message)
        return
    try:
        self._checkpoint_incoming(incoming, force=True)
        total = len(missing)
        if frame.depth == 0 and 100 * total > self.max_missing_percent * frame.record.chunks_total:
            raise core.FileTransferError('missing_percent_exceeded',
                                        f'{total}/{frame.record.chunks_total} chunks missing; threshold {self.max_missing_percent}%', phase='repairing')
        if frame.previous_missing is not None:
            frame.no_progress = 0 if total < frame.previous_missing else frame.no_progress + 1
        frame.previous_missing = total
        frame.record.repair_progress = {'missing_total': total, 'no_progress': frame.no_progress, 'depth': frame.depth}
        frame.record.event('repair_progress', **frame.record.repair_progress)
        if frame.no_progress >= self.max_no_progress_cycles:
            raise core.FileTransferError('repair_no_progress', f'{self.max_no_progress_cycles} consecutive repair cycles made no progress', phase='repairing')
        if frame.depth >= self.max_recursion_depth:
            raise core.FileTransferError('recursion_depth_limit', 'missing list would exceed recursive repair depth', phase='repairing')
        ranges = canonical_missing_ranges(missing, chunk_count=frame.record.chunks_total)
        self._start_list(frame, ranges)
    except core.FileTransferError as exc:
        self._fail_incoming(incoming, exc)
    except Exception as exc:
        self._fail_incoming(incoming, core.FileTransferError('storage_failed', str(exc), phase='repairing'))


def _fail_incoming(self, incoming, failure, *, terminal_state='failed'):
    frame = self._recursive_frames.get(incoming.record.transfer_id)
    if frame is not None:
        if frame.ending or incoming.record.state in core._TERMINAL_STATES:
            return
        frame.ending = True
    resumable._fail_incoming(self, incoming, failure, terminal_state=terminal_state)


def display_snapshot(self):
    # Вложенный RESULT/cancel не подменяет пользовательский ROOT в TUI/status.
    # После close ROOT внутренние terminal records не показываем как новый файл.
    with self._lock:
        root = self._records.get(self._recursive_root_id)
        if root is not None:
            return root.snapshot()
        if self._recursive_root_id is not None:
            return None
    return resumable.display_snapshot(self)


def _publish_verified(self, incoming, end, final_temp):
    frame = self._recursive_frames.get(incoming.meta.transfer_id)
    if frame is None or not frame.parent_id:
        return resumable._publish_verified(self, incoming, end, final_temp)
    parent = self._recursive_frames[frame.parent_id]
    try:
        frame.service_request = read_missing_list(final_temp, frame.parent_id,
                                                 parent.record.chunks_total, frame.record.transfer_id)
    except FileProtocolError as exc:
        raise core.FileTransferError('protocol_error', str(exc), phase='verifying') from exc
    # Служебный файл проверен тем же FT1 engine, но не публикуется в Downloads.
    # Контекст хранит разобранный запрос до settlement RESULT и снятия child.
    return final_temp


def _terminal_record_settled(self, record, state, *, failure=None, final_path=None):
    frame = self._recursive_frames.get(record.transfer_id)
    if frame is not None and not frame.parent_id and state != 'completed':
        _cancel_descendants(self, frame)
    core.FileTransferManager._terminal_record_settled(self, record, state, failure=failure, final_path=final_path)
    if record.state not in core._TERMINAL_STATES or frame is None:
        return
    if not frame.settled:
        # Drain failure оставляет child context и внешний lease занятыми.
        # Нельзя выдать его удаление за завершение host write.
        self._abort_recursive(core.FileTransferError(
            record.failure['code'], record.failure['message'], phase='settling'), record.transfer_id)
        return
    if record.state != state:
        failure = core.FileTransferError(record.failure['code'], record.failure['message'], phase='settling')
    if frame.parent_id:
        parent = self._recursive_frames.get(frame.parent_id)
        if parent is not None:
            with self._lock:
                parent.child_id = None
                if self._incoming is frame.incoming or self._incoming is None:
                    self._incoming = parent.incoming if parent.record.state not in core._TERMINAL_STATES else None
                if record.state == 'completed' and frame.service_request is not None:
                    parent.processed[record.transfer_id] = frame.meta
                    parent.requests.append(frame.service_request)
                with parent.record._condition:
                    parent.record._condition.notify_all()
            if record.state != 'completed':
                self._abort_recursive(failure or core.FileTransferError('remote_failed', 'missing-list transfer failed'), record.transfer_id)
            elif parent.deferred_end is not None:
                end = parent.deferred_end
                parent.deferred_end = None
                self._enqueue_rx(end)
        # Две session одного процесса могут иметь общий receive_dir. TX не
        # владеет RX partial с тем же ID, а RX не владеет исходником peer TX.
        if record.direction == 'TX':
            self._resume_store.delete_outgoing(record.transfer_id)
            path = self._resume_store.root / 'recursive' / f'{transfer_id_text(record.transfer_id)}.missing'
            path.unlink(missing_ok=True)
        else:
            self._resume_store.delete_incoming(record.transfer_id, delete_part=True)
        self._recursive_frames.pop(record.transfer_id, None)
    elif record.state != 'completed':
        self._abort_recursive(failure or core.FileTransferError('remote_failed', 'root transfer failed'), record.transfer_id)


def _root_frame(self, transfer_id):
    frame = self._recursive_frames.get(transfer_id)
    while frame is not None and frame.parent_id:
        frame = self._recursive_frames.get(frame.parent_id)
    return frame


def _cancel_descendants(self, root):
    for frame in list(self._recursive_frames.values()):
        if not frame.parent_id or frame.record is None or _root_frame(self, frame.record.transfer_id) is not root:
            continue
        if frame.record.state in core._TERMINAL_STATES:
            continue
        frame.record.cancel_event.set()
        with frame.record._condition:
            frame.record._condition.notify_all()
        if frame.incoming is not None and not frame.cancel_queued:
            frame.cancel_queued = True
            # RX child не имеет TX worker: одного cancel_event недостаточно,
            # иначе он остаётся до idle timeout и может мешать следующему ROOT.
            self._enqueue_rx(core._CancelIncoming(frame.record.transfer_id))


def _abort_recursive(self, failure, transfer_id=None):
    root = _root_frame(self, self._recursive_root_id if transfer_id is None else transfer_id)
    if root is None:
        return
    _cancel_descendants(self, root)
    if root.record.state in core._TERMINAL_STATES:
        return
    # remote_failed описывает локальную обёртку отрицательного RESULT.
    # При подъёме ошибки дочернего файла сохраняем исходный код peer в ROOT.
    remote_code = failure.details.get('remote_code')
    if failure.code == 'remote_failed' and isinstance(remote_code, str):
        failure = core.FileTransferError(remote_code, failure.message,
                                         phase=failure.phase, details=failure.details)
    root.record.event('recursive_operation_failed', code=failure.code, error=str(failure))
    if root.record.direction == 'TX':
        root.record.set_remote_result(ResultMessage(root.record.transfer_id, False, failure.code, failure.message))
    elif root.incoming is not None:
        self._fail_incoming(root.incoming, failure)


def _await_remote_completion(self, record, prepared, *, meta, end, chunk_size):
    frame = self._recursive_frames[record.transfer_id]
    control_replays = 0
    interval = self._timing_budget_s("control", self.control_replay_interval_s)
    if self.result_timeout_s is not None:
        # Явный result_timeout_s ограничивает один control wait,
        # а не длительность repair/child.
        interval = min(interval, self.result_timeout_s)
    while True:
        record.set_state('waiting_result')
        deadline = time.monotonic() + interval
        with record._condition:
            while record.remote_result is None and not frame.requests:
                if record.cancel_event.is_set():
                    raise core.FileTransferCancelled()
                if getattr(record, 'control_overflow', False):
                    raise core.FileTransferError('control_queue_overflow', 'bounded FT1 control queue overflow', phase='waiting_result')
                if self._stopping.is_set():
                    raise core.FileTransferError('local_shutdown', 'manager stopped', phase='waiting_result')
                if frame.child_id is not None:
                    # Время дочернего обмена не расходует ожидание родителя.
                    record._condition.wait()
                    deadline = time.monotonic() + interval
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                record._condition.wait(remaining)
            if record.remote_result is not None:
                return record.remote_result
            request = frame.requests.popleft() if frame.requests else None
        if request is not None:
            total = sum(item.count for item in request.ranges)
            record.repair_progress = {'missing_total': total, 'depth': frame.depth}
            record.event('repair_progress', **record.repair_progress)
            self._send_requested_chunks(record, prepared, request, chunk_size=chunk_size)
            end = replace(end, repair_id=request.request_id)
            self._send_message(end, cancel_event=record.cancel_event)
            control_replays = 0
            continue
        if control_replays >= self.max_control_replays:
            raise core.FileTransferError('remote_result_timeout', 'peer did not answer bounded control replay', phase='waiting_result')
        control_replays += 1
        record.event('control_replay', attempt=control_replays, maximum=self.max_control_replays)
        self._send_message(meta, cancel_event=record.cancel_event)
        self._send_message(end, cancel_event=record.cancel_event)


def _expire_stale_incoming(self):
    incoming = self._incoming
    if incoming is not None:
        frame = self._recursive_frames.get(incoming.meta.transfer_id)
        if frame is not None and frame.child_id is not None:
            return
    manager._expire_stale_incoming(self)


def cancel(self, transfer_id):
    root = _root_frame(self, parse_transfer_id(transfer_id))
    if root is not None:
        _cancel_descendants(self, root)
    return core.FileTransferManager.cancel(self, transfer_id)


def feed_binary(self, payload):
    try:
        message = decode_message(payload)
    except FileProtocolError:
        return
    if isinstance(message, MissingMessage):
        # В текущем протоколе запрос принимается только из проверенного
        # служебного файла; compact MISSING не запускает скрытый второй repair.
        with self._lock:
            record = self._records.get(message.transfer_id)
        if record is not None and record.direction == "TX" and record.state not in core._TERMINAL_STATES:
            record.set_remote_result(ResultMessage(message.transfer_id, False, "protocol_error", "compact MISSING is unsupported"))
        return
    resumable.feed_binary(self, payload)


def close(self):
    # Persistent stack не восстанавливаем автоматически: сохраняем ROOT partial,
    # останавливаем внутренние сессии и позволяем явный ROOT resume после restart.
    try:
        resumable._stop_receiver_for_close(self)
        for frame in list(self._recursive_frames.values()):
            if frame.record is None or frame.ending or frame.record.state in core._TERMINAL_STATES:
                continue
            if frame.record.cancel_event.is_set() and not getattr(frame.record, "_shutdown_suspend", False):
                # Явная отмена могла ещё стоять в RX queue. Не превращаем её
                # в suspend и не восстанавливаем manifest удалённого partial.
                if frame.incoming is not None:
                    self._cancel_incoming(frame.record.transfer_id)
                continue
            # После publication исходного .part уже нет: повторный checkpoint
            # при закрытии не должен восстановить RX поверх завершённого файла.
            if frame.parent_id and frame.incoming is not None and not getattr(frame.incoming, "_publication_committed", False):
                self._checkpoint_incoming(frame.incoming, status='suspended', force=True)
            frame.record._shutdown_suspend = True
            frame.record.cancel_event.set()
            with frame.record._condition:
                frame.record._condition.notify_all()
        root = self._recursive_frames.get(self._recursive_root_id)
        if root is not None and not root.ending and root.incoming is not None and not getattr(root.incoming, "_publication_committed", False) and root.record.state not in core._TERMINAL_STATES:
            self._incoming = root.incoming
    finally:
        resumable.close(self)

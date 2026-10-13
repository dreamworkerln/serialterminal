from __future__ import annotations

from . import core, manager, pipeline_manager, resumable


class FileTransferManager(core.FileTransferManager):
    """Единый runtime owner; recovery/storage/pipeline — составные политики."""

    __init__ = manager.initialize
    _await_resume = resumable._await_resume
    _can_revive_timed_out_receiver = manager._can_revive_timed_out_receiver
    _checkpoint_incoming = manager._checkpoint_incoming
    _chunk_count = staticmethod(resumable._chunk_count)
    _cleanup_published = resumable._cleanup_published
    _completed_matches_meta = manager._completed_matches_meta
    _data_pipeline = pipeline_manager._data_pipeline
    _discard_data_pipeline = pipeline_manager._discard_data_pipeline
    _earliest_missing = staticmethod(resumable._earliest_missing)
    _expire_stale_incoming = manager._expire_stale_incoming
    _fail_incoming = resumable._fail_incoming
    _finish_early_result = resumable._finish_early_result
    _handle_data = resumable._handle_data
    _handle_end = resumable._handle_end
    _handle_meta = manager._handle_meta
    _handle_sender_cancel = resumable._handle_sender_cancel
    _load_received = resumable._load_received
    _missing_indexes = staticmethod(resumable._missing_indexes)
    _path_is_direct_receive_file = manager._path_is_direct_receive_file
    _pipeline_fallback = pipeline_manager._pipeline_fallback
    _prepare_source = manager._prepare_source
    _publish_verified = resumable._publish_verified
    _raise_binary_failure = resumable._raise_binary_failure
    _reconcile_published = manager._reconcile_published
    _recovery_pause = resumable._recovery_pause
    _replay_completed_end = manager._replay_completed_end
    _restore_incoming = manager._restore_incoming
    _save_sender_journal = manager._save_sender_journal
    _send_chunks_from = pipeline_manager._send_chunks_from
    _send_message_direct = resumable._send_message_direct
    _send_resume = resumable._send_resume
    _send_worker = resumable._send_worker
    _sender_resume_candidate = manager._sender_resume_candidate
    _start_new_incoming = manager._start_new_incoming
    _suspend_incoming = resumable._suspend_incoming
    _terminal_record = manager._terminal_record
    _valid_publishing_destination = resumable._valid_publishing_destination
    _validated_sender_candidate = manager._validated_sender_candidate
    _verify_resume_wire = staticmethod(manager._verify_resume_wire)
    close = resumable.close
    display_snapshot = resumable.display_snapshot
    feed_binary = resumable.feed_binary
    start_send = resumable.start_send

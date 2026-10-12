"""Разбор фактически отправленных FT1 файлов дырок для assertions тестов."""
import gzip
import hashlib
import struct

from serialterminal.file_transfer import Compression, DataMessage, EndMessage, MetaMessage, MissingMessage, MissingRange, decode_message


def service_requests(messages, parent_id):
    decoded = [decode_message(item) if isinstance(item, bytes) else item for item in list(messages)]
    metadata = {}
    for message in decoded:
        if isinstance(message, MetaMessage) and message.parent_transfer_id == parent_id:
            assert metadata.setdefault(message.transfer_id, message) == message
    result = []
    for transfer_id, meta in metadata.items():
        ends = [m for m in decoded if isinstance(m, EndMessage) and m.transfer_id == transfer_id]
        if not ends:
            continue
        blocks = {}
        for message in decoded:
            if isinstance(message, DataMessage) and message.transfer_id == transfer_id:
                assert blocks.setdefault(message.chunk_index, message.payload) == message.payload
        end = ends[-1]
        if set(blocks) != set(range(end.chunk_count)):
            continue
        wire = b''.join(blocks[i] for i in range(end.chunk_count))
        assert len(wire) == meta.wire_size
        assert hashlib.sha256(wire).digest() == end.wire_sha256
        raw = gzip.decompress(wire) if meta.compression == Compression.GZIP else wire
        assert len(raw) == meta.original_size
        assert hashlib.sha256(raw).digest() == meta.original_sha256
        magic, parent, total, count = struct.unpack('>4sQII', raw[:20])
        assert magic == b'MRF2' and parent == parent_id
        assert len(raw) == 20 + 8 * count
        ranges = tuple(MissingRange(*struct.unpack('>II', raw[offset:offset+8])) for offset in range(20,len(raw),8))
        assert sum(r.count for r in ranges) == total
        assert meta.depth >= 1
        result.append(MissingMessage(parent_id,ranges,request_id=transfer_id))
    return result

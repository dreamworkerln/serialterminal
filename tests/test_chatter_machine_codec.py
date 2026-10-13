import json
from pathlib import Path
import base64
import pytest

from serialterminal.profiles.chatter.machine_codec import Frame, FrameError, Kind, Parser, MAX_LINE, decode, encode

VECTORS = json.loads((Path(__file__).parent/"fixtures/machine_vectors.json").read_text())


@pytest.mark.parametrize("vector", VECTORS)
def test_shared_vectors(vector):
    frame = Frame(Kind(vector["kind"]), vector["epoch"], vector["request"], bytes.fromhex(vector["payload"]))
    assert encode(frame).decode() == vector["line"]
    assert decode(vector["line"]) == frame
    body = bytes.fromhex(vector["body"])
    for index in range(len(body)):
        damaged = bytearray(body)
        damaged[index] ^= 1
        with pytest.raises(FrameError):
            decode(b"/m1 " + base64.b64encode(damaged))


def test_fragmentation_resynchronization_and_bound():
    frame = Frame(Kind.RX, 9, 0, b"payload")
    wire = encode(frame)
    parser = Parser()
    values = []
    for byte in wire:
        values += parser.feed(bytes([byte]))
    assert values == [frame]
    assert parser.feed(wire[:-1]+wire) == [frame]
    assert parser.errors == 1
    assert parser.feed(b"x"*(MAX_LINE*100)) == []
    assert len(parser.buffer) <= MAX_LINE
    assert parser.feed(wire) == [frame]
    assert parser.feed(wire+wire) == [frame,frame]


@pytest.mark.parametrize("line", [b"/m1 ", b"/m1 !!!!", b"/m1 QQ==", b"/m1 "+b"A"*400, b"USER"])
def test_bad_frames(line):
    with pytest.raises(FrameError):
        decode(line)

"""Input-event (B: variable) receive structures and helpers, without a sim.

The receive records are built byte by byte the way SimConnect lays them
out (packed, header of three DWORDs) and cast the way the receiver does,
so a layout slip shows up here rather than as garbage from a live sim.
"""
import os
import struct
import sys
from ctypes import POINTER, c_double, cast, create_string_buffer, sizeof

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simconnect import scdefs  # noqa: E402
from simconnect.receiver import ReceiverInstance  # noqa: E402
from simconnect.sc import InputEvent, input_event_name  # noqa: E402


def _recv(recv_id, body):
    """A SimConnect receive record: dwSize, dwVersion, dwID, then body."""
    size = 12 + len(body)
    buf = create_string_buffer(struct.pack("<III", size, 0, recv_id) + body, size)
    return buf, ReceiverInstance.cast_recv(cast(buf, POINTER(scdefs.RECV)))


def test_struct_sizes_match_the_packed_header():
    assert sizeof(scdefs.INPUT_EVENT_DESCRIPTOR) == 64 + 8 + 4
    assert sizeof(scdefs.RECV_GET_INPUT_EVENT) == 12 + 4 + 4
    assert sizeof(scdefs.RECV_SUBSCRIBE_INPUT_EVENT) == 12 + 8 + 4
    assert sizeof(scdefs.RECV_ENUMERATE_INPUT_EVENT_PARAMS) == 12 + 8 + 260


def test_receive_ids_dispatch_to_the_input_event_records():
    m = ReceiverInstance._recv_map
    assert m[scdefs.RECV_ID_ENUMERATE_INPUT_EVENTS] is scdefs.RECV_ENUMERATE_INPUT_EVENTS
    assert m[scdefs.RECV_ID_GET_INPUT_EVENT] is scdefs.RECV_GET_INPUT_EVENT
    assert m[scdefs.RECV_ID_SUBSCRIBE_INPUT_EVENT] is scdefs.RECV_SUBSCRIBE_INPUT_EVENT
    assert m[scdefs.RECV_ID_ENUMERATE_INPUT_EVENT_PARAMS] is scdefs.RECV_ENUMERATE_INPUT_EVENT_PARAMS


def test_enumeration_yields_every_descriptor_in_the_send():
    def desc(name, h, t):
        return name.encode().ljust(64, b"\0") + struct.pack("<QI", h, t)
    body = struct.pack("<IIII", 5, 2, 0, 1)
    body += desc("AUTOPILOT_Master", 0x1122334455667788, scdefs.INPUT_EVENT_TYPE_DOUBLE)
    body += desc("FMS_Scratchpad", 0xAABBCCDD, scdefs.INPUT_EVENT_TYPE_STRING)
    _buf, recv = _recv(scdefs.RECV_ID_ENUMERATE_INPUT_EVENTS, body)
    assert isinstance(recv, scdefs.RECV_ENUMERATE_INPUT_EVENTS)
    assert recv.dwRequestID == 5 and recv.dwArraySize == 2
    got = [(d.Name.decode(), d.Hash, d.eType) for d in recv.descriptors()]
    assert got == [
        ("AUTOPILOT_Master", 0x1122334455667788, scdefs.INPUT_EVENT_TYPE_DOUBLE),
        ("FMS_Scratchpad", 0xAABBCCDD, scdefs.INPUT_EVENT_TYPE_STRING),
    ]


def test_get_reply_decodes_a_double():
    body = struct.pack("<II", 9, scdefs.INPUT_EVENT_TYPE_DOUBLE) + struct.pack("<d", 0.75)
    _buf, recv = _recv(scdefs.RECV_ID_GET_INPUT_EVENT, body)
    assert isinstance(recv, scdefs.RECV_GET_INPUT_EVENT)
    assert recv.dwRequestID == 9
    assert recv.value == pytest.approx(0.75)


def test_get_reply_decodes_a_string_to_its_terminator():
    body = struct.pack("<II", 9, scdefs.INPUT_EVENT_TYPE_STRING) + b"KJFK\0\0\0\0"
    _buf, recv = _recv(scdefs.RECV_ID_GET_INPUT_EVENT, body)
    assert recv.value == "KJFK"


def test_subscribe_reply_carries_hash_and_value():
    body = struct.pack("<QI", 0xFEEDBEEF, scdefs.INPUT_EVENT_TYPE_DOUBLE) + struct.pack("<d", 1.0)
    _buf, recv = _recv(scdefs.RECV_ID_SUBSCRIBE_INPUT_EVENT, body)
    assert isinstance(recv, scdefs.RECV_SUBSCRIBE_INPUT_EVENT)
    assert recv.Hash == 0xFEEDBEEF
    assert recv.value == pytest.approx(1.0)


def test_declarations_cover_the_input_event_api():
    dll = scdefs.windll.LoadLibrary(
        os.path.join(os.path.dirname(scdefs.__file__), "SimConnect.dll"))
    decls = scdefs._decls(dll)
    for name in ("EnumerateInputEvents", "GetInputEvent", "SetInputEvent",
                 "SubscribeInputEvent", "UnsubscribeInputEvent",
                 "EnumerateInputEventParams"):
        assert name in decls


def test_name_normalization_drops_the_prefix_only():
    assert input_event_name("B:AUTOPILOT_Master") == "AUTOPILOT_Master"
    assert input_event_name("b:AUTOPILOT_Master") == "AUTOPILOT_Master"
    assert input_event_name("AUTOPILOT_Master") == "AUTOPILOT_Master"
    assert input_event_name("L:NotAnInputEvent") == "L:NotAnInputEvent"


def test_resolve_accepts_name_hash_and_record():
    from simconnect.sc import SimConnect
    sc = SimConnect.__new__(SimConnect)
    sc._input_events = {"AUTOPILOT_Master": InputEvent("AUTOPILOT_Master", 42, scdefs.INPUT_EVENT_TYPE_DOUBLE)}
    assert sc.resolve_input_event("B:AUTOPILOT_Master") == 42
    assert sc.resolve_input_event("AUTOPILOT_Master") == 42
    assert sc.resolve_input_event(42) == 42
    assert sc.resolve_input_event(sc._input_events["AUTOPILOT_Master"]) == 42
    with pytest.raises(KeyError):
        sc.resolve_input_event("B:Missing")


def test_remove_receiver_drops_only_the_named_one():
    from simconnect.sc import SimConnect
    sc = SimConnect.__new__(SimConnect)
    keep = ReceiverInstance(scdefs.RECV_OPEN, lambda r: True)
    drop_fn = lambda r: True  # noqa: E731
    drop = ReceiverInstance(scdefs.RECV_EXCEPTION, drop_fn)
    sc._receivers = [keep, drop]
    assert sc.remove_receiver(drop) is True
    assert sc._receivers == [keep]
    sc._receivers = [keep, drop]
    assert sc.remove_receiver(drop_fn) is True
    assert sc._receivers == [keep]
    assert sc.remove_receiver(drop_fn) is False

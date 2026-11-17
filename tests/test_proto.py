from devin_proxy.transport.proto import Message, f_str, f_varint, fields, varint


def test_varint_roundtrip():
    for n in (0, 1, 127, 128, 300, 65535, 2**32, 2**63 - 1):
        b = varint(n)
        i, val = 0, 0
        shift = 0
        while True:
            x = b[i]
            i += 1
            val |= (x & 0x7F) << shift
            if not x & 0x80:
                break
            shift += 7
        assert val == n


def test_f_str_and_fields():
    body = f_str(1, "hello") + f_varint(7, 42) + f_str(2, "")
    got = list(fields(body))
    assert (1, 2, b"hello") in got
    assert (7, 0, 42) in got


def test_message_builder():
    m = Message().str_(1, "x").varint_(3, 7)
    out = list(fields(m.body))
    assert (1, 2, b"x") in out
    assert (3, 0, 7) in out


def test_fields_tolerates_reserved_wiretype():
    # field 1 ok, then a bogus tag with wt=6 (reserved) — must not raise,
    # must yield what was already decoded
    body = f_str(1, "ok") + bytes([(5 << 3) | 6]) + b"\x00\x00"
    got = list(fields(body))
    assert (1, 2, b"ok") in got


def test_fields_tolerates_truncated_tail():
    body = f_str(1, "ok") + bytes([2 << 3 | 2]) + b"\xff\xff\xff\xff\x0f"  # huge len
    got = list(fields(body))
    assert (1, 2, b"ok") in got


def test_fields_skips_group():
    # wt=3 start-group (field 4) wrapping a varint, wt=4 end-group — skipped,
    # following fields still decode
    group = bytes([(4 << 3) | 3, (1 << 3) | 0, 0x2A, (4 << 3) | 4])
    body = f_str(1, "pre") + group + f_str(2, "post")
    got = [(no, wt) for no, wt, _ in fields(body)]
    assert (1, 2) in got
    assert (2, 2) in got


def test_fields_bad_varint_stops_not_raises():
    body = f_str(1, "ok") + b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff"
    got = list(fields(body))
    assert (1, 2, b"ok") in got

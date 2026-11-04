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

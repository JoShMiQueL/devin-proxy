from devin_proxy.translate import openai_to_wire
from devin_proxy.transport.proto import fields


def _source(prompt_bytes):
    for no, _wt, v in fields(prompt_bytes):
        if no == 2:
            return v
    return None


def _text(prompt_bytes):
    for no, _wt, v in fields(prompt_bytes):
        if no == 3:
            return v.decode()
    return ""


def test_user_becomes_source1():
    msgs = [{"role": "user", "content": "hi"}]
    _, prompts = openai_to_wire(msgs)
    assert len(prompts) == 1
    assert _source(prompts[0]) == 1
    assert _text(prompts[0]) == "hi"


def test_assistant_becomes_source2():
    msgs = [{"role": "assistant", "content": "answer"}]
    _, prompts = openai_to_wire(msgs)
    assert _source(prompts[0]) == 2


def test_system_goes_to_field2():
    msgs = [{"role": "system", "content": "custom sys"},
            {"role": "user", "content": "u"}]
    sys_, _ = openai_to_wire(msgs)
    assert sys_ == "custom sys"


def test_frame_note_inserted_before_last_user():
    msgs = [{"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"}]
    _, prompts = openai_to_wire(msgs, frame_note="FRAME")
    texts = [_text(p) for p in prompts]
    sources = [_source(p) for p in prompts]
    assert "FRAME" in texts
    assert texts.index("FRAME") < texts.index("q2")
    assert sources[texts.index("FRAME")] == 2

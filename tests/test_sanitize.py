from devin_proxy.jailbreak.sanitize import sanitize_history_artifacts, sanitize_messages


def test_drops_empty_assistant():
    msgs = [{"role": "assistant", "content": ""},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "u"}]
    out, dropped = sanitize_messages(msgs)
    assert dropped == 1
    assert len(out) == 2


def test_keeps_tool_calls():
    msgs = [{"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "f"}}]}]
    _out, dropped = sanitize_messages(msgs)
    assert dropped == 0


def test_excises_refusal_sentence():
    # Anchored refusal at the head of a message that also carries useful text:
    # HISTORY_REFUSAL_RE's anchored branch catches the leading refusal, and
    # the surviving sentences are long enough to keep the message.
    msgs = [{"role": "assistant",
             "content": "I can't help with that. Here's the code you asked "
                        "for and it works correctly with the setup described "
                        "in the previous message, so the answer survives."}]
    out, stats = sanitize_history_artifacts(msgs)
    assert stats["history_refusals"] == 1
    assert "I can't help" not in out[0]["content"]
    assert "Here's the code" in out[0]["content"]


def test_strips_switch_note():
    msgs = [{"role": "user",
             "content": "[Note: model was just switched from X to Y. Adjust "
                        "your self-identification accordingly.] real question"}]
    out, stats = sanitize_history_artifacts(msgs)
    assert stats["switch_notes"] == 1
    assert out[0]["content"] == "real question"

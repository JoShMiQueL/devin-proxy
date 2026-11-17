from devin_proxy.config import Settings
from devin_proxy.pipeline import Engine


class _T:
    def __init__(self, name="t", desc="d", params=None):
        self.name, self.description = name, desc
        self.parameters = params or {}


class _Tool:
    def __init__(self, name="t", desc="d", params=None):
        self.function = _T(name, desc, params)


def _engine(**kw):
    from devin_proxy.jailbreak.override import OverridePrompt
    from devin_proxy.transport.auth import Auth
    s = Settings(**kw)
    return Engine(s, Auth(s.backend, client_version="0"), OverridePrompt())


def _big_msgs(n_pairs, chunk=12000):
    msgs = [{"role": "system", "content": "sys " + "x" * 800}]
    for i in range(n_pairs):
        msgs.append({"role": "user", "content": f"u{i} " + "q" * chunk})
        msgs.append({"role": "assistant", "content": f"a{i} " + "r" * chunk})
    msgs.append({"role": "user", "content": "latest"})
    return msgs


def test_no_prune_under_budget():
    e = _engine()
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "hi"}]
    out, dropped = e._prune_history(msgs, [], e.settings)
    assert dropped == 0 and out == msgs


def test_prune_drops_oldest_keeps_system_and_tail():
    e = _engine(max_input_tokens=240000, prune_keep_turns=12)
    msgs = _big_msgs(80)
    tools = [_Tool()]
    out, dropped = e._prune_history(msgs, tools, e.settings)
    assert dropped > 0
    assert out[0]["role"] == "system"
    # tail kept: last message is the final user ask
    assert out[-1]["content"] == "latest"
    # under budget after prune
    assert e._est_tokens(out, tools) <= 240000 + (240000 // 10)


def test_prune_respects_keep_turns_floor():
    e = _engine(max_input_tokens=1000, prune_keep_turns=12)
    msgs = _big_msgs(50)
    out, _ = e._prune_history(msgs, [], e.settings)
    non_sys = [m for m in out if m.get("role") != "system"]
    assert len(non_sys) <= 12


def test_prune_disabled_when_zero():
    e = _engine(max_input_tokens=0)
    msgs = _big_msgs(40)
    out, dropped = e._prune_history(msgs, [], e.settings)
    assert dropped == 0 and len(out) == len(msgs)


def test_est_tokens_counts_content_and_reasoning():
    e = _engine()
    msgs = [{"role": "assistant", "content": "x" * 400,
             "reasoning_content": "y" * 400}]
    assert e._est_tokens(msgs, []) == (400 + 400) // 4

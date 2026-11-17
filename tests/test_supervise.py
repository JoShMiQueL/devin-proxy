"""The service watchdog: `devin-proxy supervise` respawns a dead serve.

The regression this guards: a bare `serve` child used to be the service.
When it died mid-request the port sat unbound until something manually
relaunched it — the client-visible ECONNREFUSED. The supervisor keeps the
port gap under ~1s by respawning on any non-zero exit.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from devin_proxy import cli
from devin_proxy.service import start


def _args(**kw):
    a = MagicMock()
    a.host = kw.get("host", "127.0.0.1")
    a.port = kw.get("port", 8390)
    a.name = kw.get("name", "default")
    return a


class TestSuperviseLoop:
    """cmd_supervise respawns the serve child on non-zero exit."""

    def test_respawns_after_crash(self):
        # child 1 dies rc=1, child 2 dies rc=1, child 3 exits clean rc=0
        child = MagicMock()
        child.wait.side_effect = [1, 1, 0]
        child.poll.return_value = None
        with patch("subprocess.Popen", return_value=child) as popen, \
                patch("time.sleep"):
            rc = cli.cmd_supervise(_args())
        assert rc == 0
        assert popen.call_count == 3
        # every spawn launches `serve --no-autostart`
        for call in popen.call_args_list:
            cmd = call[0][0]
            assert cmd[1:3] == ["-m", "devin_proxy"]
            assert "serve" in cmd
            assert "--no-autostart" in cmd

    def test_clean_exit_does_not_respawn(self):
        child = MagicMock()
        child.wait.return_value = 0
        child.poll.return_value = None
        with patch("subprocess.Popen", return_value=child) as popen:
            rc = cli.cmd_supervise(_args())
        assert rc == 0
        assert popen.call_count == 1

    def test_gives_up_on_spawn_failures(self):
        with patch("subprocess.Popen", side_effect=OSError("no binary")), \
                patch("time.sleep"):
            rc = cli.cmd_supervise(_args())
        assert rc == 1  # MAX_FAST_FAILURES reached -> bail


class TestServiceLaunchesSupervisor:
    """service.start must spawn `supervise`, not bare `serve`."""

    def test_spawned_cmd_is_supervise(self, tmp_path, monkeypatch):
        captured = {}

        class FakeProc:
            pid = 4242

            def poll(self):
                return None  # pretend alive

            def terminate(self):
                pass

        def fake_popen(cmd, **kw):
            captured["cmd"] = cmd
            return FakeProc()

        monkeypatch.setattr("devin_proxy.service.REG_DIR", tmp_path)
        monkeypatch.setattr("devin_proxy.service.get",
                            lambda name, probe=True: None)
        monkeypatch.setattr("devin_proxy.service._free_port",
                            lambda h, p, **kw: 8390)
        monkeypatch.setattr("devin_proxy.service._probe", lambda url: True)
        with patch("subprocess.Popen", side_effect=fake_popen), \
                patch("devin_proxy.service.open"):
            inst, spawned = start("default", "127.0.0.1", 8390)
        assert spawned
        cmd = captured["cmd"]
        assert cmd[:3] == [sys.executable, "-m", "devin_proxy"]
        assert "supervise" in cmd
        assert "serve" not in cmd  # supervise spawns serve itself
        assert inst.pid == 4242

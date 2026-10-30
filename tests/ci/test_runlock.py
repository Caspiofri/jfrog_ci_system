"""Run locks: one holder per name across processes; a second run exits 2 with the holder's pid and start time."""
import json
import subprocess
import sys
import textwrap

import pytest

from ci import run as run_cli
from ci.runlock import RunLocked, run_lock


def test_a_second_holder_is_refused_with_the_first_holders_details(tmp_path):
    with run_lock("collect", tmp_path):
        with pytest.raises(RunLocked) as exc:
            with run_lock("collect", tmp_path):
                pass
        assert f"pid {__import__('os').getpid()}" in str(exc.value) and "since 20" in str(exc.value)
        with run_lock("detect", tmp_path):  # another name is independent
            pass
    with run_lock("collect", tmp_path):  # released after the block
        pass


def test_the_lock_is_released_when_the_block_raises(tmp_path):
    with pytest.raises(ValueError):
        with run_lock("collect", tmp_path):
            raise ValueError("boom")
    with run_lock("collect", tmp_path):
        pass


def test_a_lock_held_by_another_process_blocks_until_it_exits(tmp_path):
    holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import sys, time
        from pathlib import Path
        from ci.runlock import run_lock
        with run_lock("collect", Path({str(tmp_path)!r})):
            print("held", flush=True)
            sys.stdin.readline()
        """)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(RunLocked) as exc:
            with run_lock("collect", tmp_path):
                pass
        assert f"pid {holder.pid}" in str(exc.value)
    finally:
        holder.communicate("\n", timeout=10)
    with run_lock("collect", tmp_path):  # the holder exited: free again
        pass
    assert json.loads((tmp_path / "collect.lock").read_text() or "{}") == {}


def test_ci_run_exits_2_when_a_collection_is_already_running(tmp_path, monkeypatch, capsys):
    import ci.runlock

    monkeypatch.setattr(ci.runlock, "LOCK_DIR", tmp_path)
    monkeypatch.setattr(run_cli, "run", lambda *a, **k: pytest.fail("must not collect while locked"))
    with run_lock("collect", tmp_path):
        with pytest.raises(SystemExit) as exc:
            run_cli.main([])
    assert exc.value.code == 2
    assert "another run is in progress (pid" in capsys.readouterr().err

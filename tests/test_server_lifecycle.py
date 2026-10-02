"""Regression tests for the embedded Wyoming server's shutdown lifecycle."""

from __future__ import annotations

import signal
import socket
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

_SERVER = """
import sys
import uvicorn
from fastapi import FastAPI
from agent_cli.server.common import create_lifespan

class Registry:
    async def start(self):
        pass
    async def stop(self):
        print("REGISTRY_STOPPED", flush=True)
    def list_status(self):
        return []

app = FastAPI(lifespan=create_lifespan(
    Registry(),
    wyoming_handler_module=f"agent_cli.server.{sys.argv[1]}.wyoming_handler",
    wyoming_uri=f"tcp://127.0.0.1:{sys.argv[3]}",
))
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]), loop=sys.argv[4])
"""


def _is_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
            return True
    except OSError:
        return False


@pytest.mark.skipif(sys.platform == "win32", reason="Requires POSIX SIGTERM handling")
@pytest.mark.timeout(30)
@pytest.mark.parametrize("server_kind", ["whisper", "tts"])
@pytest.mark.parametrize("event_loop", ["asyncio", "uvloop"])
def test_sigterm_stops_http_and_wyoming(
    unused_tcp_port_factory: Callable[[], int],
    server_kind: str,
    event_loop: str,
) -> None:
    """Wyoming 1.10.2 run() steals SIGTERM; embedding must retain Uvicorn shutdown.

    Upstream wyoming/server.py registers a process-wide handler in run(), but
    start()/stop() leave signals to the host. Exercise the actual dependency
    in a child so a regression cannot replace pytest's own signal handlers.
    """
    if event_loop == "uvloop":
        pytest.importorskip("uvloop")

    http_port, wyoming_port = unused_tcp_port_factory(), unused_tcp_port_factory()
    with subprocess.Popen(
        [sys.executable, "-c", _SERVER, server_kind, str(http_port), str(wyoming_port), event_loop],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ) as process:
        try:
            deadline = time.monotonic() + 15
            while not (_is_listening(http_port) and _is_listening(wyoming_port)):
                assert process.poll() is None, process.communicate()[0]
                assert time.monotonic() < deadline, "Server did not start"
                time.sleep(0.02)

            # An actual protocol reply proves Wyoming finished its startup.
            with socket.create_connection(("127.0.0.1", wyoming_port), timeout=2) as client:
                client.sendall(b'{"type":"describe"}\n')
                assert b'"info"' in client.recv(65536)

            process.send_signal(signal.SIGTERM)
            try:
                output, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pytest.fail("SIGTERM left the HTTP server running after Wyoming stopped")

            assert "REGISTRY_STOPPED" in output
            assert not _is_listening(http_port)
            assert not _is_listening(wyoming_port)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

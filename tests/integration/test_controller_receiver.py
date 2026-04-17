"""Integration tests for the controller's receiver role dispatch."""

from __future__ import annotations

import asyncio
import json
import socket
import time
from pathlib import Path

import pytest

from tcp_sim.gui.controller import (
    ReceiverSettings,
    RuntimeSettings,
    SimulatorController,
    SinkSettings,
    StreamSettings,
)


def _reserve_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _reserve_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_status(
    controller: SimulatorController,
    fragment: str,
    timeout_seconds: float = 3.0,
) -> bool:
    seen: list[str] = getattr(controller, "_test_seen_messages", [])
    setattr(controller, "_test_seen_messages", seen)
    deadline = time.monotonic() + timeout_seconds
    while True:
        seen.extend(controller.read_status_messages())
        if any(fragment in m for m in seen):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


@pytest.mark.integration
def test_controller_starts_tcp_server_receiver_and_writes_sink(tmp_path: Path) -> None:
    sink_path = tmp_path / "records.jsonl"
    port = _reserve_tcp_port()
    controller = SimulatorController()
    try:
        controller.start_reception(
            RuntimeSettings(
                mode="server",
                protocol="tcp",
                host="127.0.0.1",
                port=port,
            ),
            ReceiverSettings(framing_mode="lf"),
            SinkSettings(enabled=True, path=str(sink_path), format="jsonl"),
        )
        assert _wait_for_status(controller, "Reception started")

        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
            client.sendall(b"alpha\nbeta\n")

        # Wait until two records land in the sink file.
        deadline = time.monotonic() + 3.0
        lines: list[str] = []
        while time.monotonic() < deadline:
            if sink_path.exists():
                lines = sink_path.read_text(encoding="utf-8").splitlines()
                if len(lines) >= 2:
                    break
            time.sleep(0.05)
        assert len(lines) >= 2
        payloads = {json.loads(ln)["payload"] for ln in lines[:2]}
        assert payloads == {"alpha", "beta"}
    finally:
        controller.shutdown()


@pytest.mark.integration
def test_controller_role_toggle_stops_sender_before_starting_receiver(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "records.csv"
    data_path.write_text("id,value\n1,a\n2,b\n", encoding="utf-8")
    send_port = _reserve_tcp_port()
    recv_port = _reserve_tcp_port()

    controller = SimulatorController()
    try:
        # Start as sender first.
        controller.start_transmission(
            RuntimeSettings(
                mode="server",
                protocol="tcp",
                host="127.0.0.1",
                port=send_port,
                send_timeout_seconds=1.0,
            ),
            StreamSettings(
                file_path=str(data_path),
                delimiter=",",
                has_header=True,
                send_header=True,
                rate_features_per_second=5.0,
                loop=True,
            ),
        )
        assert _wait_for_status(controller, "Transmission started")

        # Flip to receiver — controller should stop the sender automatically.
        controller.start_reception(
            RuntimeSettings(
                mode="server",
                protocol="tcp",
                host="127.0.0.1",
                port=recv_port,
            ),
            ReceiverSettings(),
            SinkSettings(enabled=False),
        )
        assert _wait_for_status(controller, "Switching to receiver role")
        assert _wait_for_status(controller, "Reception started")

        # Verify the sender port is no longer bound.
        with pytest.raises((ConnectionRefusedError, OSError, TimeoutError)):
            with socket.create_connection(("127.0.0.1", send_port), timeout=0.5):
                pass
    finally:
        controller.shutdown()


@pytest.mark.integration
def test_controller_configure_sink_runtime_swap(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    port = _reserve_tcp_port()

    controller = SimulatorController()
    try:
        controller.start_reception(
            RuntimeSettings(mode="server", protocol="tcp", host="127.0.0.1", port=port),
            ReceiverSettings(),
            SinkSettings(enabled=True, path=str(first), format="jsonl"),
        )
        assert _wait_for_status(controller, "Reception started")

        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
            client.sendall(b"one\n")
            # wait briefly for first record to land
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if first.exists() and first.read_text(encoding="utf-8").strip():
                    break
                time.sleep(0.05)

            controller.configure_sink(
                SinkSettings(enabled=True, path=str(second), format="jsonl")
            )
            assert _wait_for_status(controller, "Sink reconfigured")

            client.sendall(b"two\n")
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if second.exists() and second.read_text(encoding="utf-8").strip():
                    break
                time.sleep(0.05)

        assert first.exists()
        assert second.exists()
        first_obj = json.loads(first.read_text(encoding="utf-8").splitlines()[0])
        second_obj = json.loads(second.read_text(encoding="utf-8").splitlines()[0])
        assert first_obj["payload"] == "one"
        assert second_obj["payload"] == "two"
    finally:
        controller.shutdown()


@pytest.mark.integration
def test_controller_starts_udp_server_receiver() -> None:
    port = _reserve_udp_port()
    controller = SimulatorController()
    try:
        controller.start_reception(
            RuntimeSettings(mode="server", protocol="udp", host="127.0.0.1", port=port),
            ReceiverSettings(),
            SinkSettings(enabled=False),
        )
        assert _wait_for_status(controller, "Reception started")

        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sender.sendto(b"hello-udp", ("127.0.0.1", port))
            # Wait for the engine's receiver_records periodic emission.
            assert _wait_for_status(
                controller, "__receiver_records__:", timeout_seconds=3.0
            )
        finally:
            sender.close()
    finally:
        controller.shutdown()

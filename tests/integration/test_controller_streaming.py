import socket
import time

import pytest

from tcp_sim.gui.controller import RuntimeSettings, SimulatorController, StreamSettings


def _reserve_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_status(
    controller: SimulatorController,
    expected_fragment: str,
    timeout_seconds: float = 3.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for message in controller.read_status_messages():
            if expected_fragment in message:
                return True
        time.sleep(0.05)
    return False


@pytest.mark.integration
def test_controller_server_mode_streams_messages(tmp_path) -> None:
    data_path = tmp_path / "records.csv"
    data_path.write_text("id,value\n1,a\n2,b\n", encoding="utf-8")

    port = _reserve_tcp_port()
    controller = SimulatorController()

    try:
        controller.start_transmission(
            RuntimeSettings(
                mode="server",
                protocol="tcp",
                host="127.0.0.1",
                port=port,
                send_timeout_seconds=1.0,
            ),
            StreamSettings(
                file_path=str(data_path),
                delimiter=",",
                has_header=True,
                send_header=True,
                rate_features_per_second=20.0,
                loop=True,
            ),
        )

        assert _wait_for_status(controller, "Transmission started", timeout_seconds=3.0)
        assert _wait_for_status(controller, "__progress__:", timeout_seconds=3.0)
        assert _wait_for_status(controller, "__rate__:", timeout_seconds=3.0)
        assert _wait_for_status(controller, "__sent__:", timeout_seconds=3.0)

        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
            client.settimeout(3.0)
            payload = client.recv(4096)

        assert payload
        decoded = payload.decode("utf-8", errors="ignore")
        assert "id,value" in decoded or "1,a" in decoded
    finally:
        controller.shutdown()


@pytest.mark.integration
def test_controller_server_mode_velocity_lifecycle_sampling(tmp_path) -> None:
    data_path = tmp_path / "records.csv"
    data_path.write_text("id,value\n1,a\n2,b\n", encoding="utf-8")

    port = _reserve_tcp_port()
    controller = SimulatorController()

    try:
        controller.start_transmission(
            RuntimeSettings(
                mode="server",
                protocol="tcp",
                host="127.0.0.1",
                port=port,
                send_timeout_seconds=1.0,
            ),
            StreamSettings(
                file_path=str(data_path),
                delimiter=",",
                has_header=True,
                send_header=True,
                rate_features_per_second=20.0,
                loop=True,
            ),
        )

        assert _wait_for_status(controller, "Transmission started", timeout_seconds=3.0)

        payloads: list[bytes] = []
        for _ in range(3):
            with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
                client.settimeout(3.0)
                payloads.append(client.recv(4096))
            time.sleep(0.1)

        assert all(payloads)
    finally:
        controller.shutdown()

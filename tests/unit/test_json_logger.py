import json
import logging

import pytest

from tcp_sim.logging.json_logger import configure_json_logger


@pytest.mark.unit
def test_json_logger_writes_structured_payload(tmp_path) -> None:
    log_path = tmp_path / "sim.log"
    logger = configure_json_logger(
        name="tcp_sim.test",
        level="INFO",
        log_file=log_path,
        max_bytes=1024,
        backup_count=1,
        console=False,
    )

    logger.info("connected", extra={"event": "client_connect", "client": "127.0.0.1"})
    for handler in logger.handlers:
        handler.flush()

    line = log_path.read_text(encoding="utf-8").strip().splitlines()[0]
    payload = json.loads(line)
    assert payload["message"] == "connected"
    assert payload["event"] == "client_connect"
    assert payload["client"] == "127.0.0.1"


@pytest.mark.unit
def test_json_logger_rotates_files(tmp_path) -> None:
    log_path = tmp_path / "rotate.log"
    logger = configure_json_logger(
        name="tcp_sim.rotate",
        level=logging.INFO,
        log_file=log_path,
        max_bytes=120,
        backup_count=1,
        console=False,
    )

    for _ in range(20):
        logger.info("x" * 30, extra={"event": "send"})

    for handler in logger.handlers:
        handler.flush()

    rotated = tmp_path / "rotate.log.1"
    assert rotated.exists()
